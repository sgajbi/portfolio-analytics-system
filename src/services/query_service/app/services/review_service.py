# src/services/query_service/app/services/review_service.py
import logging
import asyncio
from sqlalchemy.ext.asyncio import AsyncSession
from collections import defaultdict
from datetime import date
from typing import Dict

from ..dtos.review_dto import (
    PortfolioReviewRequest,
    PortfolioReviewResponse,
    ReviewSection,
    OverviewSection,
    HoldingsSection,
    TransactionsSection,
    ReviewPerformanceSection,
    ReviewPerformanceResult,
    IncomeAndActivitySection,
)
from ..dtos.summary_dto import (
    SummaryRequest,
    SummarySection as SummarySubSection,
    AllocationDimension,
)
from ..dtos.performance_dto import PerformanceRequest, StandardPeriod as PerfStandardPeriod
from ..dtos.risk_dto import RiskRequest

from .portfolio_service import PortfolioService
from .summary_service import SummaryService
from .performance_service import PerformanceService
from .risk_service import RiskService
from .position_service import PositionService
from .transaction_service import TransactionService
from .instrument_service import InstrumentService

from portfolio_common.monitoring import REVIEW_GENERATION_DURATION_SECONDS

logger = logging.getLogger(__name__)


class ReviewService:
    """
    Orchestrates calls to other services to build a comprehensive portfolio review.
    """

    def __init__(self, db: AsyncSession):
        self.db = db
        self.portfolio_service = PortfolioService(db)
        self.summary_service = SummaryService(db)
        self.performance_service = PerformanceService(db)
        self.risk_service = RiskService(db)
        self.position_service = PositionService(db)
        self.transaction_service = TransactionService(db)
        self.instrument_service = InstrumentService(db)

    async def get_portfolio_review(
        self, portfolio_id: str, request: PortfolioReviewRequest
    ) -> PortfolioReviewResponse:

        with REVIEW_GENERATION_DURATION_SECONDS.labels(portfolio_id=portfolio_id).time():
            logger.info(f"Generating review for portfolio {portfolio_id}")

            portfolio_details = await self.portfolio_service.get_portfolio_by_id(portfolio_id)
            if not portfolio_details:
                raise ValueError(f"Portfolio {portfolio_id} not found")

            tasks = {}
            as_of_date = request.as_of_date
            ytd_period = {"type": "YTD"}

            # --- Task Creation ---
            if (
                ReviewSection.OVERVIEW in request.sections
                or ReviewSection.ALLOCATION in request.sections
                or ReviewSection.INCOME_AND_ACTIVITY in request.sections
            ):
                summary_req = SummaryRequest(
                    as_of_date=as_of_date,
                    period=ytd_period,
                    sections=list(SummarySubSection),
                    allocation_dimensions=list(AllocationDimension),
                )
                tasks["summary"] = self.summary_service.get_portfolio_summary(
                    portfolio_id, summary_req
                )

            if ReviewSection.PERFORMANCE in request.sections:
                perf_periods = [
                    PerfStandardPeriod(type="MTD"),
                    PerfStandardPeriod(type="QTD"),
                    PerfStandardPeriod(type="YTD"),
                    PerfStandardPeriod(type="THREE_YEAR"),
                    PerfStandardPeriod(type="SI", name="Since Inception"),
                ]
                net_perf_req = PerformanceRequest(
                    scope={"as_of_date": as_of_date, "net_or_gross": "NET"}, periods=perf_periods
                )
                gross_perf_req = PerformanceRequest(
                    scope={"as_of_date": as_of_date, "net_or_gross": "GROSS"}, periods=perf_periods
                )
                tasks["performance_net"] = self.performance_service.calculate_performance(
                    portfolio_id, net_perf_req
                )
                tasks["performance_gross"] = self.performance_service.calculate_performance(
                    portfolio_id, gross_perf_req
                )

            if ReviewSection.RISK_ANALYTICS in request.sections:
                risk_req = RiskRequest(
                    scope={"as_of_date": as_of_date, "net_or_gross": "NET"},
                    periods=[{"type": "YTD"}, {"type": "THREE_YEAR"}],
                    metrics=["VOLATILITY", "SHARPE"],
                )
                tasks["risk"] = self.risk_service.calculate_risk(portfolio_id, risk_req)

            if ReviewSection.HOLDINGS in request.sections:
                tasks["holdings"] = self.position_service.get_portfolio_positions(portfolio_id)

            if ReviewSection.TRANSACTIONS in request.sections:
                ytd_start_date = date(as_of_date.year, 1, 1)
                tasks["transactions"] = self.transaction_service.get_transactions(
                    portfolio_id, skip=0, limit=1000, start_date=ytd_start_date, end_date=as_of_date
                )

            results = await asyncio.gather(*tasks.values(), return_exceptions=True)
            results_map = dict(zip(tasks.keys(), results))

            for task_name, result in results_map.items():
                if isinstance(result, Exception):
                    logger.error(
                        f"Sub-service call '{task_name}' failed during review generation.",
                        exc_info=result,
                    )
                    raise result

            # --- Response Assembly ---
            response = PortfolioReviewResponse(portfolio_id=portfolio_id, as_of_date=as_of_date)

            if "summary" in results_map:
                summary_data = results_map["summary"]
                if ReviewSection.OVERVIEW in request.sections:
                    response.overview = OverviewSection(
                        total_market_value=summary_data.wealth.total_market_value
                        if summary_data.wealth
                        else 0.0,
                        total_cash=summary_data.wealth.total_cash if summary_data.wealth else 0.0,
                        risk_profile=portfolio_details.risk_exposure,
                        portfolio_type=portfolio_details.portfolio_type,
                        pnl_summary=summary_data.pnl_summary,
                    )
                if ReviewSection.ALLOCATION in request.sections:
                    response.allocation = summary_data.allocation
                if ReviewSection.INCOME_AND_ACTIVITY in request.sections:
                    response.income_and_activity = IncomeAndActivitySection(
                        income_summary_ytd=summary_data.income_summary.model_dump(),
                        activity_summary_ytd=summary_data.activity_summary.model_dump(),
                    )

            if "performance_net" in results_map:
                net_perf = results_map["performance_net"]
                gross_perf = results_map["performance_gross"]

                if net_perf and net_perf.summary:
                    combined_summary: Dict[str, ReviewPerformanceResult] = {}
                    for period_name, net_result in net_perf.summary.items():
                        gross_result = gross_perf.summary.get(period_name) if gross_perf else None
                        combined_summary[period_name] = ReviewPerformanceResult(
                            start_date=net_result.start_date,
                            end_date=net_result.end_date,
                            net_cumulative_return=net_result.cumulative_return,
                            net_annualized_return=net_result.annualized_return,
                            gross_cumulative_return=gross_result.cumulative_return
                            if gross_result
                            else None,
                            gross_annualized_return=gross_result.annualized_return
                            if gross_result
                            else None,
                        )
                    response.performance = ReviewPerformanceSection(summary=combined_summary)
                else:
                    response.performance = None

            if "risk" in results_map:
                risk_data = results_map["risk"]
                if risk_data and risk_data.results:
                    response.risk_analytics = risk_data
                else:
                    response.risk_analytics = None

            if ReviewSection.HOLDINGS in request.sections:
                holdings_by_asset_class = defaultdict(list)
                if "holdings" in results_map:
                    for pos in results_map["holdings"].positions:
                        asset_class = pos.asset_class or "Unclassified"
                        holdings_by_asset_class[asset_class].append(pos)
                response.holdings = HoldingsSection(holdingsByAssetClass=holdings_by_asset_class)

            if ReviewSection.TRANSACTIONS in request.sections:
                txns_by_asset_class = defaultdict(list)
                if "transactions" in results_map and results_map["transactions"].transactions:
                    sec_ids = {t.security_id for t in results_map["transactions"].transactions}
                    instruments = await self.instrument_service.get_instruments_by_ids(
                        list(sec_ids)
                    )
                    asset_class_map = {inst.security_id: inst.asset_class for inst in instruments}

                    for txn in results_map["transactions"].transactions:
                        asset_class = asset_class_map.get(txn.security_id) or "Unclassified"
                        txns_by_asset_class[asset_class].append(txn)
                response.transactions = TransactionsSection(
                    transactionsByAssetClass=txns_by_asset_class
                )

            logger.info(f"Successfully generated review for portfolio {portfolio_id}")
            return response
