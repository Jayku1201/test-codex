"""Pydantic schemas for contact resources."""
from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


Tag = Annotated[str, Field(min_length=1, max_length=30)]
PhoneNumber = Annotated[
    str, Field(min_length=7, max_length=32, pattern=r"^[+0-9().\- ]+$")
]


class ContactBase(BaseModel):
    company: str | None = None
    title: str | None = None
    email: EmailStr | None = None
    phone: PhoneNumber | None = None
    tags: list[Tag] | None = Field(default=None, max_length=20)
    note: str | None = None

    @field_validator("tags")
    @classmethod
    def validate_tags(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        unique_tags: list[str] = []
        for tag in value:
            cleaned = tag.strip()
            if not cleaned:
                msg = "Tags must not be empty"
                raise ValueError(msg)
            if cleaned not in unique_tags:
                unique_tags.append(cleaned)
        return unique_tags


class ContactCustomPayload(BaseModel):
    custom: dict[str, Any] | None = None


class ContactCreate(ContactBase, ContactCustomPayload):
    name: Annotated[str, Field(min_length=1, max_length=60)]


class ContactUpdate(ContactBase, ContactCustomPayload):
    name: Annotated[str, Field(min_length=1, max_length=60)] | None = None


class ContactRead(ContactBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    last_interacted_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
    custom: dict[str, Any] = Field(default_factory=dict)
