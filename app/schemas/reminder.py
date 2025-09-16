"""Pydantic schemas for reminder resources."""
from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field


class ReminderBase(BaseModel):
    content: str = Field(min_length=1)
    done: bool = False
    sync_google: bool = False


class ReminderCreate(ReminderBase):
    contact_id: int = Field(gt=0)
    remind_at: date


class ReminderUpdate(BaseModel):
    remind_at: date | None = None
    content: str | None = Field(default=None, min_length=1)
    done: bool | None = None
    sync_google: bool | None = None


class ReminderRead(ReminderBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    contact_id: int
    remind_at: date
    created_at: datetime
    google_event_id: str | None = None
