# src/services/calculators/position_valuation_calculator/app/core/valuation_scheduler.py
import logging
import asyncio
from typing import List
from datetime import date, timedelta

from portfolio_common.db import get_async_db_session
from portfolio_common.kafka_utils import KafkaProducer, get_kafka_producer
from portfolio_common.config import KAFKA_VALUATION_REQUIRED_TOPIC
from portfolio_common.events import PortfolioValuationRequiredEvent
from portfolio_common.database_models import PortfolioValuationJob
from ..repositories.valuation_repository import ValuationRepository
from sqlalchemy.dialects.postgresql import insert as pg_insert

logger = logging.getLogger(__name__)

class ValuationScheduler:
    """
    A background task that ensures all open positions are valued daily by
    finding gaps in the valuation history and creating jobs to fill them.
    """
    def __init__(self, poll_interval: int = 30, batch_size: int = 100):
        self._poll_interval = poll_interval
        self._batch_size = batch_size
        self._running = True
        self._producer: KafkaProducer = get_kafka_producer()

    def stop(self):
        """Signals the scheduler to gracefully shut down."""
        logger.info("Valuation scheduler shutdown signal received.")
        self._running = False

    async def _create_jobs_to_fill_gaps(self, repo: ValuationRepository):
        """
        Finds all open positions, checks for gaps in their valuation history up to the
        current system date, and creates jobs to fill those gaps.
        """
        target_date = date.today()
        open_positions = await repo.get_all_open_positions()
        
        if not open_positions:
            return

        all_job_values = []
        for pos in open_positions:
            portfolio_id = pos['portfolio_id']
            security_id = pos['security_id']

            first_tx_date = await repo.get_first_transaction_date(portfolio_id, security_id)
            last_snapshot_date = await repo.get_last_snapshot_date(portfolio_id, security_id)

            start_date = last_snapshot_date + timedelta(days=1) if last_snapshot_date else first_tx_date

            if not start_date or start_date > target_date:
                continue

            # Generate jobs for each missing day
            current_date = start_date
            while current_date <= target_date:
                all_job_values.append({
                    "portfolio_id": portfolio_id,
                    "security_id": security_id,
                    "valuation_date": current_date,
                    "status": "PENDING",
                })
                current_date += timedelta(days=1)
        
        if not all_job_values:
            return

        logger.info(f"Found {len(all_job_values)} historical/daily valuation gaps to fill up to {target_date}.")
        stmt = pg_insert(PortfolioValuationJob).values(all_job_values)
        stmt = stmt.on_conflict_do_nothing(index_elements=['portfolio_id', 'security_id', 'valuation_date'])
        await repo.db.execute(stmt)

    async def _dispatch_jobs(self, jobs: List[PortfolioValuationJob]):
        """Publishes a batch of claimed jobs to Kafka."""
        if not jobs:
            return
        
        logger.info(f"Dispatching {len(jobs)} claimed valuation jobs to Kafka.")
        for job in jobs:
            event = PortfolioValuationRequiredEvent(
                portfolio_id=job.portfolio_id,
                security_id=job.security_id,
                valuation_date=job.valuation_date,
                correlation_id=job.correlation_id
            )
            headers = [('correlation_id', (job.correlation_id or "").encode('utf-8'))]
            self._producer.publish_message(
                topic=KAFKA_VALUATION_REQUIRED_TOPIC,
                key=job.portfolio_id,
                value=event.model_dump(mode='json'),
                headers=headers
            )
        self._producer.flush(timeout=10)
        logger.info(f"Successfully flushed {len(jobs)} valuation jobs.")

    async def run(self):
        """The main polling loop for the scheduler."""
        logger.info(f"ValuationScheduler started. Polling every {self._poll_interval} seconds.")
        while self._running:
            try:
                async for db in get_async_db_session():
                    async with db.begin():
                        repo = ValuationRepository(db)
                        
                        await repo.find_and_reset_stale_jobs()
                        
                        # This now creates jobs up to the current date
                        await self._create_jobs_to_fill_gaps(repo)
                        
                        claimed_jobs = await repo.find_and_claim_eligible_jobs(self._batch_size)
                
                if claimed_jobs:
                    await self._dispatch_jobs(claimed_jobs)

            except Exception as e:
                logger.error("Error in valuation scheduler polling loop.", exc_info=True)

            try:
                await asyncio.sleep(self._poll_interval)
            except asyncio.CancelledError:
                break
        
        logger.info("ValuationScheduler has stopped.")