# src/services/query_service/app/dtos/concentration_dto.py
from datetime import date
from typing import List, Literal, Optional, Dict, Any
from pydantic import BaseModel, Field

# --- Request DTOs ---

class ConcentrationRequestScope(BaseModel):
    """Defines the overall context for the concentration calculation."""
    as_of_date: date
    reporting_currency: str = Field("USD", description="ISO currency code for reporting.")

class ConcentrationRequestOptions(BaseModel):
    """Defines the calculation options for the concentration metrics."""
    lookthrough_enabled: bool = Field(True, description="Enable look-through for fund holdings.")
    issuer_top_n: int = Field(10, gt=0, description="The number of top issuer exposures to return.")
    bulk_top_n: List[int] = Field([5, 10], description="A list of 'N' values for Top-N bulk concentration.")

class ConcentrationRequest(BaseModel):
    """The main request body for the concentration calculation endpoint."""
    scope: ConcentrationRequestScope
    metrics: List[Literal["ISSUER", "BULK"]]
    options: ConcentrationRequestOptions = Field(default_factory=ConcentrationRequestOptions)


# --- Response DTOs ---

class Finding(BaseModel):
    """Represents a single concentration finding that exceeds a threshold."""
    level: Literal["WARN", "BREACH"]
    message: str

class ResponseSummary(BaseModel):
    """Contains high-level summary information for the concentration report."""
    portfolio_market_value: float
    findings: List[Finding]

class IssuerExposure(BaseModel):
    """Represents the exposure to a single issuer."""
    issuer_name: str
    exposure: float
    weight: float
    flag: Optional[Literal["WARN", "BREACH"]] = None

class IssuerConcentration(BaseModel):
    """Contains the results for the issuer concentration metric."""
    top_exposures: List[IssuerExposure]

class BulkConcentration(BaseModel):
    """Contains the results for the bulk concentration metrics."""
    top_n_weights: Dict[str, float]
    single_position_weight: float
    hhi: float
    flag: Optional[Literal["WARN", "BREACH"]] = None

class ConcentrationResponse(BaseModel):
    """The final, complete response object for a concentration query."""
    scope: ConcentrationRequestScope
    summary: ResponseSummary
    issuer_concentration: Optional[IssuerConcentration] = None
    bulk_concentration: Optional[BulkConcentration] = None