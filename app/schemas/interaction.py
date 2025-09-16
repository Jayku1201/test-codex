"""Pydantic schemas for interaction resources."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.interaction import InteractionType


class InteractionBase(BaseModel):
    summary: str | None = None
    content: str | None = None


class InteractionCreate(InteractionBase):
    contact_id: int = Field(gt=0)
    type: InteractionType
    happened_at: datetime


class InteractionUpdate(InteractionBase):
    type: InteractionType | None = None
    happened_at: datetime | None = None


class InteractionRead(InteractionBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    contact_id: int
    type: InteractionType
    happened_at: datetime
    created_at: datetime
