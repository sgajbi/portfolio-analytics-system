# src/services/query_service/app/dtos/risk_dto.py
from pydantic import BaseModel, Field, ConfigDict
from typing import List, Literal, Optional, Dict, Any
from datetime import date

# Reuse the well-defined period models from the performance DTOs for consistency
from .performance_dto import PerformanceRequestPeriod


class RiskRequestScope(BaseModel):
    """Defines the overall context for the risk calculation."""
    as_of_date: date = Field(default_factory=date.today)
    reporting_currency: Optional[str] = None
    net_or_gross: Literal["NET", "GROSS"] = Field("NET", description="Specifies whether to calculate Net or Gross performance returns as the basis for risk metrics.")


class VaROptions(BaseModel):
    """Defines specific options for Value at Risk (VaR) calculations."""
    method: Literal["HISTORICAL", "GAUSSIAN", "CORNISH_FISHER"] = Field("HISTORICAL", description="The statistical method to use for VaR calculation.")
    confidence: float = Field(0.99, gt=0, lt=1, description="The confidence level for the VaR calculation (e.g., 0.99 for 99%).")
    horizon_days: int = Field(1, gt=0, description="The time horizon in days for the VaR calculation.")
    include_expected_shortfall: bool = Field(True, description="If true, also calculates Expected Shortfall (CVaR), the average loss beyond the VaR threshold.")


class RiskOptions(BaseModel):
    """Defines the calculation options applicable to all requested risk metrics."""
    frequency: Literal["DAILY", "WEEKLY", "MONTHLY"] = Field("DAILY", description="The frequency of returns to use for calculations.")
    annualization_factor: Optional[int] = Field(None, description="Overrides the default annualization factor (e.g., 252 for daily). If None, a default is used based on frequency.")
    use_log_returns: bool = Field(False, description="If true, use logarithmic returns; otherwise, use arithmetic returns.")
    risk_free_mode: Literal["ZERO", "ANNUAL_RATE"] = Field("ZERO", description="Method for determining the risk-free rate for Sharpe ratio.")
    risk_free_annual_rate: Optional[float] = Field(None, ge=0, description="The annual risk-free rate to use if mode is 'ANNUAL_RATE'.")
    mar_annual_rate: float = Field(0.0, ge=0, description="The Minimum Acceptable Return (MAR) for the Sortino Ratio, expressed as an annual rate.")
    benchmark_security_id: Optional[str] = Field(None, description="The security ID of the benchmark to use for Beta, Tracking Error, and Information Ratio.")
    var: VaROptions = Field(default_factory=VaROptions, description="Specific options for Value at Risk calculations.")


class RiskRequest(BaseModel):
    """The main request body for the multi-metric risk calculation endpoint."""
    scope: RiskRequestScope
    periods: List[PerformanceRequestPeriod]
    metrics: List[Literal[
        "VOLATILITY", "DRAWDOWN", "SHARPE", "SORTINO",
        "BETA", "TRACKING_ERROR", "INFORMATION_RATIO", "VAR"
    ]]
    options: RiskOptions = Field(default_factory=RiskOptions)


class RiskValue(BaseModel):
    """Represents the result of a single risk metric calculation."""
    value: Optional[float] = None
    details: Optional[Dict[str, Any]] = Field(None, description="Additional details, e.g., drawdown dates or VaR's Expected Shortfall.")


class RiskPeriodResult(BaseModel):
    """Contains all calculated risk metrics for a single requested period."""
    start_date: date
    end_date: date
    metrics: Dict[str, RiskValue]


class RiskResponse(BaseModel):
    """The final, complete response object for a risk query."""
    scope: RiskRequestScope
    results: Dict[str, RiskPeriodResult] = Field(..., description="A dictionary mapping each requested period's name to its calculated risk results.")