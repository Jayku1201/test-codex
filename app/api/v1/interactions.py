"""Interaction API routes."""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.common import data_response
from app.core.db import get_session
from app.models import Contact, Interaction
from app.schemas import InteractionCreate, InteractionRead, InteractionUpdate


router = APIRouter(prefix="/interactions", tags=["interactions"])


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_interaction(
    payload: InteractionCreate, session: AsyncSession = Depends(get_session)
) -> dict[str, InteractionRead]:
    """Create a new interaction for a contact."""

    contact = await session.get(Contact, payload.contact_id)
    if contact is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contact not found")

    interaction = Interaction(**payload.model_dump())
    session.add(interaction)
    await session.flush()
    await _sync_contact_last_interacted(session, contact.id)
    await session.commit()
    await session.refresh(interaction)
    return data_response(InteractionRead.model_validate(interaction))


@router.get("")
async def list_interactions(
    contact_id: int | None = None,
    from_datetime: datetime | None = Query(None, alias="from"),
    to_datetime: datetime | None = Query(None, alias="to"),
    session: AsyncSession = Depends(get_session),
) -> dict[str, list[InteractionRead]]:
    """List interactions with optional filtering."""

    stmt = select(Interaction)
    if contact_id is not None:
        stmt = stmt.where(Interaction.contact_id == contact_id)
    if from_datetime is not None:
        stmt = stmt.where(Interaction.happened_at >= from_datetime)
    if to_datetime is not None:
        stmt = stmt.where(Interaction.happened_at <= to_datetime)

    stmt = stmt.order_by(Interaction.happened_at.desc())
    result = await session.execute(stmt)
    interactions = result.scalars().all()
    payload = [InteractionRead.model_validate(interaction) for interaction in interactions]
    return data_response(payload)


@router.put("/{interaction_id}")
async def update_interaction(
    interaction_id: int,
    payload: InteractionUpdate,
    session: AsyncSession = Depends(get_session),
) -> dict[str, InteractionRead]:
    """Update an existing interaction."""

    interaction = await _get_interaction_or_404(session, interaction_id)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(interaction, field, value)

    await session.flush()
    await _sync_contact_last_interacted(session, interaction.contact_id)
    await session.commit()
    await session.refresh(interaction)
    return data_response(InteractionRead.model_validate(interaction))


@router.delete("/{interaction_id}")
async def delete_interaction(
    interaction_id: int, session: AsyncSession = Depends(get_session)
) -> dict[str, dict[str, bool]]:
    """Delete an interaction."""

    interaction = await _get_interaction_or_404(session, interaction_id)
    contact_id = interaction.contact_id
    await session.delete(interaction)
    await session.flush()
    await _sync_contact_last_interacted(session, contact_id)
    await session.commit()
    return data_response({"deleted": True})


async def _get_interaction_or_404(
    session: AsyncSession, interaction_id: int
) -> Interaction:
    interaction = await session.get(Interaction, interaction_id)
    if interaction is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Interaction not found")
    return interaction


async def _sync_contact_last_interacted(session: AsyncSession, contact_id: int) -> None:
    """Update the contact's last interacted timestamp."""

    contact = await session.get(Contact, contact_id)
    if contact is None:
        return
    result = await session.execute(
        select(func.max(Interaction.happened_at)).where(Interaction.contact_id == contact_id)
    )
    contact.last_interacted_at = result.scalar_one_or_none()
