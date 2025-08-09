from pydantic import BaseModel, Field, ConfigDict
from datetime import date
from typing import List, Optional

class Portfolio(BaseModel):
    """
    Represents a single portfolio for ingestion.
    """
    portfolio_id: str = Field(..., alias="portfolioId")
    base_currency: str = Field(..., alias="baseCurrency")
    open_date: date = Field(..., alias="openDate")
    close_date: Optional[date] = Field(None, alias="closeDate")
    risk_exposure: str = Field(..., alias="riskExposure")
    investment_time_horizon: str = Field(..., alias="investmentTimeHorizon")
    portfolio_type: str = Field(..., alias="portfolioType")
    objective: Optional[str] = None
    booking_center: str = Field(..., alias="bookingCenter")
    cif_id: str = Field(..., alias="cifId")
    is_leverage_allowed: bool = Field(False, alias="isLeverageAllowed")
    advisor_id: Optional[str] = Field(None, alias="advisorId")
    status: str

    model_config = ConfigDict(
        populate_by_name=True,
        json_schema_extra={
            "example": {
                "portfolioId": "PORT_001",
                "baseCurrency": "USD",
                "openDate": "2024-01-01",
                "riskExposure": "Medium",
                "investmentTimeHorizon": "Long",
                "portfolioType": "Discretionary",
                "bookingCenter": "Singapore",
                "cifId": "CIF_12345",
                "status": "Active"
            }
        }
    )

class PortfolioIngestionRequest(BaseModel):
    """
    Represents the request body for ingesting a list of portfolios.
    """
    portfolios: List[Portfolio]