from pydantic import BaseModel, ConfigDict
from datetime import date
from typing import List, Optional


class PortfolioRecord(BaseModel):
    """
    Represents a single, detailed portfolio record for API responses.
    """

    portfolio_id: str
    base_currency: str
    open_date: date
    close_date: Optional[date] = None
    risk_exposure: str
    investment_time_horizon: str
    portfolio_type: str
    objective: Optional[str] = None
    booking_center: str
    cif_id: str
    is_leverage_allowed: bool
    advisor_id: Optional[str] = None
    status: str

    model_config = ConfigDict(from_attributes=True)


class PortfolioQueryResponse(BaseModel):
    """
    Represents the API response for a portfolio query.
    """

    portfolios: List[PortfolioRecord]
