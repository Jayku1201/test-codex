"""Google OAuth and Calendar helper utilities."""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlencode

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.db import AsyncSessionLocal
from app.models import Contact, GoogleToken

AUTH_BASE_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
CALENDAR_EVENTS_URL = "https://www.googleapis.com/calendar/v3/calendars/primary/events"
TOKEN_EXPIRY_GRACE = timedelta(seconds=60)

logger = logging.getLogger(__name__)


class GoogleOAuthError(Exception):
    """Base error for Google OAuth operations."""


class GoogleNotConfiguredError(GoogleOAuthError):
    """Raised when OAuth credentials are not configured."""


class GoogleNotConnectedError(GoogleOAuthError):
    """Raised when no stored credentials are available."""


class GoogleAPIError(GoogleOAuthError):
    """Raised when Google API returns an error response."""

    def __init__(self, message: str, *, status_code: int | None = None, body: str | None = None):
        super().__init__(message)
        self.status_code = status_code
        self.body = body


class GoogleOAuthClient:
    """Handle OAuth URL generation and token lifecycle management."""

    def __init__(self, settings: Settings):
        self.settings = settings

    def _require_configured(self) -> None:
        if not (
            self.settings.google_client_id
            and self.settings.google_client_secret
            and self.settings.google_redirect_uri
            and self.settings.google_scopes
        ):
            raise GoogleNotConfiguredError("Google OAuth credentials are not fully configured")

    def build_authorize_url(self, *, state: str | None = None) -> str:
        """Return the Google OAuth authorization URL."""

        self._require_configured()
        params: dict[str, Any] = {
            "client_id": self.settings.google_client_id,
            "redirect_uri": self.settings.google_redirect_uri,
            "response_type": "code",
            "scope": " ".join(self.settings.google_scopes),
            "access_type": "offline",
            "prompt": "consent",
        }
        if state is not None:
            params["state"] = state
        return f"{AUTH_BASE_URL}?{urlencode(params)}"

    async def exchange_code(self, session: AsyncSession, code: str) -> GoogleToken:
        """Exchange an authorization code for tokens and persist them."""

        self._require_configured()
        payload = {
            "code": code,
            "client_id": self.settings.google_client_id,
            "client_secret": self.settings.google_client_secret,
            "redirect_uri": self.settings.google_redirect_uri,
            "grant_type": "authorization_code",
        }
        token_data = await self._request_token(payload)
        token = await self._store_token(session, token_data)
        return token

    async def ensure_valid_token(self, session: AsyncSession) -> GoogleToken | None:
        """Return a valid access token, refreshing it when necessary."""

        self._require_configured()
        token = await self._get_token(session)
        if token is None:
            return None

        if token.expiry is None:
            return token

        now = datetime.now(timezone.utc)
        if token.expiry - now > TOKEN_EXPIRY_GRACE:
            return token

        if not token.refresh_token:
            if token.expiry <= now:
                raise GoogleNotConnectedError("Stored Google token has expired and cannot be refreshed")
            return token

        refresh_payload = {
            "refresh_token": token.refresh_token,
            "client_id": self.settings.google_client_id,
            "client_secret": self.settings.google_client_secret,
            "grant_type": "refresh_token",
        }
        token_data = await self._request_token(refresh_payload)
        await self._store_token(session, token_data, existing=token)
        return token

    async def _get_token(self, session: AsyncSession) -> GoogleToken | None:
        result = await session.execute(select(GoogleToken).limit(1))
        return result.scalars().first()

    async def _store_token(
        self,
        session: AsyncSession,
        token_data: dict[str, Any],
        *,
        existing: GoogleToken | None = None,
    ) -> GoogleToken:
        access_token = token_data.get("access_token")
        if not access_token:
            raise GoogleAPIError("Google token response missing access_token")

        expires_in = int(token_data.get("expires_in", 3600))
        expiry = datetime.now(timezone.utc) + timedelta(seconds=expires_in)
        refresh_token = token_data.get("refresh_token")

        token = existing
        if token is None:
            token = await self._get_token(session)
        if token is None:
            token = GoogleToken(access_token=access_token, refresh_token=refresh_token, expiry=expiry)
            session.add(token)
        else:
            token.access_token = access_token
            if refresh_token:
                token.refresh_token = refresh_token
            token.expiry = expiry

        await session.flush()
        return token

    async def _request_token(self, payload: dict[str, str]) -> dict[str, Any]:
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(TOKEN_URL, data=payload)
        except httpx.HTTPError as exc:  # pragma: no cover - network failure
            logger.error("Failed to communicate with Google OAuth token endpoint", exc_info=exc)
            raise GoogleAPIError("Unable to reach Google OAuth endpoint") from exc

        if response.status_code >= 400:
            logger.error(
                "Google OAuth token exchange failed",
                extra={"status_code": response.status_code, "body": response.text},
            )
            raise GoogleAPIError(
                "Google OAuth token exchange failed",
                status_code=response.status_code,
                body=response.text,
            )
        return response.json()


