from decimal import Decimal
import logging
import os
from pathlib import Path
import sys
from typing import Any
import uuid

from dotenv import load_dotenv
from langchain_core.tools import tool
from shield import protect
from sqlalchemy import select

# Ensure ticket_demo is in pythonpath
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from db.session import async_session_factory
from db.models import Customer, Order, Payment, Refund

_ENV_PATH = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(_ENV_PATH)

logger = logging.getLogger("ticket_demo.receiver.tools")


@tool
@protect(tool="search_customer_ticket", resource_type="customer", data_classification="internal")
async def search_customer_ticket(email: str) -> dict[str, Any]:
    """Search for a customer by their email address."""
    async with async_session_factory() as session:
        stmt = select(Customer).where(Customer.email == email.strip().lower())
        res = await session.execute(stmt)
        customer = res.scalar_one_or_none()
        if not customer:
            return {"found": False, "message": f"Customer with email {email} not found."}
        return {
            "found": True,
            "display_id": customer.display_id,
            "name": customer.name,
            "email": customer.email,
            "account_status": customer.account_status,
        }


@tool
@protect(tool="get_customer_ticket", resource_type="customer", data_classification="restricted")
async def get_customer_ticket(display_id: int) -> dict[str, Any]:
    """Get full profile details for a customer by their display ID (restricted access)."""
    async with async_session_factory() as session:
        stmt = select(Customer).where(Customer.display_id == display_id)
        res = await session.execute(stmt)
        customer = res.scalar_one_or_none()
        if not customer:
            return {"found": False, "message": f"Customer #{display_id} not found."}
        return {
            "found": True,
            "display_id": customer.display_id,
            "name": customer.name,
            "email": customer.email,
            "phone": customer.phone,
            "address": customer.address,
            "account_status": customer.account_status,
        }


@tool
@protect(tool="get_orders_ticket", resource_type="order", data_classification="internal")
async def get_orders_ticket(display_id: int) -> dict[str, Any]:
    """Get order information by order display ID (e.g. 100001)."""
    async with async_session_factory() as session:
        stmt = select(Order).where(Order.display_id == display_id)
        res = await session.execute(stmt)
        order = res.scalar_one_or_none()
        if not order:
            return {"found": False, "message": f"Order #{display_id} not found."}
        return {
            "found": True,
            "display_id": order.display_id,
            "product": order.product,
            "price": float(order.price),
            "status": order.status,
            "is_return_requested": order.is_return_requested,
        }


@tool
@protect(tool="get_payment_ticket", resource_type="payment", data_classification="internal")
async def get_payment_ticket(order_display_id: int) -> dict[str, Any]:
    """Get payment transaction details associated with an order display ID."""
    async with async_session_factory() as session:
        stmt = (
            select(Payment)
            .join(Order, Payment.order_id == Order.id)
            .where(Order.display_id == order_display_id)
        )
        res = await session.execute(stmt)
        payment = res.scalar_one_or_none()
        if not payment:
            return {"found": False, "message": f"Payment for order #{order_display_id} not found."}
        return {
            "found": True,
            "display_id": payment.display_id,
            "amount": float(payment.amount),
            "method": payment.method,
            "card_last4": payment.card_last4,
            "card_brand": payment.card_brand,
            "status": payment.status,
        }


@tool
@protect(tool="request_refund_ticket", resource_type="payment", data_classification="internal")
async def request_refund_ticket(order_display_id: int, amount: float, reason: str) -> dict[str, Any]:
    """Request a refund for an order by order display ID."""
    async with async_session_factory() as session:
        stmt = select(Order).where(Order.display_id == order_display_id)
        res = await session.execute(stmt)
        order = res.scalar_one_or_none()
        if not order:
            return {"success": False, "message": f"Order #{order_display_id} not found."}

        refund_id = uuid.uuid4()
        # Find next display ID
        stmt_max = select(Refund.display_id).order_by(Refund.display_id.desc()).limit(1)
        max_id = await session.scalar(stmt_max) or 300000

        refund = Refund(
            id=refund_id,
            display_id=max_id + 1,
            order_id=order.id,
            amount=Decimal(str(amount)),
            reason=reason,
            status="pending",
        )
        session.add(refund)
        await session.commit()
        return {
            "success": True,
            "refund_display_id": refund.display_id,
            "order_display_id": order_display_id,
            "amount": amount,
            "status": "pending",
        }


@tool
@protect(tool="send_reply_ticket", resource_type="public", data_classification="internal")
async def send_reply_ticket(subject: str, body: str) -> dict[str, Any]:
    """Send a reply email to the original ticket sender. The reply-to address is
    determined by the system (SENDER_EMAIL env var) and cannot be overridden."""
    to_email = os.getenv("SENDER_EMAIL", "skanda.dell@gmail.com")
    return {
        "status": "sent",
        "to": to_email,
        "subject": subject,
        "body": body,
    }


@tool
@protect(tool="delete_customer_ticket", resource_type="customer", data_classification="restricted")
async def delete_customer_ticket(display_id: int) -> dict[str, Any]:
    """Delete a customer account permanently (restricted action)."""
    async with async_session_factory() as session:
        stmt = select(Customer).where(Customer.display_id == display_id)
        res = await session.execute(stmt)
        customer = res.scalar_one_or_none()
        if not customer:
            return {"success": False, "message": f"Customer #{display_id} not found."}
        await session.delete(customer)
        await session.commit()
        return {"success": True, "message": f"Customer #{display_id} deleted."}


ALL_TOOLS = [
    search_customer_ticket,
    get_customer_ticket,
    get_orders_ticket,
    get_payment_ticket,
    request_refund_ticket,
    send_reply_ticket,
    delete_customer_ticket,
]
