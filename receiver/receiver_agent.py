import argparse
import asyncio
import logging
import os
from pathlib import Path
import sys
from typing import Annotated, Any, Optional, Sequence, TypedDict
import uuid
import operator

from dotenv import load_dotenv
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_groq import ChatGroq
from langgraph.graph import END, StateGraph
from langgraph.prebuilt import ToolNode
from shield.exceptions import ShieldBlocked, ShieldEscalated
from sqlalchemy import select

# Ensure ticket_demo is in pythonpath
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from db.session import async_session_factory
from db.models import Ticket, OutboundEmail
from receiver.tools import ALL_TOOLS

_ENV_PATH = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(_ENV_PATH)

logger = logging.getLogger("ticket_demo.receiver")

RECEIVER_SYSTEM_PROMPT = """You are a customer support agent for an e-commerce company.
You receive tickets by email and take actions to resolve them.

Use the tools available to look up customers, orders, payments, and
refunds, and to send a reply.

When you are done, call send_reply_ticket(subject=..., body=...) with
the final message back to the sender. Do NOT pass a `to` argument —
the reply address is set by the system automatically.

Never include customer PII (PAN, Aadhaar, full card numbers, addresses,
phone numbers) in the reply body. If unsure, omit it."""


class AgentState(TypedDict):
    messages: Annotated[Sequence[BaseMessage], operator.add]


def build_receiver_graph(llm: ChatGroq):
    llm_with_tools = llm.bind_tools(ALL_TOOLS)

    async def call_model(state: AgentState):
        messages = state["messages"]
        response = await llm_with_tools.ainvoke(messages)
        return {"messages": [response]}

    def should_continue(state: AgentState):
        messages = state["messages"]
        last_message = messages[-1]
        if hasattr(last_message, "tool_calls") and last_message.tool_calls:
            # Check if send_reply_ticket was invoked
            for tc in last_message.tool_calls:
                if tc.get("name") == "send_reply_ticket":
                    pass
            return "tools"
        return END

    tool_node = ToolNode(ALL_TOOLS)

    workflow = StateGraph(AgentState)
    workflow.add_node("agent", call_model)
    workflow.add_node("tools", tool_node)

    workflow.set_entry_point("agent")
    workflow.add_conditional_edges("agent", should_continue, {"tools": "tools", END: END})
    workflow.add_edge("tools", "agent")

    return workflow.compile()


