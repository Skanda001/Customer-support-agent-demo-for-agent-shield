import uuid
from datetime import datetime, timezone
from sqlalchemy import Boolean, DateTime, Integer, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from db.base import Base


class Ticket(Base):
    __tablename__ = "tickets_ticket_demo"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    display_id: Mapped[int] = mapped_column(
        Integer, unique=True, index=True, nullable=False
    )
    sender_email: Mapped[str] = mapped_column(Text, nullable=False)
    recipient_email: Mapped[str] = mapped_column(Text, nullable=False)
    subject: Mapped[str] = mapped_column(Text, nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(Text, nullable=False)
    is_malicious: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    attack_strength: Mapped[str] = mapped_column(
        Text, default="none", nullable=False
    )
    generated_by: Mapped[str] = mapped_column(
        Text, default="llm", nullable=False
    )
    status: Mapped[str] = mapped_column(
        Text, default="pending", nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    outbound_emails = relationship("OutboundEmail", back_populates="ticket", cascade="all, delete-orphan")
