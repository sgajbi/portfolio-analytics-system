# src/services/query_service/app/services/review_service.py
import logging
import asyncio
from sqlalchemy.ext.asyncio import AsyncSession
from collections import defaultdict
from datetime import date, timedelta

from ..dtos.review_dto import (
    PortfolioReviewRequest, PortfolioReviewResponse, ReviewSection, OverviewSection,
    HoldingsSection, TransactionsSection
)
from ..dtos.summary_dto import SummaryRequest, AllocationDimension
from ..dtos.performance_dto import PerformanceRequest, StandardPeriod as PerfStandardPeriod
from ..dtos.risk_dto import RiskRequest
from ..dtos.instrument_dto import InstrumentRecord

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

    @REVIEW_GENERATION_DURATION_SECONDS.labels(portfolio_id=...).time()
    async def get_portfolio_review(
        self, portfolio_id: str, request: PortfolioReviewRequest
    ) -> PortfolioReviewResponse:
        
        REVIEW_GENERATION_DURATION_SECONDS.labels(portfolio_id=portfolio_id)
        logger.info(f"Generating review for portfolio {portfolio_id}")

        tasks = {}
        ytd_period = {"type": "YTD"}
        as_of_date = request.as_of_date

        if ReviewSection.OVERVIEW in request.sections or \
           ReviewSection.ALLOCATION in request.sections or \
           ReviewSection.INCOME_AND_ACTIVITY in request.sections:
            summary_req = SummaryRequest(
                as_of_date=as_of_date,
                period=ytd_period,
                sections=["WEALTH", "PNL", "INCOME", "ACTIVITY", "ALLOCATION"],
                allocation_dimensions=list(AllocationDimension)
            )
            tasks['summary'] = self.summary_service.get_portfolio_summary(portfolio_id, summary_req)
            tasks['portfolio_details'] = self.portfolio_service.get_portfolio_by_id(portfolio_id)

        if ReviewSection.PERFORMANCE in request.sections:
            perf_req = PerformanceRequest(
                scope={"as_of_date": as_of_date, "net_or_gross": "NET"},
                periods=[
                    PerfStandardPeriod(type="MTD"), PerfStandardPeriod(type="QTD"),
                    PerfStandardPeriod(type="YTD"), PerfStandardPeriod(type="THREE_YEAR"),
                    PerfStandardPeriod(type="SI", name="Since Inception")
                ],
                options={"include_annualized": True, "include_cumulative": True}
            )
            tasks['performance_net'] = self.performance_service.calculate_performance(portfolio_id, perf_req)
            
            perf_req.scope.net_or_gross = "GROSS"
            tasks['performance_gross'] = self.performance_service.calculate_performance(portfolio_id, perf_req)

        if ReviewSection.RISK_ANALYTICS in request.sections:
            risk_req = RiskRequest(
                scope={"as_of_date": as_of_date, "net_or_gross": "NET"},
                periods=[{"type": "YTD"}, {"type": "THREE_YEAR"}],
                metrics=["VOLATILITY", "SHARPE"]
            )
            tasks['risk'] = self.risk_service.calculate_risk(portfolio_id, risk_req)

        if ReviewSection.HOLDINGS in request.sections:
            tasks['holdings'] = self.position_service.get_portfolio_positions(portfolio_id)

        if ReviewSection.TRANSACTIONS in request.sections:
            ytd_start_date = date(as_of_date.year, 1, 1)
            tasks['transactions'] = self.transaction_service.get_transactions(
                portfolio_id, skip=0, limit=1000, start_date=ytd_start_date, end_date=as_of_date
            )
        
        results = await asyncio.gather(*tasks.values())
        results_map = dict(zip(tasks.keys(), results))

        # --- Assemble Response ---
        response = PortfolioReviewResponse(portfolio_id=portfolio_id, as_of_date=as_of_date)

        if 'summary' in results_map:
            summary_data = results_map['summary']
            portfolio_details = results_map['portfolio_details']
            if ReviewSection.OVERVIEW in request.sections:
                response.overview = OverviewSection(
                    total_market_value=summary_data.wealth.total_market_value,
                    total_cash=summary_data.wealth.total_cash,
                    risk_profile=portfolio_details.risk_exposure,
                    portfolio_type=portfolio_details.portfolio_type,
                    pnl_summary=summary_data.pnl_summary
                )
            if ReviewSection.ALLOCATION in request.sections:
                response.allocation = summary_data.allocation
            if ReviewSection.INCOME_AND_ACTIVITY in request.sections:
                response.income_and_activity = {
                    "income_summary_ytd": summary_data.income_summary,
                    "activity_summary_ytd": summary_data.activity_summary
                }

        if 'performance_net' in results_map:
            response.performance = results_map['performance_net']
            
        if 'risk' in results_map:
            response.risk_analytics = results_map['risk']
        
        # --- NEW: Robust Grouping Logic ---
        if 'holdings' in results_map or 'transactions' in results_map:
            # 1. Collect all unique security IDs from both results
            sec_ids = set()
            if 'holdings' in results_map:
                sec_ids.update(p.security_id for p in results_map['holdings'].positions)
            if 'transactions' in results_map:
                sec_ids.update(t.security_id for t in results_map['transactions'].transactions)
            
            # 2. Fetch all instrument details in a single batch call
            instruments = await self.instrument_service.get_instruments_by_ids(list(sec_ids))
            asset_class_map = {inst.security_id: inst.asset_class for inst in instruments}

            # 3. Group holdings using the fetched asset class data
            if 'holdings' in results_map:
                holdings_by_asset_class = defaultdict(list)
                for pos in results_map['holdings'].positions:
                    asset_class = asset_class_map.get(pos.security_id) or "Unclassified"
                    holdings_by_asset_class[asset_class].append(pos)
                response.holdings = HoldingsSection(holdingsByAssetClass=holdings_by_asset_class)
            
            # 4. Group transactions using the same asset class data
            if 'transactions' in results_map:
                txns_by_asset_class = defaultdict(list)
                for txn in results_map['transactions'].transactions:
                    asset_class = asset_class_map.get(txn.security_id) or "Unclassified"
                    txns_by_asset_class[asset_class].append(txn)
                response.transactions = TransactionsSection(transactionsByAssetClass=txns_by_asset_class)

        return response