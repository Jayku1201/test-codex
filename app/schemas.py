"""Pydantic schemas for request and response validation."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field


def current_timestamp() -> str:
    """Return the current UTC timestamp in ISO 8601 format."""

    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


class HealthResponse(BaseModel):
    status: str


class CustomerBase(BaseModel):
    phone: Optional[str] = Field(default=None, max_length=50)
    company: Optional[str] = Field(default=None, max_length=200)
    status: Optional[str] = Field(default=None, max_length=50)
    notes: Optional[str] = Field(default=None, max_length=1000)


class CustomerCreate(CustomerBase):
    name: str = Field(..., min_length=1, max_length=200)
    email: EmailStr
    status: Optional[str] = Field(default="active", max_length=50)


class CustomerUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    email: Optional[EmailStr] = None
    phone: Optional[str] = Field(default=None, max_length=50)
    company: Optional[str] = Field(default=None, max_length=200)
    status: Optional[str] = Field(default=None, max_length=50)
    notes: Optional[str] = Field(default=None, max_length=1000)


class Customer(CustomerBase):
    id: int
    name: str
    email: EmailStr
    status: Optional[str]
    created_at: str
    updated_at: str

    model_config = ConfigDict(from_attributes=True)


class InteractionBase(BaseModel):
    interaction_type: str = Field(..., min_length=1, max_length=100)
    subject: Optional[str] = Field(default=None, max_length=200)
    notes: Optional[str] = Field(default=None, max_length=2000)
    occurred_at: Optional[str] = None


class InteractionCreate(InteractionBase):
    pass


class Interaction(InteractionBase):
    id: int
    customer_id: int
    occurred_at: str
    created_at: str

    model_config = ConfigDict(from_attributes=True)


class CustomerWithInteractions(Customer):
    interactions: List[Interaction] = Field(default_factory=list)
