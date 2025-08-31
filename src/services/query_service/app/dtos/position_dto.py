# services/query-service/app/dtos/position_dto.py
from pydantic import BaseModel, Field, ConfigDict
from decimal import Decimal
from datetime import date
from typing import List, Optional

from .valuation_dto import ValuationData

class Position(BaseModel):
    security_id: str
    quantity: Decimal
    instrument_name: str
    position_date: date
    asset_class: Optional[str] = None # ADDED: New field for direct asset class info
    
    cost_basis: Decimal
    
    cost_basis_local: Optional[Decimal] = None
    
    valuation: Optional[ValuationData] = None
    reprocessing_status: Optional[str] = None
    
    model_config = ConfigDict(from_attributes=True)

class PortfolioPositionsResponse(BaseModel):
    portfolio_id: str
    positions: List[Position]


class PositionHistoryRecord(BaseModel):
    """
    Represents a snapshot of a security's position at a specific point in time,
    as a result of a transaction.
    """
    position_date: date = Field(..., description="The date of this position snapshot.")
    transaction_id: str = Field(..., description="The ID of the transaction that created this position state.")
    quantity: Decimal = Field(..., description="The number of shares held as of this record.")
    
    cost_basis: Decimal = Field(..., description="The total cost basis of the holding as of this record.")
    
    cost_basis_local: Optional[Decimal] = Field(None, description="The total cost basis in the instrument's local currency.")

    valuation: Optional[ValuationData] = None
    reprocessing_status: Optional[str] = None
    
    model_config = ConfigDict(
        from_attributes=True
    )

class PortfolioPositionHistoryResponse(BaseModel):
    """
    Represents the API response for a portfolio's position history.
    """
    portfolio_id: str = Field(..., description="The ID of the portfolio.")
    security_id: str = Field(..., description="The security ID for which the history is being returned.")
    positions: List[PositionHistoryRecord] = Field(..., description="A time-series list of position records.")