class GoogleCalendarService:
    """Interact with the Google Calendar API for reminders."""

    def __init__(self, oauth_client: GoogleOAuthClient):
        self._oauth = oauth_client

    async def _require_token(self, session: AsyncSession) -> GoogleToken:
        token = await self._oauth.ensure_valid_token(session)
        if token is None:
            raise GoogleNotConnectedError("Google account is not connected")
        return token

    async def create_event(
        self,
        session: AsyncSession,
        contact: Contact,
        remind_at: date | datetime,
        content: str,
    ) -> str:
        token = await self._require_token(session)
        body = self._build_event_body(contact, remind_at, content)
        data = await self._authorized_request("POST", CALENDAR_EVENTS_URL, token, json=body)
        event_id = data.get("id") if isinstance(data, dict) else None
        if not event_id:
            raise GoogleAPIError("Google Calendar did not return an event id")
        return str(event_id)

    async def update_event(
        self,
        session: AsyncSession,
        event_id: str,
        contact: Contact,
        remind_at: date | datetime,
        content: str,
    ) -> None:
        token = await self._require_token(session)
        body = self._build_event_body(contact, remind_at, content)
        await self._authorized_request("PATCH", f"{CALENDAR_EVENTS_URL}/{event_id}", token, json=body)

    async def delete_event(self, session: AsyncSession, event_id: str) -> None:
        token = await self._require_token(session)
        await self._authorized_request("DELETE", f"{CALENDAR_EVENTS_URL}/{event_id}", token)

    async def _authorized_request(
        self,
        method: str,
        url: str,
        token: GoogleToken,
        *,
        json: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        headers = {
            "Authorization": f"Bearer {token.access_token}",
            "Content-Type": "application/json",
        }
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.request(method, url, headers=headers, json=json)
        except httpx.HTTPError as exc:  # pragma: no cover - network failure
            logger.error("Google Calendar request failed", exc_info=exc)
            raise GoogleAPIError("Failed to communicate with Google Calendar") from exc

        if response.status_code >= 400:
            logger.error(
                "Google Calendar API error",
                extra={"status_code": response.status_code, "body": response.text},
            )
            raise GoogleAPIError(
                "Google Calendar API error",
                status_code=response.status_code,
                body=response.text,
            )

        if response.status_code == 204 or not response.content:
            return None
        return response.json()

    @staticmethod
    def _build_event_body(contact: Contact, remind_at: date | datetime, content: str) -> dict[str, Any]:
        date_value = remind_at.date() if isinstance(remind_at, datetime) else remind_at
        iso_date = date_value.isoformat()
        return {
            "summary": content,
            "description": f"Contact: {contact.name} / id: {contact.id}",
            "start": {"date": iso_date},
            "end": {"date": iso_date},
        }


def get_google_oauth_client() -> GoogleOAuthClient:
    return GoogleOAuthClient(get_settings())


def get_google_calendar_service() -> GoogleCalendarService:
    return GoogleCalendarService(get_google_oauth_client())


async def get_stored_google_token() -> GoogleToken | None:
    """Return the stored Google token using an independent session."""

    async with AsyncSessionLocal() as session:
        result = await session.execute(select(GoogleToken).limit(1))
        return result.scalars().first()
