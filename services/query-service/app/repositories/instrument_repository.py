import logging
from typing import List, Optional

from sqlalchemy.orm import Session
from sqlalchemy import func

from portfolio_common.database_models import Instrument

logger = logging.getLogger(__name__)

class InstrumentRepository:
    """
    Handles read-only database queries for instrument data.
    """
    def __init__(self, db: Session):
        self.db = db

    def _get_base_query(
        self,
        security_id: Optional[str] = None,
        product_type: Optional[str] = None
    ) -> Session.query:
        """
        Constructs a base query with all the common filters.
        """
        query = self.db.query(Instrument)
        if security_id:
            query = query.filter(Instrument.security_id == security_id)
        if product_type:
            query = query.filter(Instrument.product_type == product_type)
        return query

    def get_instruments(
        self,
        skip: int,
        limit: int,
        security_id: Optional[str] = None,
        product_type: Optional[str] = None
    ) -> List[Instrument]:
        """
        Retrieves a paginated list of instruments with optional filters.
        """
        query = self._get_base_query(security_id, product_type)
        results = query.order_by(Instrument.name.asc()).offset(skip).limit(limit).all()
        logger.info(f"Found {len(results)} instruments with given filters.")
        return results

    def get_instruments_count(
        self,
        security_id: Optional[str] = None,
        product_type: Optional[str] = None
    ) -> int:
        """
        Returns the total count of instruments for the given filters.
        """
        query = self._get_base_query(security_id, product_type)
        count = query.with_entities(func.count(Instrument.id)).scalar()
        return count