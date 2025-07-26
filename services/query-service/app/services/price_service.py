import logging
from datetime import date
from typing import Optional
from sqlalchemy.orm import Session

from ..repositories.price_repository import MarketPriceRepository
from ..dtos.price_dto import MarketPriceRecord, MarketPriceResponse

logger = logging.getLogger(__name__)

class MarketPriceService:
    """
    Handles the business logic for querying market price data.
    """
    def __init__(self, db: Session):
        self.db = db
        self.repo = MarketPriceRepository(db)

    def get_prices(
        self,
        security_id: str,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None
    ) -> MarketPriceResponse:
        """
        Retrieves a filtered list of market prices for a security.
        """
        logger.info(f"Fetching market prices for security '{security_id}'.")
        
        # 1. Get the list of prices from the repository
        db_results = self.repo.get_prices(
            security_id=security_id,
            start_date=start_date,
            end_date=end_date
        )
        
        # 2. Map the database results to our DTO
        prices = [MarketPriceRecord.model_validate(row) for row in db_results]
        
        # 3. Construct the final API response object
        return MarketPriceResponse(
            security_id=security_id,
            prices=prices
        )