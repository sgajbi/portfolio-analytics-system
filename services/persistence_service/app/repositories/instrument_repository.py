# services/persistence_service/app/repositories/instrument_repository.py
import logging
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from portfolio_common.database_models import Instrument as DBInstrument
from portfolio_common.events import InstrumentEvent

logger = logging.getLogger(__name__)

class InstrumentRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_or_update_instrument(self, event: InstrumentEvent) -> DBInstrument:
        try:
            stmt = select(DBInstrument).filter_by(security_id=event.security_id)
            result = await self.db.execute(stmt)
            db_instrument = result.scalars().first()
            
            instrument_data = event.model_dump(by_alias=True)

            if db_instrument:
                for key, value in instrument_data.items():
                    setattr(db_instrument, key, value)
                logger.info(f"Instrument '{event.security_id}' found, staging for update.")
            else:
                db_instrument = DBInstrument(**instrument_data)
                self.db.add(db_instrument)
                logger.info(f"Instrument '{event.security_id}' not found, staging for creation.")

            return db_instrument
        except Exception as e:
            logger.error(f"Failed to stage upsert for instrument '{event.security_id}': {e}", exc_info=True)
            raise