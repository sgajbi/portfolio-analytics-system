from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator


class CoreSnapshotMode(str, Enum):
    BASELINE = "BASELINE"
    SIMULATION = "SIMULATION"


class CoreSnapshotSection(str, Enum):
    POSITIONS_BASELINE = "positions_baseline"
    POSITIONS_PROJECTED = "positions_projected"
    POSITIONS_DELTA = "positions_delta"
    PORTFOLIO_TOTALS = "portfolio_totals"
    INSTRUMENT_ENRICHMENT = "instrument_enrichment"


class CoreSnapshotPositionBasis(str, Enum):
    MARKET_VALUE_BASE = "market_value_base"


class CoreSnapshotWeightBasis(str, Enum):
    TOTAL_MARKET_VALUE_BASE = "total_market_value_base"


class CoreSnapshotSimulationOptions(BaseModel):
    session_id: str = Field(..., description="Simulation session identifier.", examples=["SIM_0001"])
    expected_version: Optional[int] = Field(
        None,
        description="Optional optimistic lock for simulation version.",
        examples=[3],
    )


class CoreSnapshotRequestOptions(BaseModel):
    include_zero_quantity_positions: bool = Field(
        False,
        description="Include positions with zero quantity in section responses.",
    )
    include_cash_positions: bool = Field(
        True,
        description="Include cash-class positions in section responses.",
    )
    position_basis: CoreSnapshotPositionBasis = Field(
        CoreSnapshotPositionBasis.MARKET_VALUE_BASE,
        description="Basis used for position valuation fields.",
    )
    weight_basis: CoreSnapshotWeightBasis = Field(
        CoreSnapshotWeightBasis.TOTAL_MARKET_VALUE_BASE,
        description="Basis used to calculate weight fields.",
    )


class CoreSnapshotRequest(BaseModel):
    as_of_date: date = Field(..., description="Business date for snapshot resolution.")
    snapshot_mode: CoreSnapshotMode = Field(
        CoreSnapshotMode.BASELINE,
        description="Snapshot mode: BASELINE or SIMULATION.",
    )
    reporting_currency: Optional[str] = Field(
        None,
        description="ISO currency code for reporting conversion. Defaults to portfolio base currency.",
        examples=["USD"],
    )
    sections: list[CoreSnapshotSection] = Field(
        ...,
        description="Requested snapshot sections.",
    )
    simulation: Optional[CoreSnapshotSimulationOptions] = Field(
        None,
        description="Simulation options required for SIMULATION mode.",
    )
    options: CoreSnapshotRequestOptions = Field(
        default_factory=CoreSnapshotRequestOptions,
        description="Section behavior options.",
    )

    @model_validator(mode="after")
    def validate_request(self):
        if not self.sections:
            raise ValueError("sections must contain at least one value")
        if self.snapshot_mode == CoreSnapshotMode.SIMULATION and self.simulation is None:
            raise ValueError("simulation.session_id is required for SIMULATION mode")
        if self.snapshot_mode == CoreSnapshotMode.BASELINE and self.simulation is not None:
            raise ValueError("simulation block is not allowed for BASELINE mode")
        return self


class CoreSnapshotValuationContext(BaseModel):
    portfolio_currency: str = Field(..., description="Portfolio base currency.")
    reporting_currency: str = Field(..., description="Reporting currency for value fields.")
    position_basis: CoreSnapshotPositionBasis = Field(...)
    weight_basis: CoreSnapshotWeightBasis = Field(...)


class CoreSnapshotSimulationMetadata(BaseModel):
    session_id: str = Field(...)
    version: int = Field(...)
    baseline_as_of_date: date = Field(...)


class CoreSnapshotPositionRecord(BaseModel):
    security_id: str = Field(..., examples=["AAPL.OQ"])
    quantity: Decimal = Field(..., examples=["100.0000000000"])
    market_value_base: Optional[Decimal] = Field(None, examples=["19500.25"])
    market_value_local: Optional[Decimal] = Field(None, examples=["18000.00"])
    weight: Optional[Decimal] = Field(None, examples=["0.1245"])
    currency: Optional[str] = Field(None, examples=["USD"])


class CoreSnapshotDeltaRecord(BaseModel):
    security_id: str = Field(..., examples=["AAPL.OQ"])
    baseline_quantity: Decimal = Field(..., examples=["100.0000000000"])
    projected_quantity: Decimal = Field(..., examples=["120.0000000000"])
    delta_quantity: Decimal = Field(..., examples=["20.0000000000"])
    baseline_market_value_base: Optional[Decimal] = Field(None, examples=["19500.25"])
    projected_market_value_base: Optional[Decimal] = Field(None, examples=["23400.30"])
    delta_market_value_base: Optional[Decimal] = Field(None, examples=["3900.05"])
    delta_weight: Optional[Decimal] = Field(None, examples=["0.0175"])


class CoreSnapshotInstrumentEnrichmentRecord(BaseModel):
    security_id: str = Field(...)
    isin: Optional[str] = Field(None)
    asset_class: Optional[str] = Field(None)
    sector: Optional[str] = Field(None)
    country_of_risk: Optional[str] = Field(None)
    instrument_name: Optional[str] = Field(None)


class CoreSnapshotPortfolioTotals(BaseModel):
    baseline_total_market_value_base: Optional[Decimal] = Field(None)
    projected_total_market_value_base: Optional[Decimal] = Field(None)
    delta_total_market_value_base: Optional[Decimal] = Field(None)


class CoreSnapshotSections(BaseModel):
    positions_baseline: Optional[list[CoreSnapshotPositionRecord]] = None
    positions_projected: Optional[list[CoreSnapshotPositionRecord]] = None
    positions_delta: Optional[list[CoreSnapshotDeltaRecord]] = None
    portfolio_totals: Optional[CoreSnapshotPortfolioTotals] = None
    instrument_enrichment: Optional[list[CoreSnapshotInstrumentEnrichmentRecord]] = None


class CoreSnapshotResponse(BaseModel):
    portfolio_id: str = Field(...)
    as_of_date: date = Field(...)
    snapshot_mode: CoreSnapshotMode = Field(...)
    generated_at: datetime = Field(...)
    valuation_context: CoreSnapshotValuationContext = Field(...)
    simulation: Optional[CoreSnapshotSimulationMetadata] = Field(None)
    sections: CoreSnapshotSections = Field(...)

    model_config = ConfigDict()
