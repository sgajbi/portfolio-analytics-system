import logging
from datetime import date
from typing import Optional
from sqlalchemy.orm import Session

from ..repositories.fx_rate_repository import FxRateRepository
from ..dtos.fx_rate_dto import FxRateRecord, FxRateResponse

logger = logging.getLogger(__name__)

class FxRateService:
    """
    Handles the business logic for querying FX rate data.
    """
    def __init__(self, db: Session):
        self.db = db
        self.repo = FxRateRepository(db)

    def get_fx_rates(
        self,
        from_currency: str,
        to_currency: str,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None
    ) -> FxRateResponse:
        """
        Retrieves a filtered list of FX rates for a currency pair.
        """
        logger.info(f"Fetching FX rates for '{from_currency}-{to_currency}'.")
        
        # 1. Get the list of rates from the repository
        db_results = self.repo.get_fx_rates(
            from_currency=from_currency,
            to_currency=to_currency,
            start_date=start_date,
            end_date=end_date
        )
        
        # 2. Map the database results to our DTO
        rates = [FxRateRecord.model_validate(row) for row in db_results]
        
        # 3. Construct the final API response object
        return FxRateResponse(
            from_currency=from_currency,
            to_currency=to_currency,
            rates=rates
        )