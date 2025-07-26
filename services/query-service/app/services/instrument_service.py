import logging
from typing import Optional
from sqlalchemy.orm import Session

from ..repositories.instrument_repository import InstrumentRepository
from ..dtos.instrument_dto import InstrumentRecord, PaginatedInstrumentResponse

logger = logging.getLogger(__name__)

class InstrumentService:
    """
    Handles the business logic for querying instrument data.
    """
    def __init__(self, db: Session):
        self.db = db
        self.repo = InstrumentRepository(db)

    def get_instruments(
        self,
        skip: int,
        limit: int,
        security_id: Optional[str] = None,
        product_type: Optional[str] = None
    ) -> PaginatedInstrumentResponse:
        """
        Retrieves a paginated and filtered list of instruments.
        """
        logger.info("Fetching instruments.")
        
        # 1. Get the total count for pagination
        total_count = self.repo.get_instruments_count(
            security_id=security_id,
            product_type=product_type
        )

        # 2. Get the paginated list of instruments
        db_results = self.repo.get_instruments(
            skip=skip,
            limit=limit,
            security_id=security_id,
            product_type=product_type
        )
        
        # 3. Map the database results to our DTO
        instruments = [InstrumentRecord.model_validate(row) for row in db_results]
        
        # 4. Construct the final API response object
        return PaginatedInstrumentResponse(
            total=total_count,
            skip=skip,
            limit=limit,
            instruments=instruments
        )