"""Field definition management API routes."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.common import data_response
from app.core.db import get_session
from app.models import ContactFieldValue, FieldDefinition
from app.schemas import (
    FieldDefinitionCreate,
    FieldDefinitionRead,
    FieldDefinitionUpdate,
)
from app.services.custom_fields import ensure_definition_compatible_with_values


router = APIRouter(prefix="/fields", tags=["fields"])


@router.get("")
async def list_fields(session: AsyncSession = Depends(get_session)) -> dict[str, list[FieldDefinitionRead]]:
    """Return all configured field definitions."""

    result = await session.execute(select(FieldDefinition).order_by(FieldDefinition.key))
    definitions = result.scalars().all()
    payload = [FieldDefinitionRead.model_validate(definition) for definition in definitions]
    return data_response(payload)


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_field(
    payload: FieldDefinitionCreate, session: AsyncSession = Depends(get_session)
) -> dict[str, FieldDefinitionRead]:
    """Create a new custom field definition."""

    definition = FieldDefinition(**payload.model_dump())
    session.add(definition)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Field key already exists",
        ) from exc
    await session.refresh(definition)
    return data_response(FieldDefinitionRead.model_validate(definition))


@router.put("/{key}")
async def update_field(
    key: str,
    payload: FieldDefinitionUpdate,
    session: AsyncSession = Depends(get_session),
) -> dict[str, FieldDefinitionRead]:
    """Update an existing field definition."""

    definition = await _get_field_or_404(session, key)
    new_key = payload.key or key

    values_result = await session.execute(
        select(ContactFieldValue).where(ContactFieldValue.field_key == key)
    )
    existing_values = values_result.scalars().all()

    definition.key = new_key
    definition.label = payload.label
    definition.type = payload.type
    definition.options = payload.options
    definition.required = payload.required

    try:
        ensure_definition_compatible_with_values(definition, existing_values)
    except ValueError as exc:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc

    if new_key != key:
        for value in existing_values:
            value.field_key = new_key

    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Field key already exists",
        ) from exc

    await session.refresh(definition)
    return data_response(FieldDefinitionRead.model_validate(definition))


@router.delete("/{key}")
async def delete_field(
    key: str, session: AsyncSession = Depends(get_session)
) -> dict[str, dict[str, bool]]:
    """Delete a field definition if it is not in use."""

    definition = await _get_field_or_404(session, key)

    in_use_result = await session.execute(
        select(ContactFieldValue.id).where(ContactFieldValue.field_key == key).limit(1)
    )
    if in_use_result.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "FIELD_IN_USE",
                "message": "Field is assigned to existing contacts",
            },
        )

    await session.delete(definition)
    await session.commit()
    return data_response({"deleted": True})


async def _get_field_or_404(session: AsyncSession, key: str) -> FieldDefinition:
    result = await session.execute(
        select(FieldDefinition).where(FieldDefinition.key == key)
    )
    definition = result.scalar_one_or_none()
    if definition is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Field definition not found"
        )
    return definition
