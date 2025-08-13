# src/services/calculators/position_valuation_calculator/app/core/valuation_scheduler.py
import logging
import asyncio
from typing import List
from datetime import date

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
    A background task that polls for open positions and creates valuation jobs,
    then polls for PENDING jobs and dispatches them as Kafka events.
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

    async def _create_jobs_for_open_positions(self, repo: ValuationRepository):
        """Finds open positions and creates valuation jobs for the current date."""
        today = date.today()
        open_positions = await repo.find_open_positions_without_jobs_for_date(today, self._batch_size)

        if not open_positions:
            return

        logger.info(f"Found {len(open_positions)} open positions requiring valuation jobs for {today}.")
        
        job_values = [
            {
                "portfolio_id": pos["portfolio_id"],
                "security_id": pos["security_id"],
                "valuation_date": today,
                "status": "PENDING",
            }
            for pos in open_positions
        ]
        
        if job_values:
            # Use a bulk insert that does nothing on conflict to avoid creating duplicate jobs
            stmt = pg_insert(PortfolioValuationJob).values(job_values)
            stmt = stmt.on_conflict_do_nothing(index_elements=['portfolio_id', 'security_id', 'valuation_date'])
            await repo.db.execute(stmt)
            logger.info(f"Successfully created {len(job_values)} new valuation jobs.")

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
                key=job.portfolio_id, # Key by portfolio for partition affinity
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
                        
                        # Step 1: Recover any jobs that may have been orphaned.
                        await repo.find_and_reset_stale_jobs()
                        
                        # Step 2 (NEW): Proactively create jobs for today
                        # In a real system, this might be a specific time, but for testing, every poll is fine.
                        await self._create_jobs_for_open_positions(repo)
                        
                        # Step 3: Find and claim eligible PENDING jobs for processing.
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