"""initial_schema

Revision ID: 001_initial
Revises: 
Create Date: 2026-10-02 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. customers_ticket_demo
    op.create_table(
        "customers_ticket_demo",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("display_id", sa.Integer(), nullable=False, unique=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("email", sa.Text(), nullable=False, unique=True),
        sa.Column("phone", sa.Text(), nullable=True),
        sa.Column("address", sa.Text(), nullable=True),
        sa.Column("account_status", sa.String(length=50), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_customers_ticket_demo_display_id", "customers_ticket_demo", ["display_id"])
    op.create_index("ix_customers_ticket_demo_email", "customers_ticket_demo", ["email"])
    op.execute("ALTER TABLE customers_ticket_demo DISABLE ROW LEVEL SECURITY")

    # 2. orders_ticket_demo
    op.create_table(
        "orders_ticket_demo",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("display_id", sa.Integer(), nullable=False, unique=True),
        sa.Column("customer_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("customers_ticket_demo.id", ondelete="CASCADE"), nullable=False),
        sa.Column("product", sa.Text(), nullable=False),
        sa.Column("price", sa.Numeric(10, 2), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default="delivered"),
        sa.Column("is_return_requested", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_orders_ticket_demo_display_id", "orders_ticket_demo", ["display_id"])
    op.create_index("ix_orders_ticket_demo_customer_id", "orders_ticket_demo", ["customer_id"])
    op.execute("ALTER TABLE orders_ticket_demo DISABLE ROW LEVEL SECURITY")

    # 3. payments_ticket_demo
    op.create_table(
        "payments_ticket_demo",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("display_id", sa.Integer(), nullable=False, unique=True),
        sa.Column("customer_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("customers_ticket_demo.id", ondelete="CASCADE"), nullable=False),
        sa.Column("order_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("orders_ticket_demo.id", ondelete="CASCADE"), nullable=False),
        sa.Column("amount", sa.Numeric(10, 2), nullable=False),
        sa.Column("method", sa.Text(), nullable=False, server_default="credit_card"),
        sa.Column("card_last4", sa.Text(), nullable=True),
        sa.Column("card_brand", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False, server_default="success"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_payments_ticket_demo_display_id", "payments_ticket_demo", ["display_id"])
    op.create_index("ix_payments_ticket_demo_customer_id", "payments_ticket_demo", ["customer_id"])
    op.create_index("ix_payments_ticket_demo_order_id", "payments_ticket_demo", ["order_id"])
    op.execute("ALTER TABLE payments_ticket_demo DISABLE ROW LEVEL SECURITY")

    # 4. refunds_ticket_demo
    op.create_table(
        "refunds_ticket_demo",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("display_id", sa.Integer(), nullable=False, unique=True),
        sa.Column("order_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("orders_ticket_demo.id", ondelete="CASCADE"), nullable=False),
        sa.Column("amount", sa.Numeric(10, 2), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default="pending"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_refunds_ticket_demo_display_id", "refunds_ticket_demo", ["display_id"])
    op.create_index("ix_refunds_ticket_demo_order_id", "refunds_ticket_demo", ["order_id"])
    op.execute("ALTER TABLE refunds_ticket_demo DISABLE ROW LEVEL SECURITY")

    # 5. tickets_ticket_demo
    op.create_table(
        "tickets_ticket_demo",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("display_id", sa.Integer(), nullable=False, unique=True),
        sa.Column("sender_email", sa.Text(), nullable=False),
        sa.Column("recipient_email", sa.Text(), nullable=False),
        sa.Column("subject", sa.Text(), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("category", sa.Text(), nullable=False),
        sa.Column("is_malicious", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("attack_strength", sa.Text(), nullable=False, server_default="none"),
        sa.Column("generated_by", sa.Text(), nullable=False, server_default="llm"),
        sa.Column("status", sa.Text(), nullable=False, server_default="pending"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_tickets_ticket_demo_display_id", "tickets_ticket_demo", ["display_id"])
    op.create_index("ix_tickets_ticket_demo_status", "tickets_ticket_demo", ["status"])
    op.execute("ALTER TABLE tickets_ticket_demo DISABLE ROW LEVEL SECURITY")

    # 6. outbound_emails_ticket_demo
    op.create_table(
        "outbound_emails_ticket_demo",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("ticket_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tickets_ticket_demo.id", ondelete="CASCADE"), nullable=True),
        sa.Column("from_email", sa.Text(), nullable=False),
        sa.Column("to_email", sa.Text(), nullable=False),
        sa.Column("subject", sa.Text(), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("delivery_mode", sa.Text(), nullable=False, server_default="mock"),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_outbound_emails_ticket_demo_ticket_id", "outbound_emails_ticket_demo", ["ticket_id"])
    op.execute("ALTER TABLE outbound_emails_ticket_demo DISABLE ROW LEVEL SECURITY")


def downgrade() -> None:
    op.drop_table("outbound_emails_ticket_demo")
    op.drop_table("tickets_ticket_demo")
    op.drop_table("refunds_ticket_demo")
    op.drop_table("payments_ticket_demo")
    op.drop_table("orders_ticket_demo")
    op.drop_table("customers_ticket_demo")
