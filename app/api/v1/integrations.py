"""External integration endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.common import data_response
from app.core.db import get_session
from app.core.oauth_google import (
    GoogleAPIError,
    GoogleNotConfiguredError,
    get_google_oauth_client,
)

router = APIRouter(prefix="/integrations", tags=["integrations"])


@router.get("/google/authorize", status_code=status.HTTP_302_FOUND)
async def google_authorize() -> RedirectResponse:
    """Redirect the user to Google's OAuth consent page."""

    oauth_client = get_google_oauth_client()
    try:
        authorize_url = oauth_client.build_authorize_url()
    except GoogleNotConfiguredError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"code": "GOOGLE_NOT_CONFIGURED", "message": str(exc)},
        ) from exc
    return RedirectResponse(authorize_url, status_code=status.HTTP_302_FOUND)


@router.get("/google/callback")
async def google_callback(
    code: str | None = None,
    error: str | None = None,
    session: AsyncSession = Depends(get_session),
) -> dict[str, dict[str, bool]]:
    """Handle the OAuth callback by exchanging the code for tokens."""

    if error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "GOOGLE_OAUTH_ERROR", "message": error},
        )
    if not code:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "VALIDATION_ERROR", "message": "Missing authorization code"},
        )

    oauth_client = get_google_oauth_client()
    try:
        await oauth_client.exchange_code(session, code)
        await session.commit()
    except GoogleNotConfiguredError as exc:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"code": "GOOGLE_NOT_CONFIGURED", "message": str(exc)},
        ) from exc
    except GoogleAPIError as exc:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={"code": "GOOGLE_API_ERROR", "message": "Failed to exchange authorization code"},
        ) from exc

    return data_response({"connected": True})
