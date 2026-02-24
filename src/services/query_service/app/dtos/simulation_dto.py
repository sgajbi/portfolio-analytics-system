# services/query-service/app/dtos/simulation_dto.py
from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class SimulationSessionCreateRequest(BaseModel):
    portfolio_id: str = Field(..., min_length=1)
    created_by: str | None = None
    ttl_hours: int = Field(default=24, ge=1, le=168)


class SimulationSessionRecord(BaseModel):
    session_id: str
    portfolio_id: str
    status: str
    version: int
    created_by: str | None = None
    created_at: datetime
    expires_at: datetime

    model_config = ConfigDict(from_attributes=True)


class SimulationSessionResponse(BaseModel):
    session: SimulationSessionRecord


class SimulationChangeInput(BaseModel):
    security_id: str = Field(..., min_length=1)
    transaction_type: str = Field(..., min_length=1)
    quantity: float | None = None
    price: float | None = None
    amount: float | None = None
    currency: str | None = None
    effective_date: date | None = None
    metadata: dict[str, Any] | None = None


class SimulationChangeUpsertRequest(BaseModel):
    changes: list[SimulationChangeInput] = Field(default_factory=list)


class SimulationChangeRecord(BaseModel):
    change_id: str
    session_id: str
    portfolio_id: str
    security_id: str
    transaction_type: str
    quantity: float | None = None
    price: float | None = None
    amount: float | None = None
    currency: str | None = None
    effective_date: date | None = None
    metadata: dict[str, Any] | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class SimulationChangesResponse(BaseModel):
    session_id: str
    version: int
    changes: list[SimulationChangeRecord]


class ProjectedPositionRecord(BaseModel):
    security_id: str
    instrument_name: str
    asset_class: str | None = None
    baseline_quantity: float
    proposed_quantity: float
    delta_quantity: float
    cost_basis: float | None = None
    cost_basis_local: float | None = None


class ProjectedPositionsResponse(BaseModel):
    session_id: str
    portfolio_id: str
    baseline_as_of: date | None = None
    positions: list[ProjectedPositionRecord]


class ProjectedSummaryResponse(BaseModel):
    session_id: str
    portfolio_id: str
    total_baseline_positions: int
    total_proposed_positions: int
    net_delta_quantity: float
