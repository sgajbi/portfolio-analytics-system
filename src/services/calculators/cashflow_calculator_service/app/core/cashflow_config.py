from enum import Enum
from pydantic import BaseModel, Field

# --- Cashflow Attribute Enums ---

class CashflowTiming(str, Enum):
    """Defines if the cashflow occurs at the beginning or end of the day."""
    BOD = "BOD"  # Beginning of Day
    EOD = "EOD"  # End of Day

class CashflowCalculationType(str, Enum):
    """Defines the method used to calculate the cashflow amount."""
    NET = "NET"
    GROSS = "GROSS"
    MVT = "MVT"  # Market Value Transaction

class CashflowClassification(str, Enum):
    """Standardized classification of the cashflow's purpose."""
    INVESTMENT_OUTFLOW = "INVESTMENT_OUTFLOW"
    INVESTMENT_INFLOW = "INVESTMENT_INFLOW"
    INCOME = "INCOME"
    EXPENSE = "EXPENSE"
    CASHFLOW_IN = "CASHFLOW_IN"
    CASHFLOW_OUT = "CASHFLOW_OUT"
    INTERNAL = "INTERNAL" # For flows with no net external impact

# --- Configuration Model ---

class CashflowRule(BaseModel):
    """Defines the cashflow calculation rule for a specific transaction type."""
    classification: CashflowClassification
    timing: CashflowTiming = CashflowTiming.EOD
    calc_type: CashflowCalculationType = CashflowCalculationType.NET
    is_position_flow: bool = Field(..., description="Does this flow affect the specific instrument's cashflow?")
    is_portfolio_flow: bool = Field(..., description="Does this flow represent an external contribution/withdrawal from the portfolio?")

# --- Central Configuration Mapping ---

CASHFLOW_CONFIG: dict[str, CashflowRule] = {
    "BUY": CashflowRule(
        classification=CashflowClassification.INVESTMENT_OUTFLOW,
        timing=CashflowTiming.BOD,
        is_position_flow=True,
        is_portfolio_flow=False
    ),
    "SELL": CashflowRule(
        classification=CashflowClassification.INVESTMENT_INFLOW,
        timing=CashflowTiming.EOD,
        is_position_flow=True,
        is_portfolio_flow=False
    ),
    "DIVIDEND": CashflowRule(
        classification=CashflowClassification.INCOME,
        timing=CashflowTiming.BOD,
        is_position_flow=True,
        is_portfolio_flow=False
    ),
    "INTEREST": CashflowRule(
        classification=CashflowClassification.INCOME,
        timing=CashflowTiming.EOD,
        is_position_flow=True,
        is_portfolio_flow=True
    ),
    "FEE": CashflowRule(
        classification=CashflowClassification.EXPENSE,
        timing=CashflowTiming.EOD,
        is_position_flow=True,
        is_portfolio_flow=True
    ),
    "TAX": CashflowRule(
        classification=CashflowClassification.EXPENSE,
        timing=CashflowTiming.EOD,
        is_position_flow=True,
        is_portfolio_flow=True
    ),
    "TRANSFER_IN": CashflowRule(
        classification=CashflowClassification.CASHFLOW_IN,
        timing=CashflowTiming.BOD,
        is_position_flow=True,
        is_portfolio_flow=True
    ),
    "DEPOSIT": CashflowRule(
        classification=CashflowClassification.CASHFLOW_IN,
        timing=CashflowTiming.BOD,
        is_position_flow=True,
        is_portfolio_flow=True
    ),
    "TRANSFER_OUT": CashflowRule(
        classification=CashflowClassification.CASHFLOW_OUT,
        timing=CashflowTiming.EOD,
        is_position_flow=True,
        is_portfolio_flow=True
    ),
    "WITHDRAWAL": CashflowRule(
        classification=CashflowClassification.CASHFLOW_OUT,
        timing=CashflowTiming.EOD,
        is_position_flow=True,
        is_portfolio_flow=True
    ),
}

def get_rule_for_transaction(transaction_type: str) -> CashflowRule | None:
    """
    Retrieves the cashflow rule for a given transaction type.
    Returns None if no specific rule is found.
    """
    return CASHFLOW_CONFIG.get(transaction_type.upper())