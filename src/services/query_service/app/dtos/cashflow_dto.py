# src/services/query_service/app/dtos/cashflow_dto.py
from pydantic import BaseModel, Field, ConfigDict
from decimal import Decimal
from datetime import date

class CashflowRecord(BaseModel):
    """
    Represents the cashflow details associated with a transaction
    for API responses.
    """
    amount: float
    currency: str
    classification: str
    timing: str
    is_position_flow: bool
    is_portfolio_flow: bool
    calculation_type: str = Field(..., alias="calculationType")

    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True
    )