"""Import endpoints for contact CSV data."""
from __future__ import annotations

import csv
import io
import uuid
from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.common import data_response
from app.core.db import get_session
from app.models import Contact, ContactFieldValue
from app.services.contact_importer import ContactImportProcessor
from app.services.import_reports import report_store


router = APIRouter(prefix="/import", tags=["import"])


@router.post("/contacts/dry-run")
async def dry_run_import_contacts(
    file: UploadFile = File(...),
    mode: str = Form(...),
    auto_create_fields: str | None = Form(None),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Validate the provided CSV without mutating the database."""

    processor = ContactImportProcessor(
        session=session,
        mode=mode,
        auto_create_fields=_parse_bool(auto_create_fields),
        dry_run=True,
    )
    content = await file.read()
    header, parsed_rows, errors = await processor.run(content)

    payload = {
        "total": len(parsed_rows) + len(errors),
        "valid": len(parsed_rows),
        "invalid": len(errors),
        "errors": [
            {"row": error.row_index, "message": error.message} for error in errors
        ],
        "sample": [
            {"row_index": row.row_index, "parsed": row.sample}
            for row in parsed_rows[:3]
        ],
    }

    return data_response(payload)


@router.post("/contacts")
async def import_contacts(
    file: UploadFile = File(...),
    mode: str = Form(...),
    auto_create_fields: str | None = Form(None),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Apply the provided CSV import and return a processing report."""

    processor = ContactImportProcessor(
        session=session,
        mode=mode,
        auto_create_fields=_parse_bool(auto_create_fields),
        dry_run=False,
    )
    content = await file.read()
    header, parsed_rows, errors = await processor.run(content)

    created = 0
    updated = 0
    skipped = 0

    lookup_by_email: dict[str, Contact] = {}
    lookup_by_phone: dict[str, Contact] = {}
    custom_cache: dict[int, list[ContactFieldValue]] = {}

    report_entries: list[tuple[int, dict[str, Any]]] = []

    for row in parsed_rows:
        contact = row.existing_contact

        email = row.base_data.get("email")
        phone = row.base_data.get("phone")
        if email and email in lookup_by_email:
            contact = lookup_by_email[email]
        elif phone and phone in lookup_by_phone:
            contact = lookup_by_phone[phone]

        status = ""
        message = ""

        if contact is None:
            contact = Contact(**row.base_data)
            contact.last_interacted_at = row.last_interacted_at
            session.add(contact)
            await session.flush()
            values: list[ContactFieldValue] = []
            for key, encoded in row.custom_values.items():
                value_row = ContactFieldValue(
                    contact_id=contact.id, field_key=key, value=encoded
                )
                session.add(value_row)
                values.append(value_row)
            custom_cache[contact.id] = values
            created += 1
            status = "created"
        else:
            if processor.mode == "create_only":
                skipped += 1
                status = "skipped"
                message = "Existing contact skipped"
            else:
                for field, value in row.base_data.items():
                    setattr(contact, field, value)
                contact.last_interacted_at = row.last_interacted_at

                if contact.id not in custom_cache:
                    result = await session.execute(
                        select(ContactFieldValue).where(
                            ContactFieldValue.contact_id == contact.id
                        )
                    )
                    custom_cache[contact.id] = list(result.scalars())

                values_list = custom_cache[contact.id]
                existing_map = {value.field_key: value for value in values_list}

                for key, encoded in row.custom_values.items():
                    if key in existing_map:
                        existing_map[key].value = encoded
                    else:
                        value_row = ContactFieldValue(
                            contact_id=contact.id, field_key=key, value=encoded
                        )
                        session.add(value_row)
                        values_list.append(value_row)

                updated += 1
                status = "updated"

        if email:
            lookup_by_email[email] = contact
        if phone:
            lookup_by_phone[phone] = contact

        row_data = {key: _format_cell(row.original.get(key)) for key in header}
        report_entries.append((row.row_index, {**row_data, "status": status, "message": message}))

    failed = len(errors)
    for error in errors:
        row_data = {key: _format_cell(error.original.get(key)) for key in header}
        report_entries.append(
            (
                error.row_index,
                {**row_data, "status": "failed", "message": error.message},
            )
        )

    await session.commit()

    report_entries.sort(key=lambda item: item[0])
    report_rows = [entry for _, entry in report_entries]
    report_csv = _build_report_csv(header, report_rows)
    token = uuid.uuid4().hex
    report_store.store(token, report_csv)

    payload = {
        "created": created,
        "updated": updated,
        "skipped": skipped,
        "failed": failed,
        "report_url": f"/api/v1/import/reports/{token}.csv",
    }

    return data_response(payload)


@router.get("/reports/{token}.csv")
async def download_report(token: str) -> Response:
    """Download a previously generated import report."""

    report_store.purge_expired()
    content = report_store.fetch(token)
    if content is None:
        raise HTTPException(status_code=404, detail="Report expired or not found")
    return Response(
        content,
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=import-report-{token}.csv"},
    )


def _parse_bool(value: str | None) -> bool:
    if value is None:
        return False
    return value.lower() in {"1", "true", "yes", "on"}


def _build_report_csv(header: list[str], rows: list[dict[str, Any]]) -> str:
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=[*header, "status", "message"])
    writer.writeheader()
    for row in rows:
        writer.writerow(row)
    return output.getvalue()


def _format_cell(value: Any) -> str:
    if value is None:
        return ""
    return str(value)

