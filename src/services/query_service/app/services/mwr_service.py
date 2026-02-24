# src/services/query_service/app/services/mwr_service.py
import logging
import asyncio
from datetime import date
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession
from performance_calculator_engine.helpers import resolve_period
from performance_calculator_engine.mwr_calculator import MWRCalculator

from ..repositories.performance_repository import PerformanceRepository
from ..repositories.portfolio_repository import PortfolioRepository
from ..repositories.cashflow_repository import CashflowRepository
from ..dtos.mwr_dto import MWRRequest, MWRResponse, MWRResult, MWRAttributes

logger = logging.getLogger(__name__)


class MWRService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.portfolio_repo = PortfolioRepository(db)
        self.perf_repo = PerformanceRepository(db)
        self.cashflow_repo = CashflowRepository(db)
        self.calculator = MWRCalculator()

    async def calculate_mwr(self, portfolio_id: str, request: MWRRequest) -> MWRResponse:
        portfolio = await self.portfolio_repo.get_by_id(portfolio_id)
        if not portfolio:
            raise ValueError(f"Portfolio {portfolio_id} not found.")

        # Resolve all requested periods into concrete start/end dates
        resolved_periods = [
            resolve_period(
                period_type=p.type,
                name=p.name or p.type,
                from_date=getattr(p, "from_date", None),
                to_date=getattr(p, "to_date", None),
                inception_date=portfolio.open_date,
                as_of_date=request.scope.as_of_date,
            )
            for p in request.periods
        ]

        # Create concurrent tasks to fetch data and calculate MWR for each period
        tasks = [
            self._process_single_period(portfolio_id, name, start, end, request.options.annualize)
            for name, start, end in resolved_periods
        ]
        period_results = await asyncio.gather(*tasks)

        # Assemble the final response
        summary = {name: result for name, result in period_results if result}
        return MWRResponse(scope=request.scope, summary=summary)

    async def _process_single_period(
        self, portfolio_id: str, name: str, start_date: date, end_date: date, annualize: bool
    ) -> tuple[str, MWRResult]:
        # Fetch timeseries for market values and cashflows for the period concurrently
        ts_task = self.perf_repo.get_portfolio_timeseries_for_range(
            portfolio_id, start_date, end_date
        )
        cf_task = self.cashflow_repo.get_external_flows(portfolio_id, start_date, end_date)
        timeseries_data, external_flows = await asyncio.gather(ts_task, cf_task)

        begin_mv = timeseries_data[0].bod_market_value if timeseries_data else Decimal(0)
        end_mv = timeseries_data[-1].eod_market_value if timeseries_data else begin_mv

        # Calculate attributes
        contributions = sum(amount for _, amount in external_flows if amount > 0)
        withdrawals = sum(amount for _, amount in external_flows if amount < 0)
        attributes = MWRAttributes(
            begin_market_value=begin_mv,
            end_market_value=end_mv,
            external_contributions=contributions,
            external_withdrawals=withdrawals,
            cashflow_count=len(external_flows),
        )

        # Perform the MWR calculation
        mwr_result_dict = self.calculator.compute_period_mwr(
            start_date=start_date,
            end_date=end_date,
            begin_mv=begin_mv,
            end_mv=end_mv,
            external_flows_portfolio_sign=external_flows,
            annualize=annualize,
        )

        mwr_result = MWRResult(
            start_date=start_date,
            end_date=end_date,
            attributes=attributes,
            mwr=float(mwr_result_dict["mwr"])
            if mwr_result_dict and mwr_result_dict.get("mwr") is not None
            else None,
            # --- THIS IS THE FIX ---
            # Use .get() to safely access the key, which may be absent for periods < 1 year.
            mwr_annualized=float(mwr_result_dict.get("mwr_annualized"))
            if mwr_result_dict and mwr_result_dict.get("mwr_annualized") is not None
            else None,
        )

        return name, mwr_result
