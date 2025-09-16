"""In-memory storage for generated import reports."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Dict


@dataclass
class _ReportEntry:
    created_at: datetime
    content: str


class ImportReportStore:
    """Store generated CSV reports for a limited duration."""

    def __init__(self, ttl_hours: int = 24) -> None:
        self._ttl = timedelta(hours=ttl_hours)
        self._storage: Dict[str, _ReportEntry] = {}

    def store(self, token: str, content: str) -> None:
        """Persist the CSV content for later download."""

        self._storage[token] = _ReportEntry(
            created_at=datetime.now(timezone.utc), content=content
        )

    def fetch(self, token: str) -> str | None:
        """Return the CSV content if the token is still valid."""

        entry = self._storage.get(token)
        if entry is None:
            return None

        if datetime.now(timezone.utc) - entry.created_at > self._ttl:
            self._storage.pop(token, None)
            return None
        return entry.content

    def purge_expired(self) -> None:
        """Remove expired entries proactively."""

        now = datetime.now(timezone.utc)
        expired = [
            token
            for token, entry in self._storage.items()
            if now - entry.created_at > self._ttl
        ]
        for token in expired:
            self._storage.pop(token, None)


report_store = ImportReportStore()

