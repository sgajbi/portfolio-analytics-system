# src/services/calculators/position_valuation_calculator/app/core/valuation_scheduler.py
import logging
import asyncio
import os
from typing import List

from portfolio_common.db import get_async_db_session
from portfolio_common.kafka_utils import KafkaProducer, get_kafka_producer
from portfolio_common.config import KAFKA_VALUATION_REQUIRED_TOPIC
from portfolio_common.events import PortfolioValuationRequiredEvent
from portfolio_common.database_models import PortfolioValuationJob
from ..repositories.valuation_repository import ValuationRepository

logger = logging.getLogger(__name__)

class ValuationScheduler:
    """
    A background task that polls the portfolio_valuation_jobs table, finds jobs
    that are ready to be processed, and dispatches them as Kafka events.
    """
    def __init__(self, poll_interval: int = 30, batch_size: int = 100):
        # Read interval from env var, fall back to the passed argument.
        self._poll_interval = int(os.getenv("VALUATION_SCHEDULER_POLL_INTERVAL", poll_interval))
        self._batch_size = batch_size
        self._running = True
        self._producer: KafkaProducer = get_kafka_producer()

    def stop(self):
        """Signals the scheduler to gracefully shut down."""
        logger.info("Valuation scheduler shutdown signal received.")
        self._running = False

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
                        
                        # First, recover any jobs that may have been orphaned.
                        await repo.find_and_reset_stale_jobs()
                        
                        # Now, find and claim new eligible jobs.
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