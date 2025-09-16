"""Models for custom field definitions and values."""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum as SQLEnum,
    ForeignKey,
    JSON,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:  # pragma: no cover - circular import guard
    from app.models.contact import Contact


class FieldType(str, Enum):
    """Supported custom field data types."""

    TEXT = "text"
    NUMBER = "number"
    DATE = "date"
    EMAIL = "email"
    PHONE = "phone"
    SINGLE_SELECT = "single_select"
    MULTI_SELECT = "multi_select"
    BOOL = "bool"


class FieldDefinition(Base):
    """Administrative definition for custom contact fields."""

    __tablename__ = "field_definitions"

    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    label: Mapped[str] = mapped_column(String(255), nullable=False)
    type: Mapped[FieldType] = mapped_column(
        SQLEnum(FieldType, name="field_type"), nullable=False
    )
    options: Mapped[list[str] | None] = mapped_column(JSON)
    required: Mapped[bool] = mapped_column(Boolean(), nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False), server_default=func.now(), nullable=False
    )


class ContactFieldValue(Base):
    """Value assigned to a custom field for a specific contact."""

    __tablename__ = "contact_field_values"
    __table_args__ = (
        UniqueConstraint("contact_id", "field_key", name="uq_contact_field_key"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    contact_id: Mapped[int] = mapped_column(
        ForeignKey("contacts.id", ondelete="CASCADE"), nullable=False
    )
    field_key: Mapped[str] = mapped_column(String(100), nullable=False)
    value: Mapped[str | None] = mapped_column(Text())

    contact: Mapped["Contact"] = relationship(
        back_populates="custom_values", lazy="joined"
    )
