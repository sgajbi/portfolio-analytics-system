from pydantic import BaseModel, Field, ConfigDict
from decimal import Decimal
from datetime import date
from typing import List

class Position(BaseModel):
    """
    Represents the latest position of a single security.
    """
    security_id: str = Field(..., description="The unique identifier for the security.")
    quantity: Decimal = Field(..., description="The number of shares held.")
    cost_basis: Decimal = Field(..., description="The total cost basis of the holding.")
    instrument_name: str = Field(..., description="The name of the instrument.")
    position_date: date = Field(..., description="The date of the last transaction that affected this position.")
    
    model_config = ConfigDict(
        from_attributes=True # Enables Pydantic to create this model from a database object
    )

class PortfolioPositionsResponse(BaseModel):
    """
    Represents the API response for a portfolio's positions.
    """
    portfolio_id: str = Field(..., description="The ID of the portfolio.")
    positions: List[Position] = Field(..., description="A list of the latest positions held in the portfolio.")