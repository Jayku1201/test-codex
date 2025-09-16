"""Reminder model definition."""
from __future__ import annotations

from datetime import date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Text, func, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.contact import Contact


class Reminder(Base):
    """A reminder associated with a contact."""

    __tablename__ = "reminders"

    id: Mapped[int] = mapped_column(primary_key=True)
    contact_id: Mapped[int] = mapped_column(
        ForeignKey("contacts.id", ondelete="CASCADE"), nullable=False
    )
    remind_at: Mapped[date] = mapped_column(Date(), nullable=False)
    content: Mapped[str] = mapped_column(Text(), nullable=False)
    done: Mapped[bool] = mapped_column(
        Boolean(), default=False, server_default=text("0"), nullable=False
    )
    sync_google: Mapped[bool] = mapped_column(
        Boolean(), default=False, server_default=text("0"), nullable=False
    )
    google_event_id: Mapped[str | None] = mapped_column(Text(), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False), server_default=func.now(), nullable=False
    )

    contact: Mapped["Contact"] = relationship(back_populates="reminders")
