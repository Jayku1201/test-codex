"""Database CRUD helpers for the CRM application."""
from __future__ import annotations

from typing import List, Optional

from sqlite3 import Connection, IntegrityError

from . import schemas


ALLOWED_SORT_COLUMNS = {"name", "email", "company", "status", "created_at", "updated_at"}


def _row_to_customer(row) -> schemas.Customer:
    return schemas.Customer(**dict(row))


def _row_to_interaction(row) -> schemas.Interaction:
    return schemas.Interaction(**dict(row))


def create_customer(connection: Connection, payload: schemas.CustomerCreate) -> schemas.Customer:
    timestamp = schemas.current_timestamp()
    data = payload.model_dump()
    if not data.get("status"):
        data["status"] = "active"

    try:
        cursor = connection.execute(
            """
            INSERT INTO customers (name, email, phone, company, status, notes, created_at, updated_at)
            VALUES (:name, :email, :phone, :company, :status, :notes, :created_at, :updated_at)
            """,
            {
                **data,
                "created_at": timestamp,
                "updated_at": timestamp,
            },
        )
    except IntegrityError as exc:  # pragma: no cover - exercised via API layer
        raise ValueError("A customer with this email already exists") from exc

    connection.commit()
    customer_id = cursor.lastrowid
    return get_customer(connection, customer_id)


def list_customers(
    connection: Connection,
    *,
    search: Optional[str] = None,
    status: Optional[str] = None,
    company: Optional[str] = None,
    limit: int = 20,
    offset: int = 0,
    sort_by: str = "created_at",
    sort_order: str = "desc",
) -> List[schemas.Customer]:
    limit = max(1, min(limit, 100))
    offset = max(0, offset)
    sort_column = sort_by if sort_by in ALLOWED_SORT_COLUMNS else "created_at"
    order = "ASC" if sort_order.lower() == "asc" else "DESC"

    query = ["SELECT * FROM customers"]
    parameters: List[object] = []
    filters = []

    if search:
        like = f"%{search.lower()}%"
        filters.append(
            "(LOWER(name) LIKE ? OR LOWER(email) LIKE ? OR LOWER(phone) LIKE ? OR LOWER(company) LIKE ?)"
        )
        parameters.extend([like, like, like, like])

    if status:
        filters.append("LOWER(status) = ?")
        parameters.append(status.lower())

    if company:
        filters.append("LOWER(company) = ?")
        parameters.append(company.lower())

    if filters:
        query.append("WHERE " + " AND ".join(filters))

    query.append(f"ORDER BY {sort_column} {order}")
    query.append("LIMIT ? OFFSET ?")
    parameters.extend([limit, offset])

    cursor = connection.execute(" ".join(query), parameters)
    rows = cursor.fetchall()
    return [_row_to_customer(row) for row in rows]


def get_customer(connection: Connection, customer_id: int) -> Optional[schemas.Customer]:
    cursor = connection.execute(
        "SELECT * FROM customers WHERE id = ?",
        (customer_id,),
    )
    row = cursor.fetchone()
    return _row_to_customer(row) if row else None


def update_customer(
    connection: Connection,
    customer_id: int,
    payload: schemas.CustomerUpdate,
) -> Optional[schemas.Customer]:
    existing = get_customer(connection, customer_id)
    if not existing:
        return None

    updates = payload.model_dump(exclude_unset=True)
    if not updates:
        return existing

    updates["updated_at"] = schemas.current_timestamp()
    set_clause = ", ".join(f"{column} = :{column}" for column in updates.keys())

    try:
        connection.execute(
            f"UPDATE customers SET {set_clause} WHERE id = :id",
            {**updates, "id": customer_id},
        )
    except IntegrityError as exc:  # pragma: no cover - exercised via API layer
        raise ValueError("A customer with this email already exists") from exc

    connection.commit()
    return get_customer(connection, customer_id)


def delete_customer(connection: Connection, customer_id: int) -> bool:
    cursor = connection.execute("DELETE FROM customers WHERE id = ?", (customer_id,))
    connection.commit()
    return cursor.rowcount > 0


def create_interaction(
    connection: Connection,
    customer_id: int,
    payload: schemas.InteractionCreate,
) -> Optional[schemas.Interaction]:
    if not get_customer(connection, customer_id):
        return None

    data = payload.model_dump()
    timestamp = schemas.current_timestamp()
    occurred_at = data.get("occurred_at") or timestamp

    cursor = connection.execute(
        """
        INSERT INTO interactions (customer_id, interaction_type, subject, notes, occurred_at, created_at)
        VALUES (:customer_id, :interaction_type, :subject, :notes, :occurred_at, :created_at)
        """,
        {
            **data,
            "customer_id": customer_id,
            "occurred_at": occurred_at,
            "created_at": timestamp,
        },
    )
    connection.commit()
    interaction_id = cursor.lastrowid
    return get_interaction(connection, interaction_id)


def get_interaction(connection: Connection, interaction_id: int) -> Optional[schemas.Interaction]:
    cursor = connection.execute("SELECT * FROM interactions WHERE id = ?", (interaction_id,))
    row = cursor.fetchone()
    return _row_to_interaction(row) if row else None


def list_interactions(
    connection: Connection,
    customer_id: Optional[int] = None,
) -> List[schemas.Interaction]:
    if customer_id is not None:
        cursor = connection.execute(
            "SELECT * FROM interactions WHERE customer_id = ? ORDER BY occurred_at DESC",
            (customer_id,),
        )
    else:
        cursor = connection.execute("SELECT * FROM interactions ORDER BY occurred_at DESC")

    rows = cursor.fetchall()
    return [_row_to_interaction(row) for row in rows]
