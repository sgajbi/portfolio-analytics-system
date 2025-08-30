# src/services/query_service/app/services/summary_service.py
import logging
import asyncio
from datetime import date, timedelta
from decimal import Decimal
from typing import List, Any, Dict
from collections import defaultdict

from sqlalchemy.ext.asyncio import AsyncSession
from performance_calculator_engine.helpers import resolve_period

from ..repositories.summary_repository import SummaryRepository
from ..repositories.portfolio_repository import PortfolioRepository
from ..dtos.summary_dto import (
    SummaryRequest, SummaryResponse, ResponseScope, WealthSummary,
    AllocationSummary, AllocationGroup, AllocationDimension, SummarySection,
    PnlSummary, IncomeSummary, ActivitySummary
)
from portfolio_common.database_models import Portfolio, DailyPositionSnapshot, Instrument, Cashflow, Transaction
# --- NEW IMPORT ---
from portfolio_common.monitoring import UNCLASSIFIED_ALLOCATION_MARKET_VALUE

logger = logging.getLogger(__name__)

class SummaryService:
    """
    Handles the business logic for creating a portfolio summary.
    """
    def __init__(self, db: AsyncSession):
        self.db = db
        self.summary_repo = SummaryRepository(db)
        self.portfolio_repo = PortfolioRepository(db)

    def _calculate_allocation_by_dimension(
        self,
        positions_data: List[Any],
        dimension: AllocationDimension,
        total_market_value: Decimal,
        as_of_date: date,
        portfolio_id: str # Pass portfolio_id for metric labels
    ) -> List[AllocationGroup]:
        if total_market_value == 0: return []
        grouped_allocation: Dict[str, Decimal] = defaultdict(Decimal)
        dimension_map = {
            AllocationDimension.ASSET_CLASS: 'asset_class', AllocationDimension.CURRENCY: 'currency',
            AllocationDimension.SECTOR: 'sector', AllocationDimension.COUNTRY_OF_RISK: 'country_of_risk',
            AllocationDimension.RATING: 'rating',
        }
        attribute_name = dimension_map.get(dimension)
        for snapshot, instrument in positions_data:
            market_value = snapshot.market_value or Decimal(0)
            group_key = "Unclassified"
            if attribute_name:
                group_key = getattr(instrument, attribute_name) or "Unclassified"
            elif dimension == AllocationDimension.MATURITY_BUCKET:
                if instrument.maturity_date and instrument.asset_class == 'Fixed Income':
                    years_to_maturity = (instrument.maturity_date - as_of_date).days / 365.25
                    if years_to_maturity <= 1: group_key = '0-1Y'
                    elif years_to_maturity <= 3: group_key = '1-3Y'
                    elif years_to_maturity <= 5: group_key = '3-5Y'
                    elif years_to_maturity <= 10: group_key = '5-10Y'
                    else: group_key = '10Y+'
                else: group_key = "N/A"
            grouped_allocation[group_key] += market_value
        
        # --- THIS IS THE FIX ---
        unclassified_value = grouped_allocation.get("Unclassified", Decimal(0))
        UNCLASSIFIED_ALLOCATION_MARKET_VALUE.labels(
            portfolio_id=portfolio_id,
            dimension=dimension.value
        ).set(float(unclassified_value))
        # --- END FIX ---

        return [
            AllocationGroup(
                group=key, market_value=value,
                weight=round(float(value / total_market_value), 4) if total_market_value else 0
            ) for key, value in sorted(grouped_allocation.items())
        ]

    async def get_portfolio_summary(
        self, portfolio_id: str, request: SummaryRequest
    ) -> SummaryResponse:
        portfolio = await self.portfolio_repo.get_by_id(portfolio_id)
        if not portfolio: raise ValueError(f"Portfolio {portfolio_id} not found")

        _, start_date, end_date = resolve_period(
            period_type=request.period.type, name=request.period.name,
            from_date=getattr(request.period, 'from_date', None), to_date=getattr(request.period, 'to_date', None),
            year=getattr(request.period, 'year', None), inception_date=portfolio.open_date, as_of_date=request.as_of_date
        )
        scope = ResponseScope(
            portfolio_id=portfolio_id, as_of_date=request.as_of_date,
            period_start_date=start_date, period_end_date=end_date
        )
        tasks = {
            "positions": self.summary_repo.get_wealth_and_allocation_data(portfolio_id, request.as_of_date),
            "cashflows": self.summary_repo.get_cashflows_for_period(portfolio_id, start_date, end_date),
            "realized_pnl": self.summary_repo.get_realized_pnl(portfolio_id, start_date, end_date),
            "unrealized_pnl_start": self.summary_repo.get_total_unrealized_pnl(portfolio_id, start_date - timedelta(days=1)),
            "unrealized_pnl_end": self.summary_repo.get_total_unrealized_pnl(portfolio_id, end_date),
        }
        results = await asyncio.gather(*tasks.values())
        data = dict(zip(tasks.keys(), results))
        
        wealth_summary, pnl_summary, income_summary, activity_summary, allocation_summary = None, None, None, None, None

        if SummarySection.WEALTH in request.sections or SummarySection.ALLOCATION in request.sections:
            total_mv = sum(s.market_value or Decimal(0) for s, i in data["positions"])
            total_cash = sum(s.market_value or Decimal(0) for s, i in data["positions"] if i.product_type == 'Cash')
            wealth_summary = WealthSummary(total_market_value=total_mv, total_cash=total_cash)
        if SummarySection.ALLOCATION in request.sections and request.allocation_dimensions and data["positions"]:
            allocation_dict = {
                f"by_{dim.value.lower()}": self._calculate_allocation_by_dimension(
                    data["positions"], dim, wealth_summary.total_market_value, request.as_of_date, portfolio_id
                ) for dim in request.allocation_dimensions
            }
            allocation_summary = AllocationSummary.model_validate(allocation_dict)
        if any(s in request.sections for s in [SummarySection.PNL, SummarySection.INCOME, SummarySection.ACTIVITY]):
            raw_cashflows: List[Cashflow] = data["cashflows"]
            
            totals = defaultdict(Decimal)
            for cf in raw_cashflows:
                if cf.classification == "TRANSFER":
                    if cf.amount > 0: totals["TRANSFER_IN"] += cf.amount
                    else: totals["TRANSFER_OUT"] += cf.amount
                elif cf.classification == "INCOME":
                    if cf.transaction and cf.transaction.transaction_type == "INTEREST":
                        totals["INTEREST_INCOME"] += cf.amount
                    else:
                        totals["DIVIDEND_INCOME"] += cf.amount
                else:
                    totals[cf.classification] += cf.amount
            
            if SummarySection.ACTIVITY in request.sections:
                activity_summary = ActivitySummary(
                    total_deposits=totals["CASHFLOW_IN"], total_withdrawals=totals["CASHFLOW_OUT"],
                    total_transfers_in=totals["TRANSFER_IN"], total_transfers_out=totals["TRANSFER_OUT"],
                    total_fees=totals["EXPENSE"]
                )
            if SummarySection.INCOME in request.sections:
                income_summary = IncomeSummary(
                    total_dividends=totals["DIVIDEND_INCOME"], total_interest=totals["INTEREST_INCOME"]
                )
            if SummarySection.PNL in request.sections:
                net_new_money = totals["CASHFLOW_IN"] + totals["CASHFLOW_OUT"] + totals["TRANSFER_IN"] + totals["TRANSFER_OUT"]
                unrealized_pnl_change = data["unrealized_pnl_end"] - data["unrealized_pnl_start"]
                realized_pnl = data["realized_pnl"]
                pnl_summary = PnlSummary(
                    net_new_money=net_new_money, realized_pnl=realized_pnl,
                    unrealized_pnl_change=unrealized_pnl_change,
                    total_pnl=realized_pnl + unrealized_pnl_change
                )
        return SummaryResponse(
            scope=scope, wealth=wealth_summary if SummarySection.WEALTH in request.sections else None,
            pnlSummary=pnl_summary, incomeSummary=income_summary,
            activitySummary=activity_summary, allocation=allocation_summary
        )