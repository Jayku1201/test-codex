"""Pydantic schemas for the personal contact management system."""

from .contact import ContactCreate, ContactRead, ContactUpdate
from .field import FieldDefinitionCreate, FieldDefinitionRead, FieldDefinitionUpdate
from .interaction import InteractionCreate, InteractionRead, InteractionType, InteractionUpdate
from .reminder import ReminderCreate, ReminderRead, ReminderUpdate

__all__ = [
    "ContactCreate",
    "ContactRead",
    "ContactUpdate",
    "FieldDefinitionCreate",
    "FieldDefinitionRead",
    "FieldDefinitionUpdate",
    "InteractionCreate",
    "InteractionRead",
    "InteractionType",
    "InteractionUpdate",
    "ReminderCreate",
    "ReminderRead",
    "ReminderUpdate",
]
