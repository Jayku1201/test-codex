"""Utilities for importing contacts from CSV payloads."""
from __future__ import annotations

import csv
import io
import re
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Iterable

from fastapi import HTTPException, status
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Contact, ContactFieldValue, FieldDefinition, FieldType
from app.schemas import ContactCreate
from app.services.custom_fields import encode_field_value

CUSTOM_PREFIX = "custom."
CUSTOM_KEY_PATTERN = re.compile(r"[A-Za-z0-9_]+")


class ImportRowError(Exception):
    """Raised when a row cannot be processed."""


@dataclass
class ParsedRow:
    row_index: int
    original: dict[str, Any]
    sample: dict[str, Any]
    base_data: dict[str, Any]
    custom_values: dict[str, str | None]
    last_interacted_at: datetime | None
    existing_contact: Contact | None


@dataclass
class RowError:
    row_index: int
    message: str
    original: dict[str, Any]


class ContactImportProcessor:
    """Parse and import contacts from CSV files."""

    def __init__(
        self,
        *,
        session: AsyncSession,
        mode: str,
        auto_create_fields: bool,
        dry_run: bool,
    ) -> None:
        if mode not in {"create_only", "upsert"}:
            msg = "mode must be either create_only or upsert"
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=msg)

        self.session = session
        self.mode = mode
        self.auto_create_fields = auto_create_fields
        self.dry_run = dry_run
        self.definitions: dict[str, FieldDefinition] = {}
    async def run(
        self, file_bytes: bytes
    ) -> tuple[list[str], list[ParsedRow], list[RowError]]:
        """Parse the incoming CSV and return the header, parsed rows, and errors."""

        reader, header = self._build_reader(file_bytes)
        raw_rows = list(reader)
        self.definitions = await self._fetch_definitions()

        emails: set[str] = set()
        phones: set[str] = set()
        for raw in raw_rows:
            email = (raw.get("email") or "").strip()
            if email:
                emails.add(email)
            phone = (raw.get("phone") or "").strip()
            if phone:
                phones.add(phone)

        existing_lookup = await self._fetch_existing_contacts(emails, phones)
        existing_custom = await self._fetch_existing_custom_values(existing_lookup.values())

        parsed_rows: list[ParsedRow] = []
        errors: list[RowError] = []

        for row_number, raw_row in enumerate(raw_rows, start=1):
            row_copy = {key: raw_row.get(key) for key in header}
            try:
                parsed = await self._parse_row(
                    row_index=row_number,
                    original=row_copy,
                    header=header,
                    existing_lookup=existing_lookup,
                    existing_custom=existing_custom,
                )
            except ImportRowError as exc:
                errors.append(RowError(row_number, str(exc), row_copy))
                continue
            parsed_rows.append(parsed)

        return header, parsed_rows, errors

    async def _parse_row(
        self,
        *,
        row_index: int,
        original: dict[str, Any],
        header: list[str],
        existing_lookup: dict[str, Contact],
        existing_custom: dict[int, dict[str, str | None]],
    ) -> ParsedRow:
        name = (original.get("name") or "").strip()
        if not name:
            msg = "name is required"
            raise ImportRowError(msg)

        base_payload: dict[str, Any] = {
            "name": name,
            "company": self._clean_optional(original.get("company")),
            "title": self._clean_optional(original.get("title")),
            "email": self._clean_optional(original.get("email")),
            "phone": self._clean_optional(original.get("phone")),
            "tags": self._parse_tags(original.get("tags")),
            "note": self._clean_optional(original.get("note")),
        }

        last_interacted_at = self._parse_datetime(original.get("last_interacted_at"))

        contact_model = ContactCreate.model_validate({**base_payload, "custom": None})
        base_data = contact_model.model_dump(exclude={"custom"})

        identifier = self._row_identifier(base_data)
        existing_contact = existing_lookup.get(identifier)
        existing_map = (
            existing_custom.get(existing_contact.id, {})
            if existing_contact is not None
            else {}
        )

        custom_values = self._prepare_custom_values(
            original=original,
            header=header,
            existing_values=existing_map,
        )

        sample_payload = {
            **base_data,
            "custom": self._sample_custom(original, header),
            "last_interacted_at": last_interacted_at.isoformat() if last_interacted_at else None,
        }

        return ParsedRow(
            row_index=row_index,
            original=original,
            sample=sample_payload,
            base_data=base_data,
            custom_values=custom_values,
            last_interacted_at=last_interacted_at,
            existing_contact=existing_contact,
        )

    async def _fetch_definitions(self) -> dict[str, FieldDefinition]:
        result = await self.session.execute(select(FieldDefinition))
        definitions = {definition.key: definition for definition in result.scalars()}
        return definitions

    async def _fetch_existing_contacts(
        self, emails: Iterable[str], phones: Iterable[str]
    ) -> dict[str, Contact]:
        identifiers: dict[str, Contact] = {}
        clauses = []
        emails = list(emails)
        phones = list(phones)
        if emails:
            clauses.append(Contact.email.in_(emails))
        if phones:
            clauses.append(Contact.phone.in_(phones))

        if not clauses:
            return {}

        stmt = select(Contact).where(or_(*clauses))
        result = await self.session.execute(stmt)
        for contact in result.scalars():
            if contact.email:
                identifiers[f"email:{contact.email}"] = contact
            if contact.phone:
                identifiers[f"phone:{contact.phone}"] = contact
        return identifiers

    async def _fetch_existing_custom_values(
        self, contacts: Iterable[Contact]
    ) -> dict[int, dict[str, str | None]]:
        contact_ids = [contact.id for contact in contacts]
        if not contact_ids:
            return {}
        stmt = select(ContactFieldValue).where(ContactFieldValue.contact_id.in_(contact_ids))
        result = await self.session.execute(stmt)
        custom_map: dict[int, dict[str, str | None]] = {}
        for value in result.scalars():
            custom_map.setdefault(value.contact_id, {})[value.field_key] = value.value
        return custom_map

    def _prepare_custom_values(
        self,
        *,
        original: dict[str, Any],
        header: list[str],
        existing_values: dict[str, str | None],
    ) -> dict[str, str | None]:
        updates: dict[str, str | None] = {}

        for column in header:
            if not column.startswith(CUSTOM_PREFIX):
                continue
            key = column[len(CUSTOM_PREFIX) :]
            raw_value = original.get(column)
            definition = self._ensure_definition(key)

            if raw_value is None or not str(raw_value).strip():
                updates[key] = None
                continue

            if definition.type == FieldType.MULTI_SELECT:
                raw_items = [item.strip() for item in str(raw_value).split(",") if item.strip()]
                value: Any = raw_items
            else:
                value = raw_value

            try:
                encoded = encode_field_value(definition, value)
            except ValueError as exc:
                raise ImportRowError(str(exc)) from exc
            updates[key] = encoded

        merged = dict(existing_values)
        merged.update(updates)

        for key, definition in self.definitions.items():
            if not definition.required:
                continue
            if merged.get(key) is None:
                raise ImportRowError(f"Field '{key}' is required")

        return updates

    def _ensure_definition(self, key: str) -> FieldDefinition:
        definition = self.definitions.get(key)
        if definition is not None:
            return definition

        if not self.auto_create_fields:
            msg = f"Unknown custom field '{key}'"
            raise ImportRowError(msg)

        if not CUSTOM_KEY_PATTERN.fullmatch(key):
            msg = "Key must match pattern [A-Za-z0-9_]"
            raise ImportRowError(msg)

        definition = FieldDefinition(key=key, label=key, type=FieldType.TEXT)
        self.definitions[key] = definition
        if not self.dry_run:
            self.session.add(definition)
        return definition

    def _sample_custom(self, original: dict[str, Any], header: list[str]) -> dict[str, Any]:
        custom: dict[str, Any] = {}
        for column in header:
            if not column.startswith(CUSTOM_PREFIX):
                continue
            custom[column[len(CUSTOM_PREFIX) :]] = original.get(column)
        return custom

    def _build_reader(self, file_bytes: bytes) -> tuple[csv.DictReader, list[str]]:
        try:
            text = file_bytes.decode("utf-8-sig")
        except UnicodeDecodeError as exc:  # pragma: no cover - defensive
            msg = "Uploaded file must be UTF-8 encoded"
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg) from exc

        stream = io.StringIO(text)
        reader = csv.DictReader(stream)
        raw_header = reader.fieldnames
        if raw_header is None:
            msg = "CSV file must include a header row"
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg)
        header = list(raw_header)
        required_columns = {
            "name",
            "company",
            "title",
            "email",
            "phone",
            "tags",
            "note",
            "last_interacted_at",
        }
        missing = required_columns - set(header)
        if missing:
            msg = f"Missing required columns: {', '.join(sorted(missing))}"
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg)
        return reader, header

    def _parse_tags(self, value: Any) -> list[str] | None:
        if value is None:
            return None
        cleaned = [item.strip() for item in str(value).split(",") if item.strip()]
        return cleaned or None

    def _parse_datetime(self, value: Any) -> datetime | None:
        if value is None:
            return None
        cleaned = str(value).strip()
        if not cleaned:
            return None
        try:
            return datetime.fromisoformat(cleaned)
        except ValueError as exc:
            raise ImportRowError("Invalid last_interacted_at format") from exc

    def _clean_optional(self, value: Any) -> str | None:
        if value is None:
            return None
        cleaned = str(value).strip()
        return cleaned or None

    def _row_identifier(self, base_data: dict[str, Any]) -> str:
        email = base_data.get("email")
        if email:
            return f"email:{email}"
        phone = base_data.get("phone")
        if phone:
            return f"phone:{phone}"
        return str(uuid.uuid4())

