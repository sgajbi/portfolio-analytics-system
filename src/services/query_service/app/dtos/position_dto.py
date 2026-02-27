# services/query-service/app/dtos/position_dto.py
from datetime import date
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field

from .valuation_dto import ValuationData


class Position(BaseModel):
    security_id: str = Field(
        ..., description="Security identifier for the position.", examples=["AAPL.OQ"]
    )
    quantity: float = Field(..., description="Position quantity.", examples=[125.0])
    instrument_name: str = Field(
        ..., description="Instrument display name.", examples=["Apple Inc."]
    )
    position_date: date = Field(
        ..., description="Business date of the position snapshot.", examples=["2025-12-30"]
    )
    asset_class: Optional[str] = Field(
        None, description="Asset class for grouping and reporting.", examples=["Equity"]
    )
    isin: Optional[str] = Field(
        None, description="ISIN instrument identifier.", examples=["US0378331005"]
    )
    currency: Optional[str] = Field(
        None, description="Instrument trading currency (ISO 4217).", examples=["USD"]
    )
    sector: Optional[str] = Field(
        None, description="Instrument sector classification.", examples=["Technology"]
    )
    country_of_risk: Optional[str] = Field(
        None, description="Instrument country of risk (ISO 3166-1 alpha-2).", examples=["US"]
    )
    cost_basis: float = Field(
        ..., description="Cost basis in portfolio base currency.", examples=[15000.0]
    )
    cost_basis_local: Optional[float] = Field(
        None, description="Cost basis in local instrument currency.", examples=[15000.0]
    )
    valuation: Optional[ValuationData] = Field(
        None, description="Valuation details for the position snapshot."
    )
    reprocessing_status: Optional[str] = Field(
        None,
        description="Reprocessing status for this portfolio-security key.",
        examples=["CURRENT", "REPROCESSING"],
    )
    held_since_date: Optional[date] = Field(
        None,
        description="Start date of the current continuous holding period in the active epoch.",
        examples=["2025-01-15"],
    )
    weight: Optional[float] = Field(
        None,
        description="Position weight versus total portfolio market value (0.0 to 1.0).",
        examples=[0.2417],
    )

    model_config = ConfigDict(from_attributes=True)


class PortfolioPositionsResponse(BaseModel):
    portfolio_id: str = Field(..., description="Portfolio identifier.", examples=["PF-001"])
    positions: List[Position] = Field(..., description="Latest positions for the portfolio.")


class PositionHistoryRecord(BaseModel):
    """
    Represents a snapshot of a security's position at a specific point in time,
    as a result of a transaction.
    """

    position_date: date = Field(..., description="The date of this position snapshot.")
    transaction_id: str = Field(
        ..., description="The ID of the transaction that created this position state."
    )
    quantity: float = Field(..., description="The number of shares held as of this record.")

    cost_basis: float = Field(
        ..., description="The total cost basis of the holding as of this record."
    )

    cost_basis_local: Optional[float] = Field(
        None, description="The total cost basis in the instrument's local currency."
    )

    valuation: Optional[ValuationData] = Field(
        None, description="Valuation details for this record."
    )
    reprocessing_status: Optional[str] = Field(
        None,
        description="Reprocessing status for this portfolio-security key.",
        examples=["CURRENT", "REPROCESSING"],
    )

    model_config = ConfigDict(from_attributes=True)


class PortfolioPositionHistoryResponse(BaseModel):
    """
    Represents the API response for a portfolio's position history.
    """

    portfolio_id: str = Field(..., description="The ID of the portfolio.")
    security_id: str = Field(
        ..., description="The security ID for which the history is being returned."
    )
    positions: List[PositionHistoryRecord] = Field(
        ..., description="A time-series list of position records."
    )