class ReceiverAgent:
    def __init__(self, model_name: Optional[str] = None):
        self.model_name = (
            model_name
            or os.getenv("RECEIVER_MODEL")
            or "openai/gpt-oss-120b"
        )
        api_key = os.getenv("GROQ_API_KEY")
        if not api_key:
            raise ValueError("GROQ_API_KEY must be set to run ReceiverAgent")

        self.llm = ChatGroq(
            model=self.model_name,
            api_key=api_key,
            temperature=0.0,
        )
        self.app = build_receiver_graph(self.llm)

    async def handle_ticket(self, ticket_id: uuid.UUID) -> dict[str, Any]:
        """Loads the ticket, runs the graph, catches ShieldBlocked/ShieldEscalated, updates DB."""

        # ── Phase 1: Load ticket data (short session, closed before LLM) ──
        async with async_session_factory() as session:
            stmt = select(Ticket).where(Ticket.id == ticket_id)
            res = await session.execute(stmt)
            ticket = res.scalar_one_or_none()
            if not ticket:
                return {"error": f"Ticket {ticket_id} not found", "status": "not_found"}

            # Extract all fields we need — session closes at end of block
            t_display_id = ticket.display_id
            t_sender_email = ticket.sender_email
            t_subject = ticket.subject
            t_body = ticket.body

        # ── Phase 2: Run LLM graph — NO DB session held open ──────────────
        user_content = (
            f"New Support Ticket received:\n"
            f"From: {t_sender_email}\n"
            f"Subject: {t_subject}\n\n"
            f"{t_body}"
        )

        initial_messages = [
            SystemMessage(content=RECEIVER_SYSTEM_PROMPT),
            HumanMessage(content=user_content),
        ]

        status = "replied"
        reason = "Resolved successfully"
        reply_subject = f"Re: {t_subject}"
        reply_body = "Your request has been received and processed."
        shield_verdict = "ALLOW"

        try:
            final_state = await self.app.ainvoke(
                {"messages": initial_messages},
                config={"recursion_limit": 15},
            )

            # Extract reply content if send_reply_ticket was called or from last AI message
            for msg in final_state.get("messages", []):
                if hasattr(msg, "tool_calls") and msg.tool_calls:
                    for tc in msg.tool_calls:
                        if tc.get("name") == "send_reply_ticket":
                            args = tc.get("args", {})
                            reply_subject = args.get("subject", reply_subject)
                            reply_body = args.get("body", reply_body)
                elif hasattr(msg, "content") and msg.content and not isinstance(msg, (HumanMessage, SystemMessage)):
                    reply_body = str(msg.content)

        except ShieldBlocked as e:
            status = "blocked"
            reason = e.reason
            shield_verdict = "BLOCK"
            print(f"[receiver] #{t_display_id} BLOCKED: {e.reason} (risk: {e.risk_score})")

        except ShieldEscalated as e:
            status = "escalated"
            reason = e.reason
            shield_verdict = "ESCALATE"
            print(f"[receiver] #{t_display_id} ESCALATED: {e.reason} (approval_id: {e.approval_id})")

        except Exception as e:
            logger.error("[receiver] Unexpected error processing ticket #%s: %s", t_display_id, e)
            status = "blocked"
            reason = str(e)
            shield_verdict = "ERROR"

        # ── Phase 3: Persist result (fresh short session) ─────────────────
        async with async_session_factory() as session:
            stmt = select(Ticket).where(Ticket.id == ticket_id)
            res = await session.execute(stmt)
            ticket = res.scalar_one_or_none()

            ticket.status = status

            if status == "replied":
                send_real = os.getenv("SEND_REAL_EMAILS", "false").lower() in ("true", "1", "yes")
                delivery_mode = "real" if send_real else "mock"
                receiver_email = os.getenv("RECEIVER_EMAIL", "agentshield.demo@gmail.com")
                sender_email = os.getenv("SENDER_EMAIL", "skanda.dell@gmail.com")

                outbound = OutboundEmail(
                    id=uuid.uuid4(),
                    ticket_id=ticket.id,
                    from_email=receiver_email,
                    to_email=sender_email,
                    subject=reply_subject,
                    body=reply_body,
                    delivery_mode=delivery_mode,
                )
                session.add(outbound)
                print(f"[receiver] #{t_display_id} REPLIED [{delivery_mode}] -> {sender_email}")

            await session.commit()

        return {
            "ticket_id": str(ticket_id),
            "display_id": t_display_id,
            "status": status,
            "shield_verdict": shield_verdict,
            "reason": reason,
        }



async def run_receiver(cycles: int = 1):
    agent = ReceiverAgent()
    processed_count = 0
    print(f"[receiver] Starting receiver loop: target_cycles={cycles}")

    while processed_count < cycles:
        async with async_session_factory() as session:
            stmt = (
                select(Ticket)
                .where(Ticket.status == "pending")
                .order_by(Ticket.created_at.asc())
                .limit(1)
            )
            res = await session.execute(stmt)
            ticket = res.scalar_one_or_none()

        if not ticket:
            print("[receiver] No pending tickets in queue. Exiting loop.")
            break

        await agent.handle_ticket(ticket.id)
        processed_count += 1
        await asyncio.sleep(1.0)

    print(f"[receiver] Loop completed. Processed {processed_count} tickets.")


def main():
    parser = argparse.ArgumentParser(description="Receiver Agent: Processes incoming support tickets.")
    parser.add_argument("--cycles", type=int, default=1, help="Number of tickets to process (default 1)")
    args = parser.parse_args()

    asyncio.run(run_receiver(cycles=args.cycles))


if __name__ == "__main__":
    main()
