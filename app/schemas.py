"""Pydantic schemas for the CRM API."""
from __future__ import annotations

from datetime import date, datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .models import TaskStatus


class InteractionBase(BaseModel):
    subject: str
    interaction_type: str = Field(default="note", max_length=50)
    medium: Optional[str] = Field(default=None, max_length=50)
    notes: Optional[str] = None
    occurred_at: Optional[datetime] = None


class InteractionCreate(InteractionBase):
    pass


class InteractionUpdate(BaseModel):
    subject: Optional[str] = None
    interaction_type: Optional[str] = Field(default=None, max_length=50)
    medium: Optional[str] = Field(default=None, max_length=50)
    notes: Optional[str] = None
    occurred_at: Optional[datetime] = None


class Interaction(InteractionBase):
    id: int
    customer_id: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class OpportunityBase(BaseModel):
    name: str
    description: Optional[str] = None
    value: float = 0.0
    status: str = Field(default="prospecting", max_length=50)
    probability: Optional[int] = Field(default=None, ge=0, le=100)
    expected_close_date: Optional[date] = None


class OpportunityCreate(OpportunityBase):
    pass


class OpportunityUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    value: Optional[float] = None
    status: Optional[str] = Field(default=None, max_length=50)
    probability: Optional[int] = Field(default=None, ge=0, le=100)
    expected_close_date: Optional[date] = None


class Opportunity(OpportunityBase):
    id: int
    customer_id: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class TaskBase(BaseModel):
    title: str
    description: Optional[str] = None
    due_date: Optional[date] = None
    status: TaskStatus = TaskStatus.TODO


class TaskCreate(TaskBase):
    pass


class TaskUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    due_date: Optional[date] = None
    status: Optional[TaskStatus] = None


class Task(TaskBase):
    id: int
    customer_id: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class CustomerBase(BaseModel):
    name: str
    email: str
    phone: Optional[str] = None
    company: Optional[str] = None
    status: str = Field(default="lead", max_length=50)
    tags: List[str] = Field(default_factory=list)
    notes: Optional[str] = None

    @field_validator("tags", mode="before")
    @classmethod
    def parse_tags(cls, value: object) -> List[str]:
        if value is None or value == "":
            return []
        if isinstance(value, str):
            return [tag.strip() for tag in value.split(",") if tag.strip()]
        return list(value)


class CustomerCreate(CustomerBase):
    pass


class CustomerUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    company: Optional[str] = None
    status: Optional[str] = Field(default=None, max_length=50)
    tags: Optional[List[str]] = None
    notes: Optional[str] = None


class Customer(CustomerBase):
    id: int
    created_at: datetime
    updated_at: datetime
    interactions: List[Interaction] = Field(default_factory=list)
    opportunities: List[Opportunity] = Field(default_factory=list)
    tasks: List[Task] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


class CustomerSummary(BaseModel):
    id: int
    name: str
    email: str
    status: str
    company: Optional[str]
    tags: List[str] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)

    @field_validator("tags", mode="before")
    @classmethod
    def parse_tags(cls, value: object) -> List[str]:
        if value is None or value == "":
            return []
        if isinstance(value, str):
            return [tag.strip() for tag in value.split(",") if tag.strip()]
        return list(value)


class AnalyticsSnapshot(BaseModel):
    total_customers: int
    leads: int
    active_opportunities: int
    won_opportunities: int
    overdue_tasks: int
