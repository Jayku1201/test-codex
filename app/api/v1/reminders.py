"""Reminder API routes."""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.v1.common import data_response
from app.core import oauth_google
from app.core.db import get_session
from app.core.oauth_google import (
    GoogleAPIError,
    GoogleNotConfiguredError,
    GoogleNotConnectedError,
)
from app.models import Contact, Reminder
from app.schemas import ReminderCreate, ReminderRead, ReminderUpdate


router = APIRouter(prefix="/reminders", tags=["reminders"])


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_reminder(
    payload: ReminderCreate, session: AsyncSession = Depends(get_session)
) -> dict[str, ReminderRead]:
    """Create a reminder for a contact."""

    contact = await session.get(Contact, payload.contact_id)
    if contact is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contact not found")

    reminder_data = payload.model_dump()
    service = oauth_google.get_google_calendar_service()
    if reminder_data.get("sync_google"):
        try:
            event_id = await service.create_event(
                session, contact, payload.remind_at, payload.content
            )
        except GoogleNotConfiguredError as exc:
            await session.rollback()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail={
                    "code": "GOOGLE_NOT_CONFIGURED",
                    "message": "Google OAuth is not configured",
                },
            ) from exc
        except GoogleNotConnectedError as exc:
            await session.rollback()
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "code": "GOOGLE_NOT_CONNECTED",
                    "message": "Google account is not connected",
                },
            ) from exc
        except GoogleAPIError as exc:
            await session.rollback()
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail={
                    "code": "GOOGLE_API_ERROR",
                    "message": "Failed to create Google Calendar event",
                },
            ) from exc
        reminder_data["google_event_id"] = event_id

    reminder = Reminder(**reminder_data)
    session.add(reminder)
    await session.commit()
    await session.refresh(reminder)
    return data_response(ReminderRead.model_validate(reminder))


@router.get("")
async def list_reminders(
    from_date: date | None = Query(None, alias="from"),
    to_date: date | None = Query(None, alias="to"),
    done: bool | None = None,
    session: AsyncSession = Depends(get_session),
) -> dict[str, list[ReminderRead]]:
    """List reminders with optional filters."""

    stmt = select(Reminder)
    if from_date is not None:
        stmt = stmt.where(Reminder.remind_at >= from_date)
    if to_date is not None:
        stmt = stmt.where(Reminder.remind_at <= to_date)
    if done is not None:
        stmt = stmt.where(Reminder.done.is_(done))

    stmt = stmt.order_by(Reminder.remind_at, Reminder.id)
    result = await session.execute(stmt)
    reminders = result.scalars().all()
    payload = [ReminderRead.model_validate(reminder) for reminder in reminders]
    return data_response(payload)


@router.put("/{reminder_id}")
async def update_reminder(
    reminder_id: int,
    payload: ReminderUpdate,
    session: AsyncSession = Depends(get_session),
) -> dict[str, ReminderRead]:
    """Update a reminder."""

    reminder = await _get_reminder_or_404(session, reminder_id, load_contact=True)
    updates = payload.model_dump(exclude_unset=True)
    desired_sync = updates.get("sync_google", reminder.sync_google)
    new_remind_at = updates.get("remind_at", reminder.remind_at)
    new_content = updates.get("content", reminder.content)
    new_event_id = reminder.google_event_id

    service = oauth_google.get_google_calendar_service()
    if desired_sync:
        try:
            if not reminder.sync_google or not new_event_id:
                new_event_id = await service.create_event(
                    session, reminder.contact, new_remind_at, new_content
                )
            else:
                await service.update_event(
                    session, new_event_id, reminder.contact, new_remind_at, new_content
                )
        except GoogleNotConfiguredError as exc:
            await session.rollback()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail={
                    "code": "GOOGLE_NOT_CONFIGURED",
                    "message": "Google OAuth is not configured",
                },
            ) from exc
        except GoogleNotConnectedError as exc:
            await session.rollback()
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "code": "GOOGLE_NOT_CONNECTED",
                    "message": "Google account is not connected",
                },
            ) from exc
        except GoogleAPIError as exc:
            await session.rollback()
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail={
                    "code": "GOOGLE_API_ERROR",
                    "message": "Failed to synchronize Google Calendar event",
                },
            ) from exc
    else:
        if reminder.sync_google and reminder.google_event_id:
            try:
                await service.delete_event(session, reminder.google_event_id)
            except GoogleNotConfiguredError as exc:
                await session.rollback()
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail={
                        "code": "GOOGLE_NOT_CONFIGURED",
                        "message": "Google OAuth is not configured",
                    },
                ) from exc
            except GoogleNotConnectedError as exc:
                await session.rollback()
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail={
                        "code": "GOOGLE_NOT_CONNECTED",
                        "message": "Google account is not connected",
                    },
                ) from exc
            except GoogleAPIError as exc:
                await session.rollback()
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail={
                        "code": "GOOGLE_API_ERROR",
                        "message": "Failed to delete Google Calendar event",
                    },
                ) from exc
            new_event_id = None

    for field, value in updates.items():
        setattr(reminder, field, value)
    reminder.sync_google = desired_sync
    reminder.google_event_id = new_event_id

    await session.commit()
    await session.refresh(reminder)
    return data_response(ReminderRead.model_validate(reminder))


@router.delete("/{reminder_id}")
async def delete_reminder(
    reminder_id: int, session: AsyncSession = Depends(get_session)
) -> dict[str, dict[str, bool]]:
    """Delete a reminder."""

    reminder = await _get_reminder_or_404(session, reminder_id)
    if reminder.sync_google and reminder.google_event_id:
        service = oauth_google.get_google_calendar_service()
        try:
            await service.delete_event(session, reminder.google_event_id)
        except GoogleNotConfiguredError as exc:
            await session.rollback()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail={
                    "code": "GOOGLE_NOT_CONFIGURED",
                    "message": "Google OAuth is not configured",
                },
            ) from exc
        except GoogleNotConnectedError as exc:
            await session.rollback()
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "code": "GOOGLE_NOT_CONNECTED",
                    "message": "Google account is not connected",
                },
            ) from exc
        except GoogleAPIError as exc:
            await session.rollback()
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail={
                    "code": "GOOGLE_API_ERROR",
                    "message": "Failed to delete Google Calendar event",
                },
            ) from exc

    await session.delete(reminder)
    await session.commit()
    return data_response({"deleted": True})


async def _get_reminder_or_404(
    session: AsyncSession, reminder_id: int, *, load_contact: bool = False
) -> Reminder:
    options = (selectinload(Reminder.contact),) if load_contact else ()
    reminder = await session.get(Reminder, reminder_id, options=options)
    if reminder is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Reminder not found")
    return reminder
