"""Server-rendered views for the personal contacts manager."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.models import (
    Contact,
    ContactFieldValue,
    GoogleToken,
    Interaction,
    Reminder,
)
from app.models.interaction import InteractionType
from app.services.custom_fields import decode_field_value, fetch_field_definitions

templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent / "templates"))

router = APIRouter()


@router.get("/", response_class=HTMLResponse, name="web_contacts")
async def contacts_page(
    request: Request,
    keyword: str | None = Query(None),
    tag: str | None = Query(None),
    session: AsyncSession = Depends(get_session),
) -> HTMLResponse:
    """Render the contacts index page."""

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

    stmt = stmt.order_by(Contact.name)
    result = await session.execute(stmt)
    contacts = list(result.scalars())

    if tag:
        contacts = [c for c in contacts if c.tags and tag in c.tags]

    contact_ids = [contact.id for contact in contacts]
    latest_interactions = await _load_latest_interactions(session, contact_ids)

    contacts_payload: list[dict[str, Any]] = []
    for contact in contacts:
        interaction = latest_interactions.get(contact.id)
        contacts_payload.append(
            {
                "id": contact.id,
                "name": contact.name,
                "company": contact.company,
                "title": contact.title,
                "email": contact.email,
                "phone": contact.phone,
                "tags": contact.tags or [],
                "last_interacted_at": contact.last_interacted_at,
                "latest_summary": _format_interaction_summary(interaction),
                "recent_note": _select_recent_note(contact, interaction),
            }
        )

    tag_rows = await session.execute(select(Contact.tags))
    tag_choices = sorted({tag for tags in tag_rows.scalars() if tags for tag in tags})
    tag_filters = [
        {"value": value, "selected": value == tag}
        for value in tag_choices
    ]

    return templates.TemplateResponse(
        "contacts/list.html",
        {
            "request": request,
            "contacts": contacts_payload,
            "keyword": keyword or "",
            "active_tag": tag or "",
            "tag_filters": tag_filters,
        },
    )


@router.get(
    "/contacts/{contact_id}",
    response_class=HTMLResponse,
    name="web_contact_detail",
)
async def contact_detail_page(
    request: Request,
    contact_id: int,
    session: AsyncSession = Depends(get_session),
) -> HTMLResponse:
    """Render the detail page for a specific contact."""

    contact = await session.get(Contact, contact_id)
    if contact is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Contact not found"
        )

    definitions = await fetch_field_definitions(session)
    values_result = await session.execute(
        select(ContactFieldValue).where(ContactFieldValue.contact_id == contact.id)
    )
    stored_values = {value.field_key: value.value for value in values_result.scalars()}

    custom_fields = []
    for definition in sorted(definitions.values(), key=lambda item: item.label.lower()):
        decoded = None
        try:
            decoded = decode_field_value(definition, stored_values.get(definition.key))
        except ValueError:
            decoded = stored_values.get(definition.key)
        custom_fields.append(
            {
                "key": definition.key,
                "label": definition.label,
                "type": definition.type.value,
                "options": definition.options or [],
                "required": definition.required,
                "value": decoded,
                "display_value": _stringify_custom_value(decoded),
            }
        )

    interactions_result = await session.execute(
        select(Interaction)
        .where(Interaction.contact_id == contact.id)
        .order_by(Interaction.happened_at.desc())
    )
    interactions = [
        {
            "id": interaction.id,
            "type": interaction.type.value,
            "summary": interaction.summary or "",
            "content": interaction.content or "",
            "happened_at": interaction.happened_at,
        }
        for interaction in interactions_result.scalars()
    ]

    reminders_result = await session.execute(
        select(Reminder)
        .where(Reminder.contact_id == contact.id)
        .order_by(Reminder.remind_at)
    )
    reminders = [
        {
            "id": reminder.id,
            "remind_at": reminder.remind_at,
            "content": reminder.content,
            "done": reminder.done,
            "sync_google": reminder.sync_google,
            "google_event_id": reminder.google_event_id,
        }
        for reminder in reminders_result.scalars()
    ]

    google_token = await session.execute(select(GoogleToken.id).limit(1))
    google_connected = google_token.scalar_one_or_none() is not None

    contact_payload = {
        "id": contact.id,
        "name": contact.name,
        "company": contact.company or "",
        "title": contact.title or "",
        "email": contact.email or "",
        "phone": contact.phone or "",
        "tags": contact.tags or [],
        "note": contact.note or "",
        "last_interacted_at": contact.last_interacted_at,
    }

    return templates.TemplateResponse(
        "contacts/detail.html",
        {
            "request": request,
            "contact": contact_payload,
            "tags_string": ", ".join(contact_payload["tags"]),
            "custom_fields": custom_fields,
            "interactions": interactions,
            "reminders": reminders,
            "interaction_types": [item.value for item in InteractionType],
            "google_connected": google_connected,
            "google_authorize_url": "/api/v1/integrations/google/authorize",
        },
    )


async def _load_latest_interactions(
    session: AsyncSession, contact_ids: list[int]
) -> dict[int, Interaction]:
    if not contact_ids:
        return {}

    stmt = (
        select(Interaction)
        .where(Interaction.contact_id.in_(contact_ids))
        .order_by(Interaction.contact_id, Interaction.happened_at.desc())
    )
    result = await session.execute(stmt)

    latest: dict[int, Interaction] = {}
    for interaction in result.scalars():
        if interaction.contact_id not in latest:
            latest[interaction.contact_id] = interaction
    return latest


def _format_interaction_summary(interaction: Interaction | None) -> str:
    if interaction is None:
        return ""
    happened_at = interaction.happened_at.strftime("%Y-%m-%d %H:%M")
    parts = [happened_at, interaction.type.value]
    if interaction.summary:
        parts.append(interaction.summary)
    return " · ".join(parts)


def _select_recent_note(
    contact: Contact, interaction: Interaction | None
) -> str:
    if interaction and interaction.summary:
        return interaction.summary
    if contact.note:
        return contact.note
    return ""


def _stringify_custom_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        return ", ".join(str(item) for item in value)
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)

