from contextlib import asynccontextmanager
import pytest
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

from shield.exceptions import ShieldBlocked, ShieldEscalated
from receiver.receiver_agent import ReceiverAgent
from receiver.tools import ALL_TOOLS


def test_tool_definitions():
    tool_names = [t.name for t in ALL_TOOLS]
    expected_tools = [
        "search_customer_ticket",
        "get_customer_ticket",
        "get_orders_ticket",
        "get_payment_ticket",
        "request_refund_ticket",
        "send_reply_ticket",
        "delete_customer_ticket",
    ]
    for expected in expected_tools:
        assert expected in tool_names
    assert len(ALL_TOOLS) == 7


@pytest.mark.asyncio
async def test_receiver_agent_handles_blocked():
    with patch.dict("os.environ", {"GROQ_API_KEY": "gsk_test12345"}):
        agent = ReceiverAgent()
        
        mock_ticket = MagicMock()
        mock_ticket.id = uuid.uuid4()
        mock_ticket.display_id = 500001
        mock_ticket.sender_email = "test@example.com"
        mock_ticket.subject = "Delete account"
        mock_ticket.body = "Please delete my account"
        mock_ticket.status = "pending"

        mock_session = MagicMock()
        mock_session.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=mock_ticket)))
        mock_session.commit = AsyncMock()

        @asynccontextmanager
        async def mock_session_factory():
            yield mock_session

        with patch("receiver.receiver_agent.async_session_factory", mock_session_factory):
            with patch.object(
                agent.app,
                "ainvoke",
                AsyncMock(
                    side_effect=ShieldBlocked(
                        reason="Denied by policy: Matched rule 'deny_customer_delete'",
                        decision_id="dec-123",
                        risk_score=100.0,
                        tool="delete_customer_ticket",
                    )
                ),
            ):
                res = await agent.handle_ticket(mock_ticket.id)
                assert res["status"] == "blocked"
                assert mock_ticket.status == "blocked"
                assert "deny_customer_delete" in res["reason"]


@pytest.mark.asyncio
async def test_receiver_agent_handles_escalated():
    with patch.dict("os.environ", {"GROQ_API_KEY": "gsk_test12345"}):
        agent = ReceiverAgent()
        
        mock_ticket = MagicMock()
        mock_ticket.id = uuid.uuid4()
        mock_ticket.display_id = 500002
        mock_ticket.sender_email = "test@example.com"
        mock_ticket.subject = "Give PAN"
        mock_ticket.body = "Send me PAN card number"
        mock_ticket.status = "pending"

        mock_session = MagicMock()
        mock_session.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=mock_ticket)))
        mock_session.commit = AsyncMock()

        @asynccontextmanager
        async def mock_session_factory():
            yield mock_session

        with patch("receiver.receiver_agent.async_session_factory", mock_session_factory):
            with patch.object(
                agent.app,
                "ainvoke",
                AsyncMock(
                    side_effect=ShieldEscalated(
                        reason="Requires supervisor approval",
                        decision_id="dec-456",
                        risk_score=50.0,
                        tool="get_customer_ticket",
                        approval_id="appr-789",
                    )
                ),
            ):
                res = await agent.handle_ticket(mock_ticket.id)
                assert res["status"] == "escalated"
                assert mock_ticket.status == "escalated"


@pytest.mark.asyncio
async def test_receiver_agent_handles_replied():
    with patch.dict("os.environ", {"GROQ_API_KEY": "gsk_test12345"}):
        agent = ReceiverAgent()

        mock_ticket = MagicMock()
        mock_ticket.id = uuid.uuid4()
        mock_ticket.display_id = 500003
        mock_ticket.sender_email = "skanda.dell@gmail.com"
        mock_ticket.subject = "Order status"
        mock_ticket.body = "When will my order arrive?"
        mock_ticket.status = "pending"

        mock_final_state = {
            "messages": [
                MagicMock(
                    tool_calls=[{
                        "name": "send_reply_ticket",
                        "args": {
                            "to": "skanda.dell@gmail.com",
                            "subject": "Re: Order status",
                            "body": "Your order #100001 has been delivered.",
                        }
                    }]
                )
            ]
        }

        mock_session = MagicMock()
        mock_session.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=mock_ticket)))
        mock_session.commit = AsyncMock()
        mock_session.add = MagicMock()

        @asynccontextmanager
        async def mock_session_factory():
            yield mock_session

        with patch("receiver.receiver_agent.async_session_factory", mock_session_factory):
            with patch.object(agent.app, "ainvoke", AsyncMock(return_value=mock_final_state)):
                res = await agent.handle_ticket(mock_ticket.id)
                assert res["status"] == "replied"
                assert mock_ticket.status == "replied"
                assert mock_session.add.called
