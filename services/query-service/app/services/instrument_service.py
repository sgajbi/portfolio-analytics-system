# services/query-service/app/services/instrument_service.py
import logging
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession

from ..repositories.instrument_repository import InstrumentRepository
from ..dtos.instrument_dto import InstrumentRecord, PaginatedInstrumentResponse

logger = logging.getLogger(__name__)

class InstrumentService:
    """
    Handles the business logic for querying instrument data.
    """
    def __init__(self, db: AsyncSession):
        self.db = db
        self.repo = InstrumentRepository(db)

    async def get_instruments(
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
        
        total_count = await self.repo.get_instruments_count(
            security_id=security_id,
            product_type=product_type
        )

        db_results = await self.repo.get_instruments(
            skip=skip,
            limit=limit,
            security_id=security_id,
            product_type=product_type
        )
        
        instruments = [InstrumentRecord.model_validate(row) for row in db_results]
        
        return PaginatedInstrumentResponse(
            total=total_count,
            skip=skip,
            limit=limit,
            instruments=instruments
        )