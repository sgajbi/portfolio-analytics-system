# src/services/query_service/app/dtos/mwr_dto.py
from pydantic import BaseModel, Field, ConfigDict
from typing import List, Literal, Union, Optional, Dict, Annotated
from datetime import date
from decimal import Decimal

# --- API Request Models ---


class MWRRequestScope(BaseModel):
    """Defines the overall context for the MWR calculation."""

    as_of_date: date = Field(
        default_factory=date.today,
        description="The reference date for relative calculations like MTD, YTD. Defaults to today.",
    )


class MWRExplicitPeriod(BaseModel):
    """Defines a custom period with explicit start and end dates."""

    type: Literal["EXPLICIT"]
    name: Optional[str] = Field(
        None, description="A unique name for this period, used as a key in the response."
    )
    from_date: date = Field(
        ..., alias="from", description="The start date of the period (inclusive)."
    )
    to_date: date = Field(..., alias="to", description="The end date of the period (inclusive).")


class MWRStandardPeriod(BaseModel):
    """Defines standard, relative period types."""

    type: Literal["MTD", "QTD", "YTD", "SI"]
    name: Optional[str] = Field(
        None, description="A unique name for this period, used as a key in the response."
    )


# A discriminated union to handle different types of period requests
MWRRequestPeriod = Annotated[
    Union[MWRExplicitPeriod, MWRStandardPeriod], Field(discriminator="type")
]


class MWRRequestOptions(BaseModel):
    """Defines options for tailoring the response."""

    annualize: bool = Field(True, description="Specifies whether to annualize the MWR result.")


class MWRRequest(BaseModel):
    """The main request body for the MWR calculation endpoint."""

    scope: MWRRequestScope
    periods: List[MWRRequestPeriod]
    options: MWRRequestOptions = Field(default_factory=MWRRequestOptions)

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "scope": {"as_of_date": "2025-08-24"},
                "periods": [
                    {"name": "Year to Date", "type": "YTD"},
                    {
                        "name": "Custom Period",
                        "type": "EXPLICIT",
                        "from": "2025-07-01",
                        "to": "2025-08-24",
                    },
                ],
                "options": {"annualize": True},
            }
        }
    )


# --- API Response Models ---


class MWRAttributes(BaseModel):
    """Holds the raw financial attributes for a given period."""

    begin_market_value: Decimal
    end_market_value: Decimal
    external_contributions: Decimal
    external_withdrawals: Decimal
    cashflow_count: int

    model_config = ConfigDict(from_attributes=True, arbitrary_types_allowed=True)


class MWRResult(BaseModel):
    """Contains the calculated MWR and attributes for a single period."""

    start_date: date
    end_date: date
    mwr: Optional[float] = Field(
        None, description="The solved Money-Weighted Rate of Return for the period."
    )
    mwr_annualized: Optional[float] = Field(None, description="The annualized MWR, if applicable.")
    attributes: MWRAttributes

    model_config = ConfigDict(from_attributes=True, arbitrary_types_allowed=True)


class MWRResponse(BaseModel):
    """The final, complete response object for an MWR query."""

    scope: MWRRequestScope
    summary: Dict[str, MWRResult] = Field(
        ..., description="A dictionary mapping the requested period name to its summary result."
    )
