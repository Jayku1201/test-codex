from __future__ import annotations

import csv
import io
from datetime import date, datetime, timedelta, timezone

import pytest

from sqlalchemy import select

from app.core.config import get_settings
from app.core.db import AsyncSessionLocal
from app.models import GoogleToken


@pytest.mark.anyio("asyncio")
async def test_contacts_crud_and_search(client):
    contact_one = {
        "name": "Alice Johnson",
        "company": "Acme Corp",
        "title": "Manager",
        "email": "alice@example.com",
        "phone": "+1-555-0101",
        "tags": ["vip", "friends"],
        "note": "Met at conference",
    }
    contact_two = {
        "name": "Bob Smith",
        "company": "Beta LLC",
        "title": "Engineer",
        "email": "bob@example.com",
        "phone": "+1-555-0202",
        "tags": ["leads"],
    }

    create_resp_one = await client.post("/api/v1/contacts", json=contact_one)
    assert create_resp_one.status_code == 201
    contact_one_id = create_resp_one.json()["data"]["id"]

    create_resp_two = await client.post("/api/v1/contacts", json=contact_two)
    assert create_resp_two.status_code == 201
    contact_two_id = create_resp_two.json()["data"]["id"]

    keyword_resp = await client.get("/api/v1/contacts", params={"keyword": "acme"})
    assert keyword_resp.status_code == 200
    keyword_data = keyword_resp.json()["data"]
    assert len(keyword_data) == 1
    assert keyword_data[0]["id"] == contact_one_id

    tag_resp = await client.get("/api/v1/contacts", params={"tag": "leads"})
    assert tag_resp.status_code == 200
    tag_ids = {item["id"] for item in tag_resp.json()["data"]}
    assert tag_ids == {contact_two_id}

    update_payload = {"company": "Acme International", "tags": ["allies"]}
    update_resp = await client.put(
        f"/api/v1/contacts/{contact_one_id}", json=update_payload
    )
    assert update_resp.status_code == 200
    assert update_resp.json()["data"]["company"] == "Acme International"
    assert update_resp.json()["data"]["tags"] == ["allies"]

    delete_resp = await client.delete(f"/api/v1/contacts/{contact_two_id}")
    assert delete_resp.status_code == 200
    assert delete_resp.json()["data"] == {"deleted": True}


@pytest.mark.anyio("asyncio")
async def test_interactions_updates_last_interacted_at(client):
    contact_resp = await client.post(
        "/api/v1/contacts",
        json={
            "name": "Charlie Contact",
            "email": "charlie@example.com",
            "phone": "+1-555-0303",
        },
    )
    contact_id = contact_resp.json()["data"]["id"]

    first_interaction_time = datetime(2023, 1, 5, 12, 0, 0)
    second_interaction_time = datetime(2024, 6, 1, 9, 30, 0)
    third_interaction_time = datetime(2025, 2, 14, 15, 0, 0)

    first_resp = await client.post(
        "/api/v1/interactions",
        json={
            "contact_id": contact_id,
            "type": "meeting",
            "summary": "Kick-off",
            "happened_at": first_interaction_time.isoformat(),
        },
    )
    assert first_resp.status_code == 201

    contact_after_first = await client.get(f"/api/v1/contacts/{contact_id}")
    assert contact_after_first.status_code == 200
    assert contact_after_first.json()["data"]["last_interacted_at"] == first_interaction_time.isoformat()

    second_resp = await client.post(
        "/api/v1/interactions",
        json={
            "contact_id": contact_id,
            "type": "call",
            "summary": "Follow-up",
            "happened_at": second_interaction_time.isoformat(),
        },
    )
    assert second_resp.status_code == 201

    contact_after_second = await client.get(f"/api/v1/contacts/{contact_id}")
    assert contact_after_second.json()["data"]["last_interacted_at"] == second_interaction_time.isoformat()

    interaction_id = first_resp.json()["data"]["id"]
    update_resp = await client.put(
        f"/api/v1/interactions/{interaction_id}",
        json={"happened_at": third_interaction_time.isoformat()},
    )
    assert update_resp.status_code == 200

    contact_after_update = await client.get(f"/api/v1/contacts/{contact_id}")
    assert contact_after_update.json()["data"]["last_interacted_at"] == third_interaction_time.isoformat()


@pytest.mark.anyio("asyncio")
async def test_reminders_crud_and_filters(client):
    contact_resp = await client.post(
        "/api/v1/contacts",
        json={
            "name": "Dana Reminder",
            "email": "dana@example.com",
            "phone": "+1-555-0404",
        },
    )
    contact_id = contact_resp.json()["data"]["id"]

    first_date = date(2024, 1, 15)
    second_date = date(2024, 3, 1)

    first_resp = await client.post(
        "/api/v1/reminders",
        json={
            "contact_id": contact_id,
            "remind_at": first_date.isoformat(),
            "content": "Send new year greetings",
        },
    )
    assert first_resp.status_code == 201
    reminder_one_id = first_resp.json()["data"]["id"]

    second_resp = await client.post(
        "/api/v1/reminders",
        json={
            "contact_id": contact_id,
            "remind_at": second_date.isoformat(),
            "content": "Schedule quarterly review",
        },
    )
    assert second_resp.status_code == 201
    reminder_two_id = second_resp.json()["data"]["id"]

    upcoming_resp = await client.get(
        "/api/v1/reminders",
        params={"from": date(2024, 2, 1).isoformat()},
    )
    assert upcoming_resp.status_code == 200
    upcoming_ids = {item["id"] for item in upcoming_resp.json()["data"]}
    assert upcoming_ids == {reminder_two_id}

    done_filter_resp = await client.get(
        "/api/v1/reminders",
        params={"done": "false"},
    )
    assert done_filter_resp.status_code == 200
    assert len(done_filter_resp.json()["data"]) == 2

    update_resp = await client.put(
        f"/api/v1/reminders/{reminder_one_id}", json={"done": True}
    )
    assert update_resp.status_code == 200
    assert update_resp.json()["data"]["done"] is True

    done_only_resp = await client.get(
        "/api/v1/reminders",
        params={"done": "true"},
    )
    assert done_only_resp.status_code == 200
    done_ids = {item["id"] for item in done_only_resp.json()["data"]}
    assert done_ids == {reminder_one_id}

    delete_resp = await client.delete(f"/api/v1/reminders/{reminder_two_id}")
    assert delete_resp.status_code == 200
    assert delete_resp.json()["data"] == {"deleted": True}


@pytest.mark.anyio("asyncio")
async def test_fields_crud_and_validation(client):
    create_text = await client.post(
        "/api/v1/fields",
        json={"key": "nickname", "label": "Nickname", "type": "text"},
    )
    assert create_text.status_code == 201

    create_select = await client.post(
        "/api/v1/fields",
        json={
            "key": "relationship",
            "label": "Relationship",
            "type": "single_select",
            "options": ["client", "partner", "friend"],
        },
    )
    assert create_select.status_code == 201

    list_resp = await client.get("/api/v1/fields")
    assert list_resp.status_code == 200
    keys = [field["key"] for field in list_resp.json()["data"]]
    assert "nickname" in keys and "relationship" in keys

    invalid_key = await client.post(
        "/api/v1/fields",
        json={"key": "bad-key", "label": "Bad", "type": "text"},
    )
    assert invalid_key.status_code == 422

    missing_options = await client.post(
        "/api/v1/fields",
        json={"key": "noopts", "label": "No Options", "type": "multi_select"},
    )
    assert missing_options.status_code == 422

    update_resp = await client.put(
        "/api/v1/fields/nickname",
        json={
            "key": "preferred_name",
            "label": "Preferred Name",
            "type": "text",
            "required": True,
        },
    )
    assert update_resp.status_code == 200
    assert update_resp.json()["data"]["key"] == "preferred_name"
    assert update_resp.json()["data"]["required"] is True

    list_after_update = await client.get("/api/v1/fields")
    assert list_after_update.status_code == 200
    updated_keys = [field["key"] for field in list_after_update.json()["data"]]
    assert "preferred_name" in updated_keys

    contact_resp = await client.post(
        "/api/v1/contacts",
        json={
            "name": "Nickname User",
            "email": "nick@example.com",
            "phone": "+1-555-0909",
            "custom": {"preferred_name": "Ace"},
        },
    )
    assert contact_resp.status_code == 201

    incompatible_update = await client.put(
        "/api/v1/fields/preferred_name",
        json={
            "key": "preferred_name",
            "label": "Preferred Name",
            "type": "number",
            "required": True,
        },
    )
    assert incompatible_update.status_code == 422


@pytest.mark.anyio("asyncio")
async def test_contacts_custom_fields_roundtrip(client):
    await client.post(
        "/api/v1/fields",
        json={"key": "joined_on", "label": "Joined On", "type": "date", "required": True},
    )
    await client.post(
        "/api/v1/fields",
        json={"key": "newsletter", "label": "Newsletter", "type": "bool"},
    )
    await client.post(
        "/api/v1/fields",
        json={
            "key": "hobbies",
            "label": "Hobbies",
            "type": "multi_select",
            "options": ["golf", "music", "reading"],
        },
    )
    await client.post(
        "/api/v1/fields",
        json={"key": "score", "label": "Score", "type": "number"},
    )

    missing_required = await client.post(
        "/api/v1/contacts",
        json={
            "name": "Evan Required",
            "email": "evan@example.com",
            "phone": "+1-555-0606",
        },
    )
    assert missing_required.status_code == 422

    create_resp = await client.post(
        "/api/v1/contacts",
        json={
            "name": "Evan Fields",
            "email": "evan.fields@example.com",
            "phone": "+1-555-0707",
            "custom": {
                "joined_on": "2024-06-01",
                "newsletter": "true",
                "hobbies": ["golf", "music"],
                "score": 4.5,
            },
        },
    )
    assert create_resp.status_code == 201
    contact_id = create_resp.json()["data"]["id"]
    custom_data = create_resp.json()["data"]["custom"]
    assert custom_data == {
        "joined_on": "2024-06-01",
        "newsletter": True,
        "hobbies": ["golf", "music"],
        "score": 4.5,
    }

    retrieve_resp = await client.get(f"/api/v1/contacts/{contact_id}")
    assert retrieve_resp.status_code == 200
    assert retrieve_resp.json()["data"]["custom"] == custom_data

    update_resp = await client.put(
        f"/api/v1/contacts/{contact_id}",
        json={
            "custom": {
                "score": 10,
            }
        },
    )
    assert update_resp.status_code == 200
    updated_custom = update_resp.json()["data"]["custom"]
    assert updated_custom["score"] == 10
    assert updated_custom["joined_on"] == "2024-06-01"
    assert updated_custom["newsletter"] is True
    assert updated_custom["hobbies"] == ["golf", "music"]

    list_resp = await client.get("/api/v1/contacts")
    assert list_resp.status_code == 200
    listed_contact = next(item for item in list_resp.json()["data"] if item["id"] == contact_id)
    assert listed_contact["custom"]["score"] == 10


@pytest.mark.anyio("asyncio")
async def test_delete_field_in_use_returns_error(client):
    await client.post(
        "/api/v1/fields",
        json={"key": "anniversary", "label": "Anniversary", "type": "date"},
    )

    contact_resp = await client.post(
        "/api/v1/contacts",
        json={
            "name": "Field Usage",
            "email": "usage@example.com",
            "phone": "+1-555-0808",
            "custom": {"anniversary": "2023-09-10"},
        },
    )
    assert contact_resp.status_code == 201
    contact_id = contact_resp.json()["data"]["id"]

    delete_resp = await client.delete("/api/v1/fields/anniversary")
    assert delete_resp.status_code == 400
    assert delete_resp.json()["error"]["code"] == "FIELD_IN_USE"

    await client.delete(f"/api/v1/contacts/{contact_id}")

    delete_after_contact = await client.delete("/api/v1/fields/anniversary")
    assert delete_after_contact.status_code == 200
    assert delete_after_contact.json()["data"] == {"deleted": True}


@pytest.mark.anyio("asyncio")
async def test_export_contacts_csv_ok(client):
    await client.post(
        "/api/v1/fields",
        json={"key": "industry", "label": "Industry", "type": "text"},
    )
    await client.post(
        "/api/v1/fields",
        json={"key": "is_vip", "label": "VIP", "type": "bool"},
    )
    await client.post(
        "/api/v1/fields",
        json={
            "key": "regions",
            "label": "Regions",
            "type": "multi_select",
            "options": ["North", "South", "West"],
        },
    )

    contact_resp = await client.post(
        "/api/v1/contacts",
        json={
            "name": "Export Target",
            "company": "Example Co",
            "title": "Lead",
            "email": "export@example.com",
            "phone": "+1-555-0606",
            "tags": ["vip", "investor"],
            "note": "Important partner",
            "custom": {
                "industry": "Finance",
                "is_vip": True,
                "regions": ["North", "South"],
            },
        },
    )
    contact_id = contact_resp.json()["data"]["id"]

    first_time = datetime(2024, 5, 1, 9, 0, 0)
    second_time = datetime(2024, 5, 2, 10, 0, 0)
    await client.post(
        "/api/v1/interactions",
        json={
            "contact_id": contact_id,
            "type": "meeting",
            "summary": "Kickoff",
            "happened_at": first_time.isoformat(),
        },
    )
    await client.post(
        "/api/v1/interactions",
        json={
            "contact_id": contact_id,
            "type": "call",
            "summary": "Follow up",
            "happened_at": second_time.isoformat(),
        },
    )

    export_resp = await client.get(
        "/api/v1/export/contacts.csv",
        params={"tags": "vip", "include_private": "false"},
    )
    assert export_resp.status_code == 200

    reader = csv.DictReader(io.StringIO(export_resp.text))
    rows = list(reader)
    assert len(rows) == 1
    row = rows[0]
    assert row["name"] == "Export Target"
    assert row["email"] == ""
    assert row["phone"] == ""
    assert row["tags"] == "vip,investor"
    assert row["custom.industry"] == "Finance"
    assert row["custom.is_vip"] == "true"
    assert row["custom.regions"] == "North,South"
    assert row["last_interaction_summary"] == (
        f"{second_time.isoformat()} call Follow up"
    )


@pytest.mark.anyio("asyncio")
async def test_import_dry_run_detects_errors(client):
    await client.post(
        "/api/v1/fields",
        json={
            "key": "loyalty",
            "label": "Loyalty",
            "type": "text",
            "required": True,
        },
    )
    await client.post(
        "/api/v1/fields",
        json={
            "key": "segment",
            "label": "Segment",
            "type": "single_select",
            "options": ["A", "B"],
        },
    )

    csv_content = (
        "name,company,title,email,phone,tags,note,last_interacted_at,custom.loyalty,custom.segment\n"
        "Valid Person,Valid Co,Rep,valid@example.com,+1-555-1111,alpha,Valid note,2024-01-01,Gold,A\n"
        "Missing Loyalty,Test Co,Rep,missing@example.com,+1-555-2222,,No note,2024-02-01,,A\n"
        "Error Person,Error Co,Rep,error@example.com,+1-555-3333,,Info,2024-02-02,Gold,Invalid\n"
    )

    resp = await client.post(
        "/api/v1/import/contacts/dry-run",
        data={"mode": "create_only"},
        files={"file": ("contacts.csv", csv_content, "text/csv")},
    )
    assert resp.status_code == 200

    payload = resp.json()["data"]
    assert payload["total"] == 3
    assert payload["valid"] == 1
    assert payload["invalid"] == 2
    assert len(payload["errors"]) == 2
    messages = {error["message"] for error in payload["errors"]}
    assert any("Field 'loyalty' is required" in msg for msg in messages)
    assert any("Value must be one of the available options" in msg for msg in messages)

    sample = payload["sample"][0]
    assert sample["row_index"] == 1
    assert sample["parsed"]["name"] == "Valid Person"
    assert sample["parsed"]["custom"]["loyalty"] == "Gold"


@pytest.mark.anyio("asyncio")
async def test_import_create_only_skips_existing(client):
    await client.post(
        "/api/v1/fields",
        json={"key": "notes", "label": "Notes", "type": "text"},
    )

    existing_resp = await client.post(
        "/api/v1/contacts",
        json={
            "name": "Existing One",
            "company": "Orig Co",
            "email": "existing@example.com",
            "phone": "+1-555-4444",
            "custom": {"notes": "keep"},
        },
    )
    existing_id = existing_resp.json()["data"]["id"]

    csv_content = """name,company,title,email,phone,tags,note,last_interacted_at,custom.notes
Existing One,Changed Co,,existing@example.com,+1-555-4444,,,
New Person,New Co,,new@example.com,+1-555-5555,,,
"""

    resp = await client.post(
        "/api/v1/import/contacts",
        data={"mode": "create_only"},
        files={"file": ("contacts.csv", csv_content, "text/csv")},
    )
    assert resp.status_code == 200
    result = resp.json()["data"]
    assert result["created"] == 1
    assert result["updated"] == 0
    assert result["skipped"] == 1
    assert result["failed"] == 0

    existing_after = await client.get(f"/api/v1/contacts/{existing_id}")
    assert existing_after.json()["data"]["company"] == "Orig Co"
    assert existing_after.json()["data"]["custom"]["notes"] == "keep"

    report_resp = await client.get(result["report_url"])
    report_rows = list(csv.DictReader(io.StringIO(report_resp.text)))
    assert [row["status"] for row in report_rows] == ["skipped", "created"]


@pytest.mark.anyio("asyncio")
async def test_import_upsert_updates_existing(client):
    await client.post(
        "/api/v1/fields",
        json={"key": "industry", "label": "Industry", "type": "text"},
    )

    create_resp = await client.post(
        "/api/v1/contacts",
        json={
            "name": "Update Me",
            "company": "Old Co",
            "email": "update@example.com",
            "phone": "+1-555-6666",
            "tags": ["old"],
            "custom": {"industry": "Tech"},
        },
    )
    contact_id = create_resp.json()["data"]["id"]

    csv_content = """name,company,title,email,phone,tags,note,last_interacted_at,custom.industry
Update Me,New Co,,update@example.com,+1-555-6666,new,,2024-03-03,Finance
Second,Second Co,,second@example.com,+1-555-7777,,,
"""

    resp = await client.post(
        "/api/v1/import/contacts",
        data={"mode": "upsert"},
        files={"file": ("contacts.csv", csv_content, "text/csv")},
    )
    assert resp.status_code == 200
    payload = resp.json()["data"]
    assert payload["created"] == 1
    assert payload["updated"] == 1
    assert payload["skipped"] == 0
    assert payload["failed"] == 0

    updated_contact = await client.get(f"/api/v1/contacts/{contact_id}")
    updated_data = updated_contact.json()["data"]
    assert updated_data["company"] == "New Co"
    assert updated_data["tags"] == ["new"]
    assert updated_data["custom"]["industry"] == "Finance"

    report_resp = await client.get(payload["report_url"])
    rows = list(csv.DictReader(io.StringIO(report_resp.text)))
    assert [row["status"] for row in rows] == ["updated", "created"]


@pytest.mark.anyio("asyncio")
async def test_custom_field_auto_create_text_only(client):
    csv_content = """name,company,title,email,phone,tags,note,last_interacted_at,custom.nickname,custom.hobby
Auto Field,,,auto@example.com,+1-555-8888,,,
"""

    resp = await client.post(
        "/api/v1/import/contacts",
        data={"mode": "create_only", "auto_create_fields": "true"},
        files={"file": ("contacts.csv", csv_content, "text/csv")},
    )
    assert resp.status_code == 200
    payload = resp.json()["data"]
    assert payload["created"] == 1

    fields_resp = await client.get("/api/v1/fields")
    field_types = {
        (field["key"], field["type"]) for field in fields_resp.json()["data"]
    }
    assert ("nickname", "text") in field_types
    assert ("hobby", "text") in field_types

    contacts_resp = await client.get("/api/v1/contacts")
    custom_payload = contacts_resp.json()["data"][0]["custom"]
    assert "nickname" in custom_payload
    assert "hobby" in custom_payload


@pytest.mark.anyio("asyncio")
async def test_google_oauth_roundtrip_fake(client, monkeypatch):
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "client-id")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "client-secret")
    monkeypatch.setenv("GOOGLE_REDIRECT_URI", "http://localhost/callback")
    monkeypatch.setenv("GOOGLE_SCOPES", "scope-one scope-two")
    get_settings.cache_clear()

    authorize_resp = await client.get("/api/v1/integrations/google/authorize")
    assert authorize_resp.status_code == 302
    location = authorize_resp.headers.get("location", "")
    assert "client-id" in location
    assert "scope-one+scope-two" in location

    async def fake_request_token(self, payload):  # type: ignore[override]
        assert payload["code"] == "auth-code"
        return {
            "access_token": "access-token",
            "refresh_token": "refresh-token",
            "expires_in": 3600,
        }

    monkeypatch.setattr(
        "app.core.oauth_google.GoogleOAuthClient._request_token",
        fake_request_token,
    )

    callback_resp = await client.get(
        "/api/v1/integrations/google/callback", params={"code": "auth-code"}
    )
    assert callback_resp.status_code == 200
    assert callback_resp.json()["data"] == {"connected": True}

    async with AsyncSessionLocal() as session:
        result = await session.execute(select(GoogleToken))
        token = result.scalars().first()
        assert token is not None
        assert token.access_token == "access-token"
        assert token.refresh_token == "refresh-token"
        assert token.expiry is not None


