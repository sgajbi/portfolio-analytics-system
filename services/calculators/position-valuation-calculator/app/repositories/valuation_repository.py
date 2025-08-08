# services/calculators/position-valuation-calculator/app/repositories/valuation_repository.py
import logging
from datetime import date
from typing import List, Optional
from sqlalchemy import select, func, distinct
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.postgresql import insert as pg_insert

from portfolio_common.database_models import (
    PositionHistory, MarketPrice, DailyPositionSnapshot, Portfolio, FxRate, Instrument
)
from portfolio_common.events import MarketPriceEvent
from ..logic.valuation_logic import ValuationLogic

logger = logging.getLogger(__name__)

class ValuationRepository:
    """
    Handles all database interactions for the position valuation service.
    """
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_instrument(self, security_id: str) -> Optional[Instrument]:
        """Fetches an instrument by its security ID."""
        # This is still needed to get the instrument's currency
        result = await self.db.execute(select(Instrument).filter_by(security_id=security_id))
        return result.scalars().first()

    async def get_fx_rate(self, from_currency: str, to_currency: str, a_date: date) -> Optional[FxRate]:
        """Fetches the latest FX rate on or before a given date to align price currency with instrument currency."""
        stmt = select(FxRate).filter(
            FxRate.from_currency == from_currency,
            FxRate.to_currency == to_currency,
            FxRate.rate_date <= a_date
        ).order_by(FxRate.rate_date.desc())
        result = await self.db.execute(stmt)
        return result.scalars().first()

    async def get_latest_price_for_position(self, security_id: str, position_date: date) -> Optional[MarketPrice]:
        """
        Finds the most recent market price for a given security on or before the position's date.
        """
        stmt = select(MarketPrice).filter(
            MarketPrice.security_id == security_id,
            MarketPrice.price_date <= position_date
        ).order_by(MarketPrice.price_date.desc())
        result = await self.db.execute(stmt)
        return result.scalars().first()

    async def get_latest_position_on_or_before(self, portfolio_id: str, security_id: str, a_date: date) -> Optional[PositionHistory]:
        """
        Finds the single most recent transactional position history record for a security
        on or before a given date.
        """
        stmt = select(PositionHistory).filter(
            PositionHistory.portfolio_id == portfolio_id,
            PositionHistory.security_id == security_id,
            PositionHistory.position_date <= a_date
        ).order_by(PositionHistory.position_date.desc(), PositionHistory.id.desc())
        result = await self.db.execute(stmt)
        return result.scalars().first()

    async def upsert_daily_snapshot(self, snapshot: DailyPositionSnapshot) -> DailyPositionSnapshot:
        """
        Idempotently inserts or updates a daily position snapshot and returns the result.
        """
        try:
            insert_dict = {c.name: getattr(snapshot, c.name) for c in snapshot.__table__.columns if c.name != 'id'}
            
            stmt = pg_insert(DailyPositionSnapshot).values(
                **insert_dict
            ).on_conflict_do_update(
                index_elements=['portfolio_id', 'security_id', 'date'],
                set_={k: v for k, v in insert_dict.items() if k not in ['portfolio_id', 'security_id', 'date']}
            ).returning(DailyPositionSnapshot)

            result = await self.db.execute(stmt)
            persisted_snapshot = result.scalar_one()
            await self.db.flush()
            logger.info(f"Staged upsert for daily snapshot for {snapshot.security_id} on {snapshot.date}")
            return persisted_snapshot
        except Exception as e:
            logger.error(f"Failed to stage upsert for daily snapshot: {e}", exc_info=True)
            raise

    async def update_snapshots_for_market_price(self, price_event: MarketPriceEvent) -> List[DailyPositionSnapshot]:
        """
        Finds all positions affected by a market price update, recalculates their
        valuation, and upserts their daily snapshots.
        """
        updated_snapshots = []
        
        # This method's logic will be updated in a subsequent step to handle the new FX rules
        stmt = select(distinct(PositionHistory.portfolio_id)).filter_by(security_id=price_event.security_id)
        result = await self.db.execute(stmt)
        portfolios_with_security = result.scalars().all()

        for portfolio_id in portfolios_with_security:
            latest_position = await self.get_latest_position_on_or_before(
                portfolio_id=portfolio_id,
                security_id=price_event.security_id,
                a_date=price_event.price_date
            )

            if not latest_position or latest_position.quantity.is_zero():
                continue

            # Placeholder for logic that will be updated
            market_value, unrealized_gain_loss = ValuationLogic.calculate(
                quantity=latest_position.quantity,
                cost_basis=latest_position.cost_basis,
                market_price=price_event.price,
                instrument_currency=price_event.currency, # Temporarily assume price currency is instrument currency
                portfolio_currency=price_event.currency
            )

            snapshot_to_save = DailyPositionSnapshot(
                portfolio_id=portfolio_id,
                security_id=price_event.security_id,
                date=price_event.price_date,
                quantity=latest_position.quantity,
                cost_basis=latest_position.cost_basis,
                market_price=price_event.price,
                market_value=market_value,
                unrealized_gain_loss=unrealized_gain_loss,
                valuation_status="VALUED" # Placeholder
            )
            
            persisted_snapshot = await self.upsert_daily_snapshot(snapshot_to_save)
            updated_snapshots.append(persisted_snapshot)
            
        return updated_snapshots