# services/persistence_service/app/repositories/fx_rate_repository.py
import logging
from typing import Tuple, List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from portfolio_common.database_models import FxRate as DBFxRate
from portfolio_common.events import FxRateEvent

logger = logging.getLogger(__name__)

class FxRateRepository:
    """
    Repository for upserting FX rate records into the database.
    """
    def __init__(self, db: AsyncSession):
        self.db = db

    async def upsert_fx_rate(self, event: FxRateEvent) -> Tuple[DBFxRate, str]:
        """
        Upserts an FX rate by (from_currency, to_currency, rate_date).
        Returns a tuple: (DBFxRate instance, status: 'created', 'updated', or 'no-op').
        """
        stmt = select(DBFxRate).filter_by(
            from_currency=event.from_currency,
            to_currency=event.to_currency,
            rate_date=event.rate_date
        )
        result = await self.db.execute(stmt)
        db_rate = result.scalars().first()
        
        fx_rate_data = event.model_dump()

        if db_rate:
            changed = False
            for key, value in fx_rate_data.items():
                if getattr(db_rate, key) != value:
                    setattr(db_rate, key, value)
                    changed = True
            status = "updated" if changed else "no-op"
            logger.info(
                f"FX Rate for '{event.from_currency}-{event.to_currency}' on {event.rate_date} "
                f"{'updated' if changed else 'already up-to-date'}."
            )
        else:
            db_rate = DBFxRate(**fx_rate_data)
            self.db.add(db_rate)
            status = "created"
            logger.info(
                f"FX Rate for '{event.from_currency}-{event.to_currency}' on {event.rate_date} created."
            )
        return db_rate, status

    async def batch_upsert_fx_rates(self, events: List[FxRateEvent]) -> Tuple[int, int, int]:
        """
        Batch upserts a list of FxRateEvent objects.
        Returns a tuple: (created_count, updated_count, noop_count).
        """
        created, updated, noop = 0, 0, 0
        for event in events:
            try:
                _, status = await self.upsert_fx_rate(event)
                if status == "created":
                    created += 1
                elif status == "updated":
                    updated += 1
                else:
                    noop += 1
            except Exception as e:
                logger.error(
                    f"Failed to upsert FX rate for '{event.from_currency}-{event.to_currency}' on '{event.rate_date}': {e}",
                    exc_info=True
                )
        logger.info(f"Batch upsert summary: {created} created, {updated} updated, {noop} unchanged.")
        return created, updated, noop