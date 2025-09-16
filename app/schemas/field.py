"""Pydantic schemas for custom field definitions."""
from __future__ import annotations

import re
from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models.field import FieldType

KeyPattern = Annotated[str, Field(min_length=1, max_length=100)]


class FieldDefinitionBase(BaseModel):
    label: Annotated[str, Field(min_length=1, max_length=255)]
    type: FieldType
    options: list[str] | None = None
    required: bool = False

    @field_validator("options")
    @classmethod
    def validate_options_list(cls, options: list[str] | None) -> list[str] | None:
        if options is None:
            return None
        cleaned: list[str] = []
        for option in options:
            if not isinstance(option, str):  # pragma: no cover - defensive
                msg = "Options must be strings"
                raise ValueError(msg)
            normalized = option.strip()
            if not normalized:
                msg = "Options must not be empty"
                raise ValueError(msg)
            if normalized not in cleaned:
                cleaned.append(normalized)
        return cleaned

    @model_validator(mode="after")
    def validate_options_for_type(self) -> "FieldDefinitionBase":
        if self.type in {FieldType.SINGLE_SELECT, FieldType.MULTI_SELECT}:
            if not self.options:
                msg = "Options are required for select fields"
                raise ValueError(msg)
        else:
            if self.options is not None:
                msg = "Options are only allowed for select fields"
                raise ValueError(msg)
        return self


class FieldDefinitionCreate(FieldDefinitionBase):
    key: KeyPattern

    @field_validator("key")
    @classmethod
    def validate_key(cls, value: str) -> str:
        if not re.fullmatch(r"[A-Za-z0-9_]+", value):
            msg = "Key must match pattern [A-Za-z0-9_]"
            raise ValueError(msg)
        return value


class FieldDefinitionUpdate(FieldDefinitionBase):
    key: KeyPattern | None = None

    @field_validator("key")
    @classmethod
    def validate_optional_key(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if not re.fullmatch(r"[A-Za-z0-9_]+", value):
            msg = "Key must match pattern [A-Za-z0-9_]"
            raise ValueError(msg)
        return value


class FieldDefinitionRead(FieldDefinitionBase):
    model_config = ConfigDict(from_attributes=True)

    key: str
    id: int
    created_at: datetime