@pytest.mark.anyio("asyncio")
async def test_reminder_create_with_google_sync_creates_event(client, monkeypatch):
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "client-id")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "client-secret")
    monkeypatch.setenv("GOOGLE_REDIRECT_URI", "http://localhost/callback")
    monkeypatch.setenv("GOOGLE_SCOPES", "scope-one")
    get_settings.cache_clear()

    async with AsyncSessionLocal() as session:
        token = GoogleToken(
            access_token="initial-token",
            refresh_token="refresh-token",
            expiry=datetime.now(timezone.utc) + timedelta(hours=1),
        )
        session.add(token)
        await session.commit()

    class FakeCalendarService:
        def __init__(self):
            self.created: list[tuple[int, date, str]] = []

        async def create_event(self, session, contact, remind_at, content):  # noqa: ANN001
            self.created.append((contact.id, remind_at, content))
            return "evt-123"

        async def update_event(self, *args, **kwargs):  # noqa: ANN001, ANN002
            raise AssertionError("update_event should not be called")

        async def delete_event(self, *args, **kwargs):  # noqa: ANN001, ANN002
            raise AssertionError("delete_event should not be called")

    fake_service = FakeCalendarService()
    monkeypatch.setattr(
        "app.api.v1.reminders.oauth_google.get_google_calendar_service",
        lambda: fake_service,
    )

    contact_resp = await client.post(
        "/api/v1/contacts",
        json={"name": "OAuth Contact", "email": "oauth@example.com"},
    )
    contact_id = contact_resp.json()["data"]["id"]

    remind_date = date(2024, 7, 4)
    create_resp = await client.post(
        "/api/v1/reminders",
        json={
            "contact_id": contact_id,
            "remind_at": remind_date.isoformat(),
            "content": "Follow up",
            "sync_google": True,
        },
    )
    assert create_resp.status_code == 201
    payload = create_resp.json()["data"]
    assert payload["sync_google"] is True
    assert payload["google_event_id"] == "evt-123"

    assert fake_service.created == [(contact_id, remind_date, "Follow up")]


@pytest.mark.anyio("asyncio")
async def test_reminder_update_delete_syncs_google(client, monkeypatch):
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "client-id")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "client-secret")
    monkeypatch.setenv("GOOGLE_REDIRECT_URI", "http://localhost/callback")
    monkeypatch.setenv("GOOGLE_SCOPES", "scope-one")
    get_settings.cache_clear()

    async with AsyncSessionLocal() as session:
        token = GoogleToken(
            access_token="initial-token",
            refresh_token="refresh-token",
            expiry=datetime.now(timezone.utc) + timedelta(hours=1),
        )
        session.add(token)
        await session.commit()

    class FakeCalendarService:
        def __init__(self):
            self.created: list[str] = []
            self.updated: list[tuple[str, date, str]] = []
            self.deleted: list[str] = []

        async def create_event(self, session, contact, remind_at, content):  # noqa: ANN001
            event_id = f"evt-{len(self.created) + 1}"
            self.created.append(event_id)
            return event_id

        async def update_event(self, session, event_id, contact, remind_at, content):  # noqa: ANN001
            self.updated.append((event_id, remind_at, content))

        async def delete_event(self, session, event_id):  # noqa: ANN001
            self.deleted.append(event_id)

    fake_service = FakeCalendarService()
    monkeypatch.setattr(
        "app.api.v1.reminders.oauth_google.get_google_calendar_service",
        lambda: fake_service,
    )

    contact_resp = await client.post(
        "/api/v1/contacts",
        json={"name": "Sync Contact", "email": "sync@example.com"},
    )
    contact_id = contact_resp.json()["data"]["id"]

    create_resp = await client.post(
        "/api/v1/reminders",
        json={
            "contact_id": contact_id,
            "remind_at": date(2024, 7, 1).isoformat(),
            "content": "First touch",
            "sync_google": True,
        },
    )
    reminder_id = create_resp.json()["data"]["id"]
    assert fake_service.created == ["evt-1"]

    update_resp = await client.put(
        f"/api/v1/reminders/{reminder_id}",
        json={
            "remind_at": date(2024, 7, 2).isoformat(),
            "content": "Updated touch",
        },
    )
    assert update_resp.status_code == 200
    assert fake_service.updated == [("evt-1", date(2024, 7, 2), "Updated touch")]

    disable_resp = await client.put(
        f"/api/v1/reminders/{reminder_id}", json={"sync_google": False}
    )
    assert disable_resp.status_code == 200
    assert fake_service.deleted == ["evt-1"]

    delete_resp = await client.delete(f"/api/v1/reminders/{reminder_id}")
    assert delete_resp.status_code == 200
