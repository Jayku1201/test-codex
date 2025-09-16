"""Contacts API routes."""
from __future__ import annotations

from datetime import datetime

from typing import Sequence

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.common import data_response
from app.core.db import get_session
from app.models import Contact, ContactFieldValue, FieldDefinition
from app.schemas import ContactCreate, ContactRead, ContactUpdate
from app.services.custom_fields import (
    decode_field_value,
    fetch_field_definitions,
    prepare_custom_field_updates,
)


router = APIRouter(prefix="/contacts", tags=["contacts"])


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_contact(
    payload: ContactCreate, session: AsyncSession = Depends(get_session)
) -> dict[str, ContactRead]:
    """Create a new contact."""

    definitions = await fetch_field_definitions(session)
    try:
        custom_updates = prepare_custom_field_updates(
            definitions, payload.custom
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc

    contact_data = payload.model_dump(exclude={"custom"})
    contact = Contact(**contact_data)
    session.add(contact)

    try:
        await session.flush()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Contact with the same email or phone already exists",
        ) from exc

    for key, encoded in custom_updates.items():
        session.add(
            ContactFieldValue(contact_id=contact.id, field_key=key, value=encoded)
        )

    try:
        await session.commit()
    except IntegrityError as exc:  # pragma: no cover - defensive but tested via API
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Contact with the same email or phone already exists",
        ) from exc

    await session.refresh(contact)
    custom_value_map = await _load_custom_values(session, [contact.id])
    contact_read = _serialize_contact(
        contact, definitions, custom_value_map.get(contact.id, {})
    )
    return data_response(contact_read)


@router.get("")
async def list_contacts(
    keyword: str | None = None,
    tag: str | None = None,
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    last_interacted_before: datetime | None = Query(None),
    last_interacted_after: datetime | None = Query(None, alias="after"),
    session: AsyncSession = Depends(get_session),
) -> dict[str, list[ContactRead]]:
    """List contacts with optional filtering and pagination."""

    stmt = select(Contact)
    if keyword:
        lowered = f"%{keyword.lower()}%"
        stmt = stmt.where(
            or_(
                func.lower(Contact.name).like(lowered),
                func.lower(Contact.company).like(lowered),
                func.lower(Contact.title).like(lowered),
                func.lower(Contact.email).like(lowered),
                func.lower(Contact.phone).like(lowered),
                func.lower(Contact.note).like(lowered),
            )
        )
    if last_interacted_before is not None:
        stmt = stmt.where(Contact.last_interacted_at.is_not(None)).where(
            Contact.last_interacted_at < last_interacted_before
        )
    if last_interacted_after is not None:
        stmt = stmt.where(Contact.last_interacted_at.is_not(None)).where(
            Contact.last_interacted_at > last_interacted_after
        )

    offset = (page - 1) * size
    stmt = stmt.order_by(Contact.name)
    result = await session.execute(stmt)
    contacts = result.scalars().all()
    if tag:
        contacts = [contact for contact in contacts if contact.tags and tag in contact.tags]

    start = offset
    end = offset + size
    page_contacts = contacts[start:end]
    definitions = await fetch_field_definitions(session)
    custom_values = await _load_custom_values(session, [c.id for c in page_contacts])
    payload = [
        _serialize_contact(contact, definitions, custom_values.get(contact.id, {}))
        for contact in page_contacts
    ]
    return data_response(payload)


@router.get("/{contact_id}")
async def retrieve_contact(
    contact_id: int, session: AsyncSession = Depends(get_session)
) -> dict[str, ContactRead]:
    """Retrieve a single contact by identifier."""

    contact = await _get_contact_or_404(session, contact_id)
    definitions = await fetch_field_definitions(session)
    custom_values = await _load_custom_values(session, [contact.id])
    return data_response(
        _serialize_contact(contact, definitions, custom_values.get(contact.id, {}))
    )


@router.put("/{contact_id}")
async def update_contact(
    contact_id: int,
    payload: ContactUpdate,
    session: AsyncSession = Depends(get_session),
) -> dict[str, ContactRead]:
    """Update the provided contact."""

    contact = await _get_contact_or_404(session, contact_id)
    definitions = await fetch_field_definitions(session)

    base_updates = payload.model_dump(exclude_unset=True, exclude={"custom"})
    for field, value in base_updates.items():
        setattr(contact, field, value)

    existing_values_result = await session.execute(
        select(ContactFieldValue).where(ContactFieldValue.contact_id == contact.id)
    )
    existing_rows = existing_values_result.scalars().all()
    existing_map = {row.field_key: row for row in existing_rows}
    try:
        custom_updates = prepare_custom_field_updates(
            definitions,
            payload.custom,
            existing_values={key: row.value for key, row in existing_map.items()},
        )
    except ValueError as exc:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc

    for key, encoded in custom_updates.items():
        if key in existing_map:
            existing_map[key].value = encoded
        else:
            session.add(
                ContactFieldValue(contact_id=contact.id, field_key=key, value=encoded)
            )

    try:
        await session.commit()
    except IntegrityError as exc:  # pragma: no cover - defensive but exercised
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Contact with the same email or phone already exists",
        ) from exc
    await session.refresh(contact)
    custom_value_map = await _load_custom_values(session, [contact.id])
    contact_read = _serialize_contact(
        contact, definitions, custom_value_map.get(contact.id, {})
    )
    return data_response(contact_read)


@router.delete("/{contact_id}")
async def delete_contact(
    contact_id: int, session: AsyncSession = Depends(get_session)
) -> dict[str, dict[str, bool]]:
    """Delete the specified contact."""

    contact = await _get_contact_or_404(session, contact_id)
    await session.delete(contact)
    await session.commit()
    return data_response({"deleted": True})


async def _get_contact_or_404(
    session: AsyncSession, contact_id: int
) -> Contact:
    contact = await session.get(Contact, contact_id)
    if contact is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contact not found")
    return contact


async def _load_custom_values(
    session: AsyncSession, contact_ids: Sequence[int]
) -> dict[int, dict[str, str | None]]:
    if not contact_ids:
        return {}

    result = await session.execute(
        select(ContactFieldValue).where(ContactFieldValue.contact_id.in_(contact_ids))
    )
    values: dict[int, dict[str, str | None]] = {}
    for row in result.scalars():
        values.setdefault(row.contact_id, {})[row.field_key] = row.value
    return values


def _serialize_contact(
    contact: Contact,
    definitions: dict[str, FieldDefinition],
    stored_values: dict[str, str | None],
) -> ContactRead:
    custom_payload: dict[str, object] = {}
    for key, stored in stored_values.items():
        definition = definitions.get(key)
        if definition is None:
            continue
        try:
            custom_payload[key] = decode_field_value(definition, stored)
        except ValueError:  # pragma: no cover - defensive against data drift
            continue

    return ContactRead(
        id=contact.id,
        name=contact.name,
        company=contact.company,
        title=contact.title,
        email=contact.email,
        phone=contact.phone,
        tags=contact.tags,
        note=contact.note,
        last_interacted_at=contact.last_interacted_at,
        created_at=contact.created_at,
        updated_at=contact.updated_at,
        custom=custom_payload,
    )
