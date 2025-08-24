# src/libs/performance-calculator-engine/src/performance_calculator_engine/mwr_calculator.py
from datetime import date
from decimal import Decimal, getcontext
from typing import List, Tuple, Optional

# Set precision for Decimal calculations
getcontext().prec = 28

class MWRCalculator:
    """
    Calculates the Money-Weighted Return (MWR) for a series of cashflows
    using an iterative solver to find the Internal Rate of Return (IRR / XIRR).
    """

    def _npv(self, rate: Decimal, dates: List[date], cashflows: List[Decimal]) -> Decimal:
        """Calculates the Net Present Value for a given rate."""
        total = Decimal(0)
        start_date = dates[0]
        for i in range(len(cashflows)):
            days_diff = Decimal((dates[i] - start_date).days)
            exponent = days_diff / Decimal("365.0")
            total += cashflows[i] / ((Decimal(1) + rate) ** exponent)
        return total

    def _npv_derivative(self, rate: Decimal, dates: List[date], cashflows: List[Decimal]) -> Decimal:
        """Calculates the derivative of the NPV function."""
        total = Decimal(0)
        start_date = dates[0]
        for i in range(len(cashflows)):
            days_diff = Decimal((dates[i] - start_date).days)
            if days_diff == 0:
                continue
            exponent = days_diff / Decimal("365.0")
            denominator = (Decimal(1) + rate) ** (exponent + 1)
            total -= cashflows[i] * exponent / denominator
        return total

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
        if not dated_cashflows_investor_sign or len(dated_cashflows_investor_sign) < 2:
            return None

        # Check for sign change, which is required for a solution to exist
        if all(cf >= 0 for _, cf in dated_cashflows_investor_sign) or all(cf <= 0 for _, cf in dated_cashflows_investor_sign):
            return None

        # Unzip and sort the data by date
        sorted_flows = sorted(dated_cashflows_investor_sign, key=lambda x: x[0])
        dates, cashflows = zip(*sorted_flows)

        rate = Decimal("0.1")  # Initial guess
        for _ in range(max_iter):
            npv_val = self._npv(rate, dates, cashflows)
            if abs(npv_val) < tol:
                return rate

            derivative_val = self._npv_derivative(rate, dates, cashflows)
            if derivative_val == 0:
                return None  # No solution

            rate = rate - (npv_val / derivative_val)

        return None # Failed to converge

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