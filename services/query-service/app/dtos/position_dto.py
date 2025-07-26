from pydantic import BaseModel, Field, ConfigDict
from decimal import Decimal
from datetime import date
from typing import List

# DTO for the "latest positions" endpoint
class Position(BaseModel):
    security_id: str
    quantity: Decimal
    cost_basis: Decimal
    instrument_name: str
    position_date: date
    
    model_config = ConfigDict(from_attributes=True)

# Response DTO for the "latest positions" endpoint
class PortfolioPositionsResponse(BaseModel):
    portfolio_id: str
    positions: List[Position]

# --- DTOs for the "position history" endpoint ---

class PositionHistoryRecord(BaseModel):
    """
    Represents a snapshot of a security's position at a specific point in time,
    as a result of a transaction.
    """
    position_date: date = Field(..., description="The date of this position snapshot.")
    transaction_id: str = Field(..., description="The ID of the transaction that created this position state.")
    quantity: Decimal = Field(..., description="The number of shares held as of this record.")
    cost_basis: Decimal = Field(..., description="The total cost basis of the holding as of this record.")
    
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