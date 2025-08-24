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
    ) -> Optional[dict]:
        """
        Builds investor-sign timeline:
        CF(t0) = -begin_mv, CF(flows) = -flow_amount, CF(tN) = +end_mv,
        solves XIRR with actual day-count exponents, and returns the results.
        """
        # 1. Build the cashflow timeline in "investor sign" convention
        timeline = []
        
        # Initial investment (outflow from investor's perspective)
        if begin_mv > 0:
            timeline.append((start_date, -begin_mv))
            
        # Intermediate flows (portfolio inflow is investor outflow, hence negate)
        for flow_date, flow_amount in external_flows_portfolio_sign:
            timeline.append((flow_date, -flow_amount))
            
        # Final value (inflow to investor's perspective)
        if end_mv > 0:
            timeline.append((end_date, end_mv))

        # Coalesce flows on the same day
        coalesced_timeline_dict = {}
        for d, cf in timeline:
            coalesced_timeline_dict[d] = coalesced_timeline_dict.get(d, Decimal(0)) + cf
        
        coalesced_timeline = list(coalesced_timeline_dict.items())

        # 2. Solve for XIRR
        mwr = self.compute_xirr(coalesced_timeline)

        if mwr is None:
            return None

        # 3. Handle annualization
        mwr_annualized = None
        period_days = (end_date - start_date).days
        if annualize:
             # XIRR is already annualized due to the (days/365) exponent.
             # Conventionally, we don't show an annualized figure for periods under a year.
            if period_days >= 365:
                mwr_annualized = mwr

        return {
            "mwr": mwr,
            "mwr_annualized": mwr_annualized,
        }