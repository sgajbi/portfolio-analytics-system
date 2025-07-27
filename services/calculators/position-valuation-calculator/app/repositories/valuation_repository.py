import logging
from datetime import date
from typing import List, Optional
from decimal import Decimal

from sqlalchemy.orm import Session
from portfolio_common.database_models import PositionHistory, MarketPrice

logger = logging.getLogger(__name__)

class ValuationRepository:
    """
    Handles all database interactions for the position valuation service.
    """
    def __init__(self, db: Session):
        self.db = db

    def get_position_by_id(self, position_history_id: int) -> Optional[PositionHistory]:
        """Fetches a single position history record by its primary key."""
        return self.db.query(PositionHistory).filter(PositionHistory.id == position_history_id).first()

    def get_latest_price_for_position(self, security_id: str, position_date: date) -> Optional[MarketPrice]:
        """
        Finds the most recent market price for a given security on or before the position's date.
        """
        return self.db.query(MarketPrice).filter(
            MarketPrice.security_id == security_id,
            MarketPrice.price_date <= position_date
        ).order_by(MarketPrice.price_date.desc()).first()

    def get_positions_for_price(self, security_id: str, price_date: date) -> List[PositionHistory]:
        """
        Finds all position history records for a given security on a specific date.
        This is used to re-value positions when a new price arrives.
        """
        return self.db.query(PositionHistory).filter(
            PositionHistory.security_id == security_id,
            PositionHistory.position_date == price_date
        ).all()

    def update_position_valuation(
        self,
        position_history_id: int,
        market_price: Decimal,
        market_value: Decimal,
        unrealized_gain_loss: Decimal
    ) -> Optional[PositionHistory]:
        """
        Updates a position record with its calculated valuation data.
        """
        position = self.get_position_by_id(position_history_id)
        if not position:
            logger.warning(f"Could not find position_history with id {position_history_id} to update.")
            return None

        position.market_price = market_price
        position.market_value = market_value
        position.unrealized_gain_loss = unrealized_gain_loss
        
        try:
            self.db.commit()
            self.db.refresh(position)
            logger.info(f"Successfully updated valuation for position_history_id {position_history_id}.")
            return position
        except Exception as e:
            logger.error(f"Failed to update valuation for position_history_id {position_history_id}: {e}", exc_info=True)
            self.db.rollback()
            return None