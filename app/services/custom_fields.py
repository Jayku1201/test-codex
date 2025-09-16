"""Helper utilities for validating and transforming custom field data."""
from __future__ import annotations

import json
import re
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any, Iterable

from pydantic import EmailStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ContactFieldValue, FieldDefinition, FieldType

PHONE_PATTERN = re.compile(r"^[+0-9().\- ]+$")


async def fetch_field_definitions(
    session: AsyncSession,
) -> dict[str, FieldDefinition]:
    """Load all field definitions keyed by their identifier."""

    result = await session.execute(select(FieldDefinition))
    definitions = result.scalars().all()
    return {definition.key: definition for definition in definitions}


def encode_field_value(definition: FieldDefinition, value: Any) -> str | None:
    """Validate and serialize a value for storage."""

    if value is None:
        if definition.required:
            msg = f"Field '{definition.key}' is required"
            raise ValueError(msg)
        return None

    match definition.type:
        case FieldType.TEXT:
            return str(value)
        case FieldType.NUMBER:
            return _encode_number(value)
        case FieldType.DATE:
            return _encode_date(value)
        case FieldType.EMAIL:
            return _encode_email(value)
        case FieldType.PHONE:
            return _encode_phone(value)
        case FieldType.SINGLE_SELECT:
            return _encode_single_select(definition, value)
        case FieldType.MULTI_SELECT:
            return _encode_multi_select(definition, value)
        case FieldType.BOOL:
            return _encode_bool(value)
    raise ValueError(f"Unsupported field type: {definition.type}")  # pragma: no cover


def decode_field_value(definition: FieldDefinition, stored: str | None) -> Any:
    """Convert a stored string value back into an appropriate Python type."""

    if stored is None:
        return None

    match definition.type:
        case FieldType.TEXT:
            return stored
        case FieldType.NUMBER:
            decimal_value = Decimal(stored)
            if decimal_value == decimal_value.to_integral_value():
                return int(decimal_value)
            return float(decimal_value)
        case FieldType.DATE:
            return stored
        case FieldType.EMAIL:
            return stored
        case FieldType.PHONE:
            return stored
        case FieldType.SINGLE_SELECT:
            return stored
        case FieldType.MULTI_SELECT:
            data = json.loads(stored)
            if not isinstance(data, list):  # pragma: no cover - defensive
                msg = "Stored multi-select values must be a list"
                raise ValueError(msg)
            return data
        case FieldType.BOOL:
            lowered = stored.strip().lower()
            if lowered not in {"true", "false"}:  # pragma: no cover
                msg = "Stored boolean value must be true or false"
                raise ValueError(msg)
            return lowered == "true"
    raise ValueError(f"Unsupported field type: {definition.type}")  # pragma: no cover


def prepare_custom_field_updates(
    definitions: dict[str, FieldDefinition],
    payload: dict[str, Any] | None,
    *,
    existing_values: dict[str, str | None] | None = None,
) -> dict[str, str | None]:
    """Validate incoming payload and return serialized updates."""

    existing_values = existing_values or {}
    payload = payload or {}
    updates: dict[str, str | None] = {}

    for key, raw_value in payload.items():
        definition = definitions.get(key)
        if definition is None:
            msg = f"Unknown custom field '{key}'"
            raise ValueError(msg)
        updates[key] = encode_field_value(definition, raw_value)

    merged: dict[str, str | None] = dict(existing_values)
    merged.update(updates)

    for key, definition in definitions.items():
        if not definition.required:
            continue
        value = merged.get(key)
        if value is None:
            msg = f"Field '{key}' is required"
            raise ValueError(msg)

    return updates


def ensure_definition_compatible_with_values(
    definition: FieldDefinition,
    values: Iterable[ContactFieldValue],
) -> None:
    """Ensure existing values remain valid after a definition change."""

    for value in values:
        try:
            decode_field_value(definition, value.value)
        except (ValueError, InvalidOperation, json.JSONDecodeError) as exc:
            msg = (
                "Existing value is incompatible with the updated field definition"
            )
            raise ValueError(msg) from exc

    if definition.required:
        for value in values:
            if value.value is None:
                msg = f"Field '{definition.key}' is required and cannot be empty"
                raise ValueError(msg)


def _encode_number(value: Any) -> str:
    try:
        if isinstance(value, Decimal):
            decimal_value = value
        elif isinstance(value, (int, float)):
            decimal_value = Decimal(str(value))
        elif isinstance(value, str):
            decimal_value = Decimal(value.strip())
        else:
            msg = "Number fields require numeric input"
            raise ValueError(msg)
    except (InvalidOperation, AttributeError) as exc:
        msg = "Number fields require numeric input"
        raise ValueError(msg) from exc
    return format(decimal_value.normalize(), "f")


def _encode_date(value: Any) -> str:
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, str):
        try:
            return date.fromisoformat(value).isoformat()
        except ValueError as exc:  # pragma: no cover - invalid iso format
            msg = "Date fields require ISO 8601 date strings"
            raise ValueError(msg) from exc
    msg = "Date fields require ISO 8601 date strings"
    raise ValueError(msg)


def _encode_email(value: Any) -> str:
    try:
        email = EmailStr(value)
    except ValueError as exc:  # pragma: no cover - invalid email
        msg = "Invalid email format"
        raise ValueError(msg) from exc
    return str(email)


def _encode_phone(value: Any) -> str:
    if not isinstance(value, str):
        msg = "Phone fields require string values"
        raise ValueError(msg)
    cleaned = value.strip()
    if not PHONE_PATTERN.fullmatch(cleaned):
        msg = "Invalid phone number format"
        raise ValueError(msg)
    return cleaned


def _encode_single_select(definition: FieldDefinition, value: Any) -> str:
    if not isinstance(value, str):
        msg = "Single select values must be strings"
        raise ValueError(msg)
    options = set(definition.options or [])
    if value not in options:
        msg = "Value must be one of the available options"
        raise ValueError(msg)
    return value


def _encode_multi_select(definition: FieldDefinition, value: Any) -> str:
    if not isinstance(value, (list, tuple)):
        msg = "Multi select values must be a list"
        raise ValueError(msg)
    options = set(definition.options or [])
    validated: list[str] = []
    for item in value:
        if not isinstance(item, str):
            msg = "Multi select values must be strings"
            raise ValueError(msg)
        if item not in options:
            msg = "Value must be one of the available options"
            raise ValueError(msg)
        if item not in validated:
            validated.append(item)
    return json.dumps(validated)


def _encode_bool(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "false"}:
            return lowered
    msg = "Boolean fields accept true/false"
    raise ValueError(msg)
