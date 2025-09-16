"""Configuration management for the FastAPI application."""
from __future__ import annotations

import os
from functools import lru_cache
from typing import Any

from dotenv import load_dotenv
from pydantic import BaseModel, Field, field_validator

load_dotenv()


class Settings(BaseModel):
    """Application configuration loaded from environment variables."""

    app_env: str = "dev"
    database_url: str = "sqlite:///./data.db"
    cors_origins: list[str] = Field(default_factory=list)
    version: str = "0.1.0"
    google_client_id: str = ""
    google_client_secret: str = ""
    google_redirect_uri: str = ""
    google_scopes: list[str] = Field(default_factory=list)

    @field_validator("cors_origins", mode="before")
    @classmethod
    def assemble_cors_origins(cls, value: Any) -> list[str]:
        if isinstance(value, str):
            if not value:
                return []
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        if isinstance(value, list):
            return value
        return []

    @field_validator("google_scopes", mode="before")
    @classmethod
    def assemble_google_scopes(cls, value: Any) -> list[str]:
        if isinstance(value, str):
            if not value:
                return []
            return [scope for scope in value.replace(",", " ").split() if scope]
        if isinstance(value, list):
            return value
        return []

    @property
    def async_database_url(self) -> str:
        if self.database_url.startswith("sqlite+aiosqlite://"):
            return self.database_url
        if self.database_url.startswith("sqlite:///"):
            return self.database_url.replace("sqlite:///", "sqlite+aiosqlite:///")
        if self.database_url.startswith("sqlite://"):
            return self.database_url.replace("sqlite://", "sqlite+aiosqlite://")
        return self.database_url


def _build_settings() -> Settings:
    raw_values: dict[str, Any] = {
        "app_env": os.getenv("APP_ENV"),
        "database_url": os.getenv("DATABASE_URL"),
        "cors_origins": os.getenv("CORS_ORIGINS"),
        "version": os.getenv("APP_VERSION"),
        "google_client_id": os.getenv("GOOGLE_CLIENT_ID"),
        "google_client_secret": os.getenv("GOOGLE_CLIENT_SECRET"),
        "google_redirect_uri": os.getenv("GOOGLE_REDIRECT_URI"),
        "google_scopes": os.getenv("GOOGLE_SCOPES"),
    }
    filtered_values = {key: value for key, value in raw_values.items() if value is not None}
    return Settings(**filtered_values)


@lru_cache()
def get_settings() -> Settings:
    """Return a cached settings instance."""
    return _build_settings()
