from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
import sys

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.database import Base, get_db
from app.main import app

TEST_DATABASE_URL = "sqlite+pysqlite:///:memory:"

engine = create_engine(
    TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db


@pytest.fixture(autouse=True)
def setup_database():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield


@pytest.fixture
def client() -> TestClient:
    with TestClient(app) as test_client:
        yield test_client


def test_create_and_retrieve_customer(client: TestClient) -> None:
    payload = {
        "name": "Alice Example",
        "email": "alice@example.com",
        "phone": "123456789",
        "company": "Example Corp",
        "status": "lead",
        "tags": ["vip", "newsletter"],
        "notes": "Important new lead.",
    }
    response = client.post("/customers", json=payload)
    assert response.status_code == 201
    created = response.json()
    assert created["id"] > 0
    assert created["name"] == payload["name"]
    assert set(created["tags"]) == {"newsletter", "vip"}

    response = client.get(f"/customers/{created['id']}")
    assert response.status_code == 200
    fetched = response.json()
    assert fetched["email"] == payload["email"]
    assert fetched["notes"] == payload["notes"]


def test_list_customers_with_filters(client: TestClient) -> None:
    customer_one = {
        "name": "Bob Builder",
        "email": "bob@example.com",
        "status": "prospect",
        "company": "BuildIt",
        "tags": ["contractor"],
    }
    customer_two = {
        "name": "Charlie Consultant",
        "email": "charlie@example.com",
        "status": "lead",
        "company": "Advisors Inc",
        "tags": ["vip"],
    }
    for payload in (customer_one, customer_two):
        assert client.post("/customers", json=payload).status_code == 201

    response = client.get("/customers")
    assert response.status_code == 200
    assert len(response.json()) == 2

    response = client.get("/customers", params={"status": "lead"})
    assert response.status_code == 200
    results = response.json()
    assert len(results) == 1
    assert results[0]["email"] == "charlie@example.com"

    response = client.get("/customers", params={"search": "build"})
    assert response.status_code == 200
    results = response.json()
    assert len(results) == 1
    assert results[0]["email"] == "bob@example.com"

    response = client.get("/customers", params={"tag": "vip"})
    assert response.status_code == 200
    results = response.json()
    assert len(results) == 1
    assert results[0]["email"] == "charlie@example.com"


def test_interactions_workflow(client: TestClient) -> None:
    customer = client.post(
        "/customers",
        json={"name": "Dana", "email": "dana@example.com", "status": "lead"},
    ).json()
    customer_id = customer["id"]

    create_response = client.post(
        f"/customers/{customer_id}/interactions",
        json={
            "subject": "Intro Call",
            "interaction_type": "call",
            "medium": "phone",
            "notes": "Discussed project scope",
        },
    )
    assert create_response.status_code == 201
    interaction = create_response.json()
    assert interaction["subject"] == "Intro Call"

    update_response = client.put(
        f"/customers/{customer_id}/interactions/{interaction['id']}",
        json={"notes": "Call went well"},
    )
    assert update_response.status_code == 200
    assert update_response.json()["notes"] == "Call went well"

    list_response = client.get(f"/customers/{customer_id}/interactions")
    assert list_response.status_code == 200
    assert len(list_response.json()) == 1

    delete_response = client.delete(
        f"/customers/{customer_id}/interactions/{interaction['id']}"
    )
    assert delete_response.status_code == 204
    assert client.get(f"/customers/{customer_id}/interactions").json() == []


def test_opportunities_tasks_and_analytics(client: TestClient) -> None:
    today = date.today()
    customer = client.post(
        "/customers",
        json={"name": "Eve", "email": "eve@example.com", "status": "prospect"},
    ).json()
    customer_id = customer["id"]

    opportunity_response = client.post(
        f"/customers/{customer_id}/opportunities",
        json={
            "name": "New Project",
            "value": 5000.0,
            "status": "proposal",
            "probability": 60,
        },
    )
    assert opportunity_response.status_code == 201
    opportunity = opportunity_response.json()

    update_opportunity = client.put(
        f"/customers/{customer_id}/opportunities/{opportunity['id']}",
        json={"status": "won"},
    )
    assert update_opportunity.status_code == 200
    assert update_opportunity.json()["status"] == "won"

    task_future = client.post(
        f"/customers/{customer_id}/tasks",
        json={
            "title": "Send contract",
            "due_date": (today + timedelta(days=3)).isoformat(),
            "status": "in_progress",
        },
    ).json()
    assert task_future["status"] == "in_progress"

    task_overdue_response = client.post(
        f"/customers/{customer_id}/tasks",
        json={
            "title": "Follow-up email",
            "due_date": (today - timedelta(days=1)).isoformat(),
            "status": "todo",
        },
    )
    assert task_overdue_response.status_code == 201

    update_task = client.put(
        f"/customers/{customer_id}/tasks/{task_future['id']}",
        json={"status": "done"},
    )
    assert update_task.status_code == 200
    assert update_task.json()["status"] == "done"

    # Add a second customer to ensure analytics counts leads correctly
    client.post(
        "/customers",
        json={"name": "Frank", "email": "frank@example.com", "status": "lead"},
    )

    analytics = client.get("/analytics/overview").json()
    assert analytics["total_customers"] == 2
    assert analytics["leads"] == 1
    assert analytics["active_opportunities"] == 1
    assert analytics["won_opportunities"] == 1
    assert analytics["overdue_tasks"] == 1

    # Clean up by deleting a task and verifying removal
    overdue_task_id = task_overdue_response.json()["id"]
    delete_task_resp = client.delete(f"/customers/{customer_id}/tasks/{overdue_task_id}")
    assert delete_task_resp.status_code == 204
    tasks_remaining = client.get(f"/customers/{customer_id}/tasks").json()
    assert len(tasks_remaining) == 1
    assert tasks_remaining[0]["id"] == task_future["id"]
