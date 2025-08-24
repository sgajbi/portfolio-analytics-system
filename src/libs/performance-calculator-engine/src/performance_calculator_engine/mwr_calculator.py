# src/libs/performance-calculator-engine/src/performance_calculator_engine/mwr_calculator.py
from datetime import date
from decimal import Decimal
from typing import List, Tuple, Optional

class MWRCalculator:
    """
    Calculates the Money-Weighted Return (MWR) for a series of cashflows
    using an iterative solver to find the Internal Rate of Return (IRR / XIRR).
    """

    def compute_xirr(
        self,
        dated_cashflows_investor_sign: List[Tuple[date, Decimal]],
        tol: Decimal = Decimal("1e-9"),
        max_iter: int = 100
    ) -> Optional[Decimal]:
        """
        Returns periodic IRR (per annum if using day-count exponent), or None if not solvable.
        Input cashflows must be in INVESTOR SIGN (outflows negative, inflows positive).
        """
        # To be implemented
        return None

    def compute_period_mwr(
        self,
        start_date: date,
        end_date: date,
        begin_mv: Decimal,
        end_mv: Decimal,
        external_flows_portfolio_sign: List[Tuple[date, Decimal]],
        annualize: bool = True
    ) -> dict:
        """
        Builds investor-sign timeline:
        CF(t0) = -begin_mv, CF(flows) = -flow_amount, CF(tN) = +end_mv,
        solves XIRR with actual day-count exponents, returns:
        { "mwr": Decimal, "mwr_annualized": Decimal|None, "count": int }
        """
        # To be implemented
        return {}