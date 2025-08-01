# services/calculators/position-valuation-calculator/app/repositories/valuation_repository.py
import logging
from datetime import date
from typing import List, Optional
from decimal import Decimal
from sqlalchemy.orm import Session
from sqlalchemy.dialects.postgresql import insert as pg_insert

from portfolio_common.database_models import PositionHistory, MarketPrice, DailyPositionSnapshot
from portfolio_common.events import MarketPriceEvent # NEW IMPORT
from ..logic.valuation_logic import ValuationLogic # NEW IMPORT


logger = logging.getLogger(__name__)

class ValuationRepository:
    """
    Handles all database interactions for the position valuation service.
    """
    def __init__(self, db: Session):
        self.db = db

    def get_latest_price_for_position(self, security_id: str, position_date: date) -> Optional[MarketPrice]:
        """
        Finds the most recent market price for a given security on or before the position's date.
        """
        return self.db.query(MarketPrice).filter(
            MarketPrice.security_id == security_id,
            MarketPrice.price_date <= position_date
        ).order_by(MarketPrice.price_date.desc()).first()

    def get_latest_position_on_or_before(self, portfolio_id: str, security_id: str, a_date: date) -> Optional[PositionHistory]:
        """
        Finds the single most recent transactional position history record for a security
        on or before a given date.
        """
        return self.db.query(PositionHistory).filter(
            PositionHistory.portfolio_id == portfolio_id,
            PositionHistory.security_id == security_id,
            PositionHistory.position_date <= a_date
        ).order_by(PositionHistory.position_date.desc(), PositionHistory.id.desc()).first()

    def upsert_daily_snapshot(self, snapshot: DailyPositionSnapshot) -> DailyPositionSnapshot:
        """
        Idempotently inserts or updates a daily position snapshot and returns the result.
        This method does NOT commit the transaction.
        """
        try:
            insert_dict = {c.name: getattr(snapshot, c.name) for c in snapshot.__table__.columns if c.name != 'id'}
            
            stmt = pg_insert(DailyPositionSnapshot).values(
                **insert_dict
            ).on_conflict_do_update(
                index_elements=['portfolio_id', 'security_id', 'date'],
                set_={k: v for k, v in insert_dict.items() if k not in ['portfolio_id', 'security_id', 'date']}
            ).returning(DailyPositionSnapshot)

            result = self.db.execute(stmt).scalar_one()
            logger.info(f"Staged upsert for daily snapshot for {snapshot.security_id} on {snapshot.date}")
            return result
        except Exception as e:
            logger.error(f"Failed to stage upsert for daily snapshot: {e}", exc_info=True)
            raise

    def update_snapshots_for_market_price(self, price_event: MarketPriceEvent) -> List[DailyPositionSnapshot]:
        """
        Finds all positions affected by a market price update, recalculates their
        valuation, and upserts their daily snapshots. Does NOT commit.

        Returns:
            A list of the updated DailyPositionSnapshot objects.
        """
        updated_snapshots = []
        
        portfolios_with_security = self.db.query(PositionHistory.portfolio_id).filter(
            PositionHistory.security_id == price_event.security_id
        ).distinct().all()

        for portfolio_tuple in portfolios_with_security:
            portfolio_id = portfolio_tuple[0]
            
            latest_position = self.get_latest_position_on_or_before(
                portfolio_id=portfolio_id,
                security_id=price_event.security_id,
                a_date=price_event.price_date
            )

            if not latest_position or latest_position.quantity.is_zero():
                continue

            market_value, unrealized_gain_loss = ValuationLogic.calculate(
                quantity=latest_position.quantity,
                cost_basis=latest_position.cost_basis,
                market_price=price_event.price
            )

            snapshot_to_save = DailyPositionSnapshot(
                portfolio_id=portfolio_id,
                security_id=price_event.security_id,
                date=price_event.price_date,
                quantity=latest_position.quantity,
                cost_basis=latest_position.cost_basis,
                market_price=price_event.price,
                market_value=market_value,
                unrealized_gain_loss=unrealized_gain_loss
            )
            
            persisted_snapshot = self.upsert_daily_snapshot(snapshot_to_save)
            updated_snapshots.append(persisted_snapshot)
            
        return updated_snapshots