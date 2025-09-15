"""FastAPI entry-point exposing CRM functionality."""
from __future__ import annotations

from fastapi import Depends, FastAPI, HTTPException, Query, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import crud, models, schemas
from .database import Base, engine, get_db

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Simple CRM", version="1.0.0")


def _get_customer_or_404(db: Session, customer_id: int) -> models.Customer:
    customer = crud.get_customer(db, customer_id=customer_id)
    if not customer:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Customer not found")
    return customer


@app.get("/health", tags=["system"])
def health_check() -> dict[str, str]:
    """Return a simple payload used for health checking."""

    return {"status": "ok"}


@app.get(
    "/customers",
    response_model=list[schemas.CustomerSummary],
    tags=["customers"],
)
def list_customers(
    *,
    db: Session = Depends(get_db),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    status: str | None = Query(default=None, description="Filter customers by status"),
    search: str | None = Query(default=None, description="Search by name, email or company"),
    tag: str | None = Query(default=None, description="Filter customers by tag"),
) -> list[schemas.CustomerSummary]:
    customers = crud.get_customers(
        db,
        skip=skip,
        limit=limit,
        status=status,
        search=search,
        tag=tag,
    )
    return [schemas.CustomerSummary.model_validate(customer) for customer in customers]


@app.post(
    "/customers",
    response_model=schemas.Customer,
    status_code=status.HTTP_201_CREATED,
    tags=["customers"],
)
def create_customer(
    customer_in: schemas.CustomerCreate, *, db: Session = Depends(get_db)
) -> schemas.Customer:
    customer = crud.create_customer(db, customer_in=customer_in)
    return schemas.Customer.model_validate(customer)


@app.get(
    "/customers/{customer_id}",
    response_model=schemas.Customer,
    tags=["customers"],
)
def get_customer(customer_id: int, *, db: Session = Depends(get_db)) -> schemas.Customer:
    customer = _get_customer_or_404(db, customer_id)
    return schemas.Customer.model_validate(customer)


@app.put(
    "/customers/{customer_id}",
    response_model=schemas.Customer,
    tags=["customers"],
)
def update_customer(
    customer_id: int,
    customer_in: schemas.CustomerUpdate,
    *,
    db: Session = Depends(get_db),
) -> schemas.Customer:
    customer = _get_customer_or_404(db, customer_id)
    customer = crud.update_customer(db, customer=customer, customer_in=customer_in)
    return schemas.Customer.model_validate(customer)


@app.delete(
    "/customers/{customer_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    tags=["customers"],
)
def delete_customer(customer_id: int, *, db: Session = Depends(get_db)) -> Response:
    customer = _get_customer_or_404(db, customer_id)
    crud.delete_customer(db, customer=customer)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@app.get(
    "/customers/{customer_id}/interactions",
    response_model=list[schemas.Interaction],
    tags=["interactions"],
)
def list_interactions(customer_id: int, *, db: Session = Depends(get_db)) -> list[schemas.Interaction]:
    customer = _get_customer_or_404(db, customer_id)
    stmt = (
        select(models.Interaction)
        .where(models.Interaction.customer_id == customer.id)
        .order_by(models.Interaction.occurred_at.desc())
    )
    interactions = list(db.scalars(stmt))
    return [schemas.Interaction.model_validate(interaction) for interaction in interactions]


@app.post(
    "/customers/{customer_id}/interactions",
    response_model=schemas.Interaction,
    status_code=status.HTTP_201_CREATED,
    tags=["interactions"],
)
def create_interaction(
    customer_id: int,
    interaction_in: schemas.InteractionCreate,
    *,
    db: Session = Depends(get_db),
) -> schemas.Interaction:
    customer = _get_customer_or_404(db, customer_id)
    interaction = crud.create_interaction(db, customer=customer, interaction_in=interaction_in)
    return schemas.Interaction.model_validate(interaction)


@app.put(
    "/customers/{customer_id}/interactions/{interaction_id}",
    response_model=schemas.Interaction,
    tags=["interactions"],
)
def update_interaction(
    customer_id: int,
    interaction_id: int,
    interaction_in: schemas.InteractionUpdate,
    *,
    db: Session = Depends(get_db),
) -> schemas.Interaction:
    _get_customer_or_404(db, customer_id)
    interaction = db.get(models.Interaction, interaction_id)
    if not interaction or interaction.customer_id != customer_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Interaction not found")
    interaction = crud.update_interaction(db, interaction=interaction, interaction_in=interaction_in)
    return schemas.Interaction.model_validate(interaction)


