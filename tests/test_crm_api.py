import os
import sys
import tempfile
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))


@pytest.fixture(scope="module")
def client():
    with tempfile.TemporaryDirectory() as tmpdir:
        os.environ["CRM_DB_PATH"] = os.path.join(tmpdir, "test.db")
        from app.main import app

        with TestClient(app) as test_client:
            yield test_client


def _unique_email() -> str:
    return f"user-{uuid.uuid4().hex}@example.com"


def _create_customer(client: TestClient, **overrides):
    payload = {
        "name": overrides.get("name", "Test User"),
        "email": overrides.get("email", _unique_email()),
        "phone": overrides.get("phone", "0900-000-000"),
        "company": overrides.get("company", "Example Corp"),
        "status": overrides.get("status", "active"),
        "notes": overrides.get("notes", "This is a test entry."),
    }
    response = client.post("/customers", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def test_healthcheck(client: TestClient):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_create_and_get_customer(client: TestClient):
    created = _create_customer(client, name="Alice", company="Wonderland", status="prospect")
    customer_id = created["id"]

    response = client.get(f"/customers/{customer_id}")
    assert response.status_code == 200
    fetched = response.json()

    assert fetched["name"] == "Alice"
    assert fetched["company"] == "Wonderland"
    assert fetched["status"] == "prospect"


def test_list_customers_filters(client: TestClient):
    _create_customer(client, name="Alice Johnson", status="prospect", company="Acme")
    _create_customer(client, name="Bob Smith", status="customer", company="Beta")

    response = client.get("/customers", params={"search": "alice"})
    assert response.status_code == 200
    names = [item["name"].lower() for item in response.json()]
    assert any("alice" in name for name in names)

    response = client.get("/customers", params={"status": "prospect"})
    assert response.status_code == 200
    statuses = {item["status"] for item in response.json()}
    assert statuses == {"prospect"}

    response = client.get("/customers", params={"company": "Beta"})
    assert response.status_code == 200
    companies = {item["company"] for item in response.json()}
    assert companies == {"Beta"}

    response = client.get("/customers", params={"limit": 1})
    assert response.status_code == 200
    assert len(response.json()) == 1


def test_update_customer(client: TestClient):
    customer = _create_customer(client, name="Charlie", status="lead")
    customer_id = customer["id"]

    response = client.put(
        f"/customers/{customer_id}",
        json={"phone": "022-123456", "status": "customer"},
    )
    assert response.status_code == 200
    updated = response.json()
    assert updated["phone"] == "022-123456"
    assert updated["status"] == "customer"
    assert updated["updated_at"] >= updated["created_at"]


def test_interactions_flow(client: TestClient):
    customer = _create_customer(client, name="Dora")
    customer_id = customer["id"]

    response = client.post(
        f"/customers/{customer_id}/interactions",
        json={"interaction_type": "call", "subject": "Follow up", "notes": "Discussed pricing."},
    )
    assert response.status_code == 201
    interaction = response.json()
    assert interaction["interaction_type"] == "call"
    assert interaction["customer_id"] == customer_id

    response = client.get(f"/customers/{customer_id}/interactions")
    assert response.status_code == 200
    interactions = response.json()
    assert len(interactions) == 1
    assert interactions[0]["id"] == interaction["id"]

    response = client.get("/interactions")
    assert response.status_code == 200
    assert any(item["id"] == interaction["id"] for item in response.json())


def test_delete_customer(client: TestClient):
    customer = _create_customer(client, name="Eve")
    customer_id = customer["id"]

    response = client.delete(f"/customers/{customer_id}")
    assert response.status_code == 204

    response = client.get(f"/customers/{customer_id}")
    assert response.status_code == 404
