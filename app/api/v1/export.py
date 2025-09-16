"""Export endpoints for contact data."""
from __future__ import annotations

import csv
import io
from datetime import datetime
from typing import Any, Sequence

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.models import Contact, ContactFieldValue, FieldDefinition, Interaction
from app.services.custom_fields import decode_field_value, fetch_field_definitions


router = APIRouter(prefix="/export", tags=["export"])

CORE_COLUMNS = [
    "name",
    "company",
    "title",
    "email",
    "phone",
    "tags",
    "note",
    "last_interacted_at",
]


@router.get("/contacts.csv")
async def export_contacts_csv(
    tags: str | None = Query(None, description="Comma separated list of tags to match"),
    from_: str | None = Query(None, alias="from"),
    to: str | None = None,
    include_private: bool = Query(False),
    session: AsyncSession = Depends(get_session),
) -> Response:
    """Export contacts with custom fields to CSV."""

    definitions = await fetch_field_definitions(session)
    custom_keys = sorted(definitions.keys())

    tag_filters = _parse_tags(tags)
    from_dt = _parse_datetime(from_)
    to_dt = _parse_datetime(to)

    stmt = select(Contact)
    if from_dt:
        stmt = stmt.where(Contact.last_interacted_at >= from_dt)
    if to_dt:
        stmt = stmt.where(Contact.last_interacted_at <= to_dt)

    result = await session.execute(stmt.order_by(Contact.name))
    contacts = result.scalars().all()

    if tag_filters:
        contacts = [
            contact
            for contact in contacts
            if contact.tags and all(tag in contact.tags for tag in tag_filters)
        ]

    contact_ids = [contact.id for contact in contacts]
    custom_values = await _load_custom_values(session, contact_ids)
    latest_interactions = await _load_latest_interactions(session, contact_ids)

    output = io.StringIO()
    header = [*CORE_COLUMNS, *(f"custom.{key}" for key in custom_keys), "last_interaction_summary"]
    writer = csv.DictWriter(output, fieldnames=header)
    writer.writeheader()

    for contact in contacts:
        row = _serialize_contact_row(
            contact,
            definitions,
            custom_values.get(contact.id, {}),
            latest_interactions.get(contact.id),
            include_private=include_private,
            custom_keys=custom_keys,
        )
        writer.writerow(row)

    csv_content = output.getvalue()
    filename = "contacts.csv"
    return Response(
        csv_content,
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


def _parse_tags(value: str | None) -> list[str]:
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    cleaned = value.strip()
    if not cleaned:
        return None
    try:
        return datetime.fromisoformat(cleaned)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="Invalid date format") from exc


async def _load_custom_values(
    session: AsyncSession, contact_ids: Sequence[int]
) -> dict[int, dict[str, str | None]]:
    if not contact_ids:
        return {}
    stmt = select(ContactFieldValue).where(ContactFieldValue.contact_id.in_(contact_ids))
    result = await session.execute(stmt)
    values: dict[int, dict[str, str | None]] = {}
    for row in result.scalars():
        values.setdefault(row.contact_id, {})[row.field_key] = row.value
    return values


async def _load_latest_interactions(
    session: AsyncSession, contact_ids: Sequence[int]
) -> dict[int, Interaction]:
    if not contact_ids:
        return {}
    stmt = (
        select(Interaction)
        .where(Interaction.contact_id.in_(contact_ids))
        .order_by(Interaction.contact_id, desc(Interaction.happened_at), Interaction.id.desc())
    )
    result = await session.execute(stmt)
    latest: dict[int, Interaction] = {}
    for interaction in result.scalars():
        if interaction.contact_id not in latest:
            latest[interaction.contact_id] = interaction
    return latest


def _serialize_contact_row(
    contact: Contact,
    definitions: dict[str, FieldDefinition],
    stored_values: dict[str, str | None],
    interaction: Interaction | None,
    *,
    include_private: bool,
    custom_keys: list[str],
) -> dict[str, Any]:
    row: dict[str, Any] = {
        "name": contact.name,
        "company": contact.company or "",
        "title": contact.title or "",
        "email": contact.email if include_private else "",
        "phone": contact.phone if include_private else "",
        "tags": ",".join(contact.tags or []),
        "note": contact.note or "",
        "last_interacted_at": contact.last_interacted_at.isoformat()
        if contact.last_interacted_at
        else "",
    }

    for key in custom_keys:
        stored = stored_values.get(key)
        definition = definitions.get(key)
        value: str = ""
        if definition is not None:
            try:
                decoded = decode_field_value(definition, stored)
                if isinstance(decoded, list):
                    value = ",".join(decoded)
                elif isinstance(decoded, bool):
                    value = "true" if decoded else "false"
                elif decoded is not None:
                    value = str(decoded)
            except ValueError:  # pragma: no cover - defensive
                value = stored or ""
        row[f"custom.{key}"] = value

    if interaction is not None:
        summary_parts = [interaction.happened_at.isoformat(), interaction.type.value]
        if interaction.summary:
            summary_parts.append(interaction.summary)
        row["last_interaction_summary"] = " ".join(summary_parts)
    else:
        row["last_interaction_summary"] = ""

    return row