@app.delete(
    "/customers/{customer_id}/interactions/{interaction_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    tags=["interactions"],
)
def delete_interaction(
    customer_id: int, interaction_id: int, *, db: Session = Depends(get_db)
) -> Response:
    _get_customer_or_404(db, customer_id)
    interaction = db.get(models.Interaction, interaction_id)
    if not interaction or interaction.customer_id != customer_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Interaction not found")
    crud.delete_interaction(db, interaction)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@app.get(
    "/customers/{customer_id}/opportunities",
    response_model=list[schemas.Opportunity],
    tags=["opportunities"],
)
def list_opportunities(customer_id: int, *, db: Session = Depends(get_db)) -> list[schemas.Opportunity]:
    customer = _get_customer_or_404(db, customer_id)
    stmt = (
        select(models.Opportunity)
        .where(models.Opportunity.customer_id == customer.id)
        .order_by(models.Opportunity.created_at.desc())
    )
    opportunities = list(db.scalars(stmt))
    return [schemas.Opportunity.model_validate(opp) for opp in opportunities]


@app.post(
    "/customers/{customer_id}/opportunities",
    response_model=schemas.Opportunity,
    status_code=status.HTTP_201_CREATED,
    tags=["opportunities"],
)
def create_opportunity(
    customer_id: int,
    opportunity_in: schemas.OpportunityCreate,
    *,
    db: Session = Depends(get_db),
) -> schemas.Opportunity:
    customer = _get_customer_or_404(db, customer_id)
    opportunity = crud.create_opportunity(db, customer=customer, opportunity_in=opportunity_in)
    return schemas.Opportunity.model_validate(opportunity)


@app.put(
    "/customers/{customer_id}/opportunities/{opportunity_id}",
    response_model=schemas.Opportunity,
    tags=["opportunities"],
)
def update_opportunity(
    customer_id: int,
    opportunity_id: int,
    opportunity_in: schemas.OpportunityUpdate,
    *,
    db: Session = Depends(get_db),
) -> schemas.Opportunity:
    _get_customer_or_404(db, customer_id)
    opportunity = db.get(models.Opportunity, opportunity_id)
    if not opportunity or opportunity.customer_id != customer_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Opportunity not found")
    opportunity = crud.update_opportunity(db, opportunity=opportunity, opportunity_in=opportunity_in)
    return schemas.Opportunity.model_validate(opportunity)


@app.delete(
    "/customers/{customer_id}/opportunities/{opportunity_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    tags=["opportunities"],
)
def delete_opportunity(
    customer_id: int, opportunity_id: int, *, db: Session = Depends(get_db)
) -> Response:
    _get_customer_or_404(db, customer_id)
    opportunity = db.get(models.Opportunity, opportunity_id)
    if not opportunity or opportunity.customer_id != customer_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Opportunity not found")
    crud.delete_opportunity(db, opportunity)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@app.get(
    "/customers/{customer_id}/tasks",
    response_model=list[schemas.Task],
    tags=["tasks"],
)
def list_tasks(customer_id: int, *, db: Session = Depends(get_db)) -> list[schemas.Task]:
    customer = _get_customer_or_404(db, customer_id)
    stmt = (
        select(models.Task)
        .where(models.Task.customer_id == customer.id)
        .order_by(models.Task.due_date.is_(None), models.Task.due_date.asc())
    )
    tasks = list(db.scalars(stmt))
    return [schemas.Task.model_validate(task) for task in tasks]


@app.post(
    "/customers/{customer_id}/tasks",
    response_model=schemas.Task,
    status_code=status.HTTP_201_CREATED,
    tags=["tasks"],
)
def create_task(
    customer_id: int,
    task_in: schemas.TaskCreate,
    *,
    db: Session = Depends(get_db),
) -> schemas.Task:
    customer = _get_customer_or_404(db, customer_id)
    task = crud.create_task(db, customer=customer, task_in=task_in)
    return schemas.Task.model_validate(task)


@app.put(
    "/customers/{customer_id}/tasks/{task_id}",
    response_model=schemas.Task,
    tags=["tasks"],
)
def update_task(
    customer_id: int,
    task_id: int,
    task_in: schemas.TaskUpdate,
    *,
    db: Session = Depends(get_db),
) -> schemas.Task:
    _get_customer_or_404(db, customer_id)
    task = db.get(models.Task, task_id)
    if not task or task.customer_id != customer_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
    task = crud.update_task(db, task=task, task_in=task_in)
    return schemas.Task.model_validate(task)


@app.delete(
    "/customers/{customer_id}/tasks/{task_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    tags=["tasks"],
)
def delete_task(customer_id: int, task_id: int, *, db: Session = Depends(get_db)) -> Response:
    _get_customer_or_404(db, customer_id)
    task = db.get(models.Task, task_id)
    if not task or task.customer_id != customer_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
    crud.delete_task(db, task)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@app.get("/analytics/overview", response_model=schemas.AnalyticsSnapshot, tags=["analytics"])
def analytics_overview(*, db: Session = Depends(get_db)) -> schemas.AnalyticsSnapshot:
    return crud.get_analytics_snapshot(db)
