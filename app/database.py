"""Database utilities for the CRM application."""
from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from typing import Generator


DEFAULT_DB_NAME = "crm.db"


def get_database_path() -> Path:
    """Return the path to the SQLite database file.

    The location can be configured with the ``CRM_DB_PATH`` environment
    variable. Relative paths are resolved from the current working directory.
    """

    path = os.getenv("CRM_DB_PATH", DEFAULT_DB_NAME)
    return Path(path)


def init_db() -> None:
    """Initialise the database if it does not exist."""

    db_path = get_database_path()
    if db_path != Path(":memory:"):
        db_path.parent.mkdir(parents=True, exist_ok=True)

    with sqlite3.connect(db_path) as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS customers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                email TEXT UNIQUE NOT NULL,
                phone TEXT,
                company TEXT,
                status TEXT,
                notes TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS interactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                customer_id INTEGER NOT NULL,
                interaction_type TEXT NOT NULL,
                subject TEXT,
                notes TEXT,
                occurred_at TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (customer_id) REFERENCES customers(id) ON DELETE CASCADE
            )
            """
        )
        connection.commit()


def get_connection() -> sqlite3.Connection:
    """Create a new SQLite connection using the configured database path."""

    db_path = get_database_path()
    connection = sqlite3.connect(db_path, check_same_thread=False)
    connection.row_factory = sqlite3.Row
    return connection


def get_db() -> Generator[sqlite3.Connection, None, None]:
    """Dependency that yields a database connection for FastAPI routes."""

    connection = get_connection()
    try:
        yield connection
    finally:
        connection.close()
