"""Version 1 API routes for the personal contact management service."""
from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.v1.contacts import router as contacts_router
from app.api.v1.export import router as export_router
from app.api.v1.fields import router as fields_router
from app.api.v1.imports import router as import_router
from app.api.v1.interactions import router as interactions_router
from app.api.v1.reminders import router as reminders_router
from app.api.v1.integrations import router as integrations_router
from app.core.config import Settings, get_settings

router = APIRouter()
router.include_router(contacts_router)
router.include_router(fields_router)
router.include_router(interactions_router)
router.include_router(reminders_router)
router.include_router(export_router)
router.include_router(import_router)
router.include_router(integrations_router)


@router.get("/health", tags=["health"])
async def health_check(settings: Settings = Depends(get_settings)) -> dict[str, dict[str, str]]:
    """Report the service health information."""
    return {"data": {"status": "ok", "version": settings.version}}
