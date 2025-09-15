"""Data access helpers for the CRM API."""
from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Sequence

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from . import models, schemas


def _tags_to_string(tags: Sequence[str] | None) -> str:
    if not tags:
        return ""
    return ",".join(sorted({tag.strip() for tag in tags if tag.strip()}))


def get_customer(db: Session, customer_id: int) -> models.Customer | None:
    return db.get(models.Customer, customer_id)


def get_customers(
    db: Session,
    *,
    skip: int = 0,
    limit: int = 100,
    status: str | None = None,
    search: str | None = None,
    tag: str | None = None,
) -> list[models.Customer]:
    stmt = select(models.Customer).order_by(models.Customer.created_at.desc())
    if status:
        stmt = stmt.where(models.Customer.status == status)
    if search:
        like_term = f"%{search.lower()}%"
        stmt = stmt.where(
            or_(
                func.lower(models.Customer.name).like(like_term),
                func.lower(models.Customer.email).like(like_term),
                func.lower(models.Customer.company).like(like_term),
            )
        )
    if tag:
        like_tag = f"%{tag.lower()}%"
        stmt = stmt.where(func.lower(models.Customer.tags).like(like_tag))

    stmt = stmt.offset(skip).limit(limit)
    return list(db.scalars(stmt))


def create_customer(db: Session, customer_in: schemas.CustomerCreate) -> models.Customer:
    customer = models.Customer(
        name=customer_in.name,
        email=customer_in.email,
        phone=customer_in.phone,
        company=customer_in.company,
        status=customer_in.status,
        tags=_tags_to_string(customer_in.tags),
        notes=customer_in.notes,
    )
    db.add(customer)
    db.commit()
    db.refresh(customer)
    return customer


def update_customer(
    db: Session, *, customer: models.Customer, customer_in: schemas.CustomerUpdate
) -> models.Customer:
    update_data = customer_in.model_dump(exclude_unset=True)
    if "tags" in update_data:
        update_data["tags"] = _tags_to_string(update_data.get("tags"))
    for field, value in update_data.items():
        setattr(customer, field, value)
    customer.updated_at = datetime.now(UTC)
    db.add(customer)
    db.commit()
    db.refresh(customer)
    return customer


def delete_customer(db: Session, *, customer: models.Customer) -> None:
    db.delete(customer)
    db.commit()


def create_interaction(
    db: Session, *, customer: models.Customer, interaction_in: schemas.InteractionCreate
) -> models.Interaction:
    interaction = models.Interaction(
        customer_id=customer.id,
        subject=interaction_in.subject,
        interaction_type=interaction_in.interaction_type,
        medium=interaction_in.medium,
        notes=interaction_in.notes,
        occurred_at=interaction_in.occurred_at or datetime.now(UTC),
    )
    db.add(interaction)
    db.commit()
    db.refresh(interaction)
    return interaction


def update_interaction(
    db: Session, *, interaction: models.Interaction, interaction_in: schemas.InteractionUpdate
) -> models.Interaction:
    update_data = interaction_in.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        if value is not None:
            setattr(interaction, field, value)
    db.add(interaction)
    db.commit()
    db.refresh(interaction)
    return interaction


def delete_interaction(db: Session, interaction: models.Interaction) -> None:
    db.delete(interaction)
    db.commit()


def create_opportunity(
    db: Session, *, customer: models.Customer, opportunity_in: schemas.OpportunityCreate
) -> models.Opportunity:
    opportunity = models.Opportunity(
        customer_id=customer.id,
        name=opportunity_in.name,
        description=opportunity_in.description,
        value=opportunity_in.value,
        status=opportunity_in.status,
        probability=opportunity_in.probability,
        expected_close_date=opportunity_in.expected_close_date,
    )
    db.add(opportunity)
    db.commit()
    db.refresh(opportunity)
    return opportunity


def update_opportunity(
    db: Session, *, opportunity: models.Opportunity, opportunity_in: schemas.OpportunityUpdate
) -> models.Opportunity:
    update_data = opportunity_in.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        if value is not None:
            setattr(opportunity, field, value)
    opportunity.updated_at = datetime.now(UTC)
    db.add(opportunity)
    db.commit()
    db.refresh(opportunity)
    return opportunity


def delete_opportunity(db: Session, opportunity: models.Opportunity) -> None:
    db.delete(opportunity)
    db.commit()


def create_task(
    db: Session, *, customer: models.Customer, task_in: schemas.TaskCreate
) -> models.Task:
    task = models.Task(
        customer_id=customer.id,
        title=task_in.title,
        description=task_in.description,
        due_date=task_in.due_date,
        status=task_in.status,
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


def update_task(db: Session, *, task: models.Task, task_in: schemas.TaskUpdate) -> models.Task:
    update_data = task_in.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        if value is not None:
            setattr(task, field, value)
    task.updated_at = datetime.now(UTC)
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


def delete_task(db: Session, task: models.Task) -> None:
    db.delete(task)
    db.commit()


def get_customer_summary(db: Session, customer: models.Customer) -> schemas.CustomerSummary:
    return schemas.CustomerSummary.model_validate(customer)


def get_analytics_snapshot(db: Session) -> schemas.AnalyticsSnapshot:
    total_customers = db.scalar(select(func.count()).select_from(models.Customer)) or 0
    leads = (
        db.scalar(
            select(func.count()).select_from(models.Customer).where(models.Customer.status == "lead")
        )
        or 0
    )
    active_opportunities = (
        db.scalar(
            select(func.count())
            .select_from(models.Opportunity)
            .where(models.Opportunity.status != "lost")
        )
        or 0
    )
    won_opportunities = (
        db.scalar(
            select(func.count())
            .select_from(models.Opportunity)
            .where(models.Opportunity.status == "won")
        )
        or 0
    )
    overdue_tasks = (
        db.scalar(
            select(func.count())
            .select_from(models.Task)
            .where(
                models.Task.due_date.is_not(None),
                models.Task.status != models.TaskStatus.DONE,
                models.Task.due_date < date.today(),
            )
        )
        or 0
    )

    return schemas.AnalyticsSnapshot(
        total_customers=total_customers,
        leads=leads,
        active_opportunities=active_opportunities,
        won_opportunities=won_opportunities,
        overdue_tasks=overdue_tasks,
    )
