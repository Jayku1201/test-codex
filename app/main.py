"""FastAPI application exposing CRM endpoints."""
from __future__ import annotations

from typing import List, Optional

from fastapi import Depends, FastAPI, HTTPException, Query, Response, status
from fastapi.middleware.cors import CORSMiddleware

from . import crud, schemas
from .database import get_db, init_db

app = FastAPI(
    title="Simple CRM API",
    description="一個簡易的客戶關係管理（CRM）系統，提供客戶與互動紀錄的基本CRUD功能。",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def startup() -> None:
    init_db()


@app.get("/health", response_model=schemas.HealthResponse)
def healthcheck() -> schemas.HealthResponse:
    return schemas.HealthResponse(status="ok")


@app.post("/customers", response_model=schemas.Customer, status_code=status.HTTP_201_CREATED)
def create_customer(
    payload: schemas.CustomerCreate,
    connection=Depends(get_db),
) -> schemas.Customer:
    try:
        customer = crud.create_customer(connection, payload)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return customer


@app.get("/customers", response_model=List[schemas.Customer])
def list_customers(
    search: Optional[str] = Query(default=None, description="依姓名、Email、電話或公司模糊查詢"),
    status_filter: Optional[str] = Query(default=None, alias="status", description="依客戶狀態篩選"),
    company: Optional[str] = Query(default=None, description="依公司名稱篩選"),
    limit: int = Query(default=20, ge=1, le=100, description="單頁筆數，最多100筆"),
    offset: int = Query(default=0, ge=0, description="起始索引"),
    sort_by: str = Query(default="created_at", description="排序欄位"),
    sort_order: str = Query(default="desc", description="排序方向（asc/desc）"),
    connection=Depends(get_db),
) -> List[schemas.Customer]:
    return crud.list_customers(
        connection,
        search=search,
        status=status_filter,
        company=company,
        limit=limit,
        offset=offset,
        sort_by=sort_by,
        sort_order=sort_order,
    )


@app.get("/customers/{customer_id}", response_model=schemas.Customer)
def get_customer(customer_id: int, connection=Depends(get_db)) -> schemas.Customer:
    customer = crud.get_customer(connection, customer_id)
    if not customer:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Customer not found")
    return customer


@app.put("/customers/{customer_id}", response_model=schemas.Customer)
def update_customer(
    customer_id: int,
    payload: schemas.CustomerUpdate,
    connection=Depends(get_db),
) -> schemas.Customer:
    try:
        customer = crud.update_customer(connection, customer_id, payload)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    if not customer:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Customer not found")
    return customer


@app.delete("/customers/{customer_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_customer(customer_id: int, connection=Depends(get_db)) -> Response:
    deleted = crud.delete_customer(connection, customer_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Customer not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@app.get("/customers/{customer_id}/interactions", response_model=List[schemas.Interaction])
def list_customer_interactions(customer_id: int, connection=Depends(get_db)) -> List[schemas.Interaction]:
    if not crud.get_customer(connection, customer_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Customer not found")
    return crud.list_interactions(connection, customer_id=customer_id)


@app.post(
    "/customers/{customer_id}/interactions",
    response_model=schemas.Interaction,
    status_code=status.HTTP_201_CREATED,
)
def create_customer_interaction(
    customer_id: int,
    payload: schemas.InteractionCreate,
    connection=Depends(get_db),
) -> schemas.Interaction:
    interaction = crud.create_interaction(connection, customer_id, payload)
    if not interaction:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Customer not found")
    return interaction


@app.get("/interactions", response_model=List[schemas.Interaction])
def list_interactions(connection=Depends(get_db)) -> List[schemas.Interaction]:
    return crud.list_interactions(connection)
