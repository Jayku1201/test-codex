"""Common helpers for API responses."""
from __future__ import annotations

from typing import TypeVar


T = TypeVar("T")


def data_response(payload: T) -> dict[str, T]:
    """Wrap a payload in the standard data envelope."""

    return {"data": payload}
