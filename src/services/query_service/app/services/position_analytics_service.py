# src/services/query_service/app/services/position_analytics_service.py
import logging
import asyncio
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import Depends
from decimal import Decimal
from typing import Any, List, Optional, Dict
import pandas as pd
from datetime import date

from portfolio_common.db import get_async_db_session
from ..dtos.position_analytics_dto import (
    PositionAnalyticsRequest, PositionAnalyticsResponse, EnrichedPosition,
    PositionAnalyticsSection, MonetaryAmount, PositionValuation, PositionInstrumentDetails,
    PositionPerformance, PositionValuationDetail
)
from ..repositories.position_repository import PositionRepository
from ..repositories.portfolio_repository import PortfolioRepository
from ..repositories.cashflow_repository import CashflowRepository
from ..repositories.performance_repository import PerformanceRepository
from ..repositories.fx_rate_repository import FxRateRepository
from performance_calculator_engine.helpers import resolve_period
from performance_calculator_engine.calculator import PerformanceCalculator
from performance_calculator_engine.constants import FINAL_CUMULATIVE_ROR_PCT
from portfolio_common.monitoring import (
    POSITION_ANALYTICS_DURATION_SECONDS,
    POSITION_ANALYTICS_SECTION_REQUESTED_TOTAL,
)

logger = logging.getLogger(__name__)

class PositionAnalyticsService:
    """
    Orchestrates the data fetching and calculation for position-level analytics.
    """
    def __init__(self, db: AsyncSession):
        self.db = db
        self.position_repo = PositionRepository(db)
        self.portfolio_repo = PortfolioRepository(db)
        self.cashflow_repo = CashflowRepository(db)
        self.perf_repo = PerformanceRepository(db)
        self.fx_repo = FxRateRepository(db)

    def _convert_timeseries_to_dict(self, timeseries_data: List[Any]) -> List[Dict]:
        return [
            {
                "date": r.date.isoformat(), "bod_market_value": r.bod_market_value,
                "eod_market_value": r.eod_market_value, "bod_cashflow": r.bod_cashflow_position,
                "eod_cashflow": r.eod_cashflow_position, "fees": r.fees,
            }
            for r in timeseries_data
        ]

    async def _calculate_performance(
        self,
        portfolio_id: str, security_id: str, instrument_currency: str,
        base_currency: str, inception_date: date, request: PositionAnalyticsRequest
    ) -> Optional[Dict[str, PositionPerformance]]:
        if not request.performance_options:
            return None

        periods = [resolve_period(p, inception_date, request.as_of_date) for p in request.performance_options.periods]
        min_start = min(p[1] for p in periods) if periods else request.as_of_date
        
        timeseries_data = await self.perf_repo.get_position_timeseries_for_range(
            portfolio_id, security_id, min_start, request.as_of_date
        )
        if not timeseries_data:
            return {name: PositionPerformance() for name, _, _ in periods}

        ts_dicts = self._convert_timeseries_to_dict(timeseries_data)
        
        results = {}
        for name, start_date, end_date in periods:
            period_ts_data = [ts for ts in ts_dicts if start_date <= date.fromisoformat(ts['date']) <= end_date]
            if not period_ts_data:
                results[name] = PositionPerformance()
                continue
            
            config = { "metric_basis": "NET", "period_type": "EXPLICIT", "performance_start_date": inception_date.isoformat(), "report_start_date": start_date.isoformat(), "report_end_date": end_date.isoformat() }
            calculator = PerformanceCalculator(config=config)
            df_local = calculator.calculate_performance(period_ts_data)
            local_return = float(df_local.iloc[-1][FINAL_CUMULATIVE_ROR_PCT]) if not df_local.empty else None

            base_return = local_return
            if instrument_currency != base_currency:
                fx_rates_db = await self.fx_repo.get_fx_rates(instrument_currency, base_currency, start_date, end_date)
                if fx_rates_db:
                    fx_series = pd.Series({r.rate_date: r.rate for r in fx_rates_db}).astype(float)
                    df_local['date_dt'] = pd.to_datetime(df_local['date'])
                    df_merged = pd.merge(df_local, fx_series.rename('fx_rate'), left_on='date_dt', right_index=True, how='left').ffill()
                    
                    if 'fx_rate' in df_merged.columns and not df_merged['fx_rate'].isnull().all():
                        df_base = df_merged.copy()
                        for col in ['bod_market_value', 'eod_market_value', 'bod_cashflow', 'eod_cashflow']:
                            df_base[col] = df_base[col] * df_base['fx_rate']
                        
                        base_ts_dicts = df_base.to_dict('records')
                        df_base_result = calculator.calculate_performance(base_ts_dicts)
                        base_return = float(df_base_result.iloc[-1][FINAL_CUMULATIVE_ROR_PCT]) if not df_base_result.empty else local_return
            
            results[name] = PositionPerformance(localReturn=local_return, baseReturn=base_return)
            
        return results


    async def _enrich_position(
        self, portfolio: Any, total_market_value_base: Decimal, repo_row: Any, request: PositionAnalyticsRequest
    ) -> EnrichedPosition:
        (
            snapshot, instrument_name, reprocessing_status, isin,
            currency, asset_class, sector, country_of_risk, epoch
        ) = repo_row

        market_value_base = snapshot.market_value or Decimal(0)
        position = EnrichedPosition(
            securityId=snapshot.security_id, quantity=float(snapshot.quantity),
            weight=float(market_value_base / total_market_value_base) if total_market_value_base else 0.0,
            held_since_date=snapshot.date
        )

        enrichment_tasks = {}
        if PositionAnalyticsSection.BASE in request.sections or PositionAnalyticsSection.INCOME in request.sections:
            enrichment_tasks['held_since_date'] = self.position_repo.get_held_since_date(portfolio.portfolio_id, snapshot.security_id, epoch)
        
        if PositionAnalyticsSection.PERFORMANCE in request.sections:
            enrichment_tasks['performance'] = self._calculate_performance(
                portfolio.portfolio_id, snapshot.security_id, currency, portfolio.base_currency,
                portfolio.open_date, request
            )
        
        task_results = await asyncio.gather(*enrichment_tasks.values(), return_exceptions=True)
        results_map = dict(zip(enrichment_tasks.keys(), task_results))
        
        if isinstance(results_map.get('held_since_date'), date):
            position.held_since_date = results_map['held_since_date']
        if isinstance(results_map.get('performance'), dict):
            position.performance = results_map['performance']

        income_tasks = {}
        if PositionAnalyticsSection.INCOME in request.sections:
            income_tasks['income_cashflows'] = self.cashflow_repo.get_income_cashflows_for_position(
                portfolio.portfolio_id, snapshot.security_id, position.held_since_date, request.as_of_date
            )
        
        income_results = await asyncio.gather(*income_tasks.values())
        income_map = dict(zip(income_tasks.keys(), income_results))

        if 'income_cashflows' in income_map:
            cashflows = income_map['income_cashflows']
            total_income_local = sum(cf.amount for cf in cashflows)
            
            total_income_base = total_income_local
            if currency != portfolio.base_currency and cashflows:
                min_cf_date = min(cf.cashflow_date for cf in cashflows)
                fx_rates_db = await self.fx_repo.get_fx_rates(currency, portfolio.base_currency, min_cf_date, request.as_of_date)
                fx_rates = {r.rate_date: r.rate for r in fx_rates_db}
                
                # Forward fill missing FX rates
                ffill_series = pd.Series(fx_rates).reindex(pd.date_range(min_cf_date, request.as_of_date, freq='D')).ffill()
                # --- THIS IS THE FIX ---
                # Convert the pandas Timestamps in the index back to date objects for the dictionary keys.
                filled_fx = {idx.date(): val for idx, val in ffill_series.items() if pd.notna(val)}
                # --- END FIX ---
                total_income_base = sum(cf.amount * filled_fx.get(cf.cashflow_date, Decimal(1)) for cf in cashflows)

            position.income = PositionValuationDetail(
                local=MonetaryAmount(amount=float(total_income_local), currency=currency),
                base=MonetaryAmount(amount=float(total_income_base), currency=portfolio.base_currency)
            )
        
        if PositionAnalyticsSection.INSTRUMENT_DETAILS in request.sections:
            position.instrument_details = PositionInstrumentDetails(
                name=instrument_name, isin=isin, assetClass=asset_class,
                sector=sector, countryOfRisk=country_of_risk, currency=currency
            )

        if PositionAnalyticsSection.VALUATION in request.sections:
            position.valuation = PositionValuation(
                marketValue=PositionValuationDetail(
                    local=MonetaryAmount(amount=float(snapshot.market_value_local or 0), currency=currency),
                    base=MonetaryAmount(amount=float(snapshot.market_value or 0), currency=portfolio.base_currency)
                ),
                costBasis=PositionValuationDetail(
                    local=MonetaryAmount(amount=float(snapshot.cost_basis_local or 0), currency=currency),
                    base=MonetaryAmount(amount=float(snapshot.cost_basis or 0), currency=portfolio.base_currency)
                ),
                unrealizedPnl=PositionValuationDetail(
                    local=MonetaryAmount(amount=float(snapshot.unrealized_gain_loss_local or 0), currency=currency),
                    base=MonetaryAmount(amount=float(snapshot.unrealized_gain_loss or 0), currency=portfolio.base_currency)
                )
            )
        return position

    async def get_position_analytics(
        self, portfolio_id: str, request: PositionAnalyticsRequest
    ) -> PositionAnalyticsResponse:
        with POSITION_ANALYTICS_DURATION_SECONDS.labels(portfolio_id=portfolio_id).time():
            logger.info(
                "Starting position analytics generation for portfolio %s",
                portfolio_id,
                extra={"sections": [s.value for s in request.sections]},
            )
            for section in request.sections:
                POSITION_ANALYTICS_SECTION_REQUESTED_TOTAL.labels(section_name=section.value).inc()

            portfolio = await self.portfolio_repo.get_by_id(portfolio_id)
            if not portfolio:
                raise ValueError(f"Portfolio {portfolio_id} not found")

            repo_results = await self.position_repo.get_latest_positions_by_portfolio(portfolio_id)

            if not repo_results:
                return PositionAnalyticsResponse(
                    portfolio_id=portfolio_id, as_of_date=request.as_of_date, total_market_value=0.0, positions=[]
                )
            total_market_value_base = sum(pos.market_value or Decimal(0) for pos, *_ in repo_results)
            enrichment_coroutines = [self._enrich_position(portfolio, total_market_value_base, row, request) for row in repo_results]
            enriched_positions = await asyncio.gather(*enrichment_coroutines)

            logger.info("Successfully generated position analytics for portfolio %s", portfolio_id)
            return PositionAnalyticsResponse(
                portfolio_id=portfolio_id,
                as_of_date=request.as_of_date,
                total_market_value=float(total_market_value_base),
                positions=enriched_positions
            )

def get_position_analytics_service(db: AsyncSession = Depends(get_async_db_session)) -> PositionAnalyticsService:
    return PositionAnalyticsService(db)