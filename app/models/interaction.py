"""Interaction model definition."""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Enum as SQLEnum, ForeignKey, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.contact import Contact


class InteractionType(str, Enum):
    """Permitted interaction categories."""

    MEETING = "meeting"
    CALL = "call"
    EMAIL = "email"
    OTHER = "other"


class Interaction(Base):
    """A recorded interaction for a contact."""

    __tablename__ = "interactions"

    id: Mapped[int] = mapped_column(primary_key=True)
    contact_id: Mapped[int] = mapped_column(
        ForeignKey("contacts.id", ondelete="CASCADE"), nullable=False
    )
    type: Mapped[InteractionType] = mapped_column(
        SQLEnum(InteractionType, name="interaction_type"), nullable=False
    )
    summary: Mapped[str | None] = mapped_column(Text())
    content: Mapped[str | None] = mapped_column(Text())
    happened_at: Mapped[datetime] = mapped_column(DateTime(timezone=False), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False), server_default=func.now(), nullable=False
    )

    contact: Mapped["Contact"] = relationship(back_populates="interactions")
