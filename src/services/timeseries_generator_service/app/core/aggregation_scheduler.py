# services/timeseries-generator-service/app/core/aggregation_scheduler.py
import logging
import asyncio
from typing import List

from portfolio_common.db import get_async_db_session
from portfolio_common.kafka_utils import KafkaProducer, get_kafka_producer
from portfolio_common.config import KAFKA_PORTFOLIO_AGGREGATION_REQUIRED_TOPIC
from portfolio_common.events import PortfolioAggregationRequiredEvent
from portfolio_common.database_models import PortfolioAggregationJob
from portfolio_common.repositories.timeseries_repository import TimeseriesRepository


logger = logging.getLogger(__name__)

class AggregationScheduler:
    """
    A background task that polls the aggregation jobs table, finds jobs
    that are ready to be processed in chronological order, and dispatches
    them as Kafka events.
    """
    def __init__(self, poll_interval: int = 5, batch_size: int = 100):
        self._poll_interval = poll_interval
        self._batch_size = batch_size
        self._running = True
        self._producer: KafkaProducer = get_kafka_producer()

    def stop(self):
        """Signals the scheduler to gracefully shut down."""
        logger.info("Aggregation scheduler shutdown signal received.")
        self._running = False

    async def _dispatch_jobs(self, jobs: List[PortfolioAggregationJob]):
        """Publishes a batch of claimed jobs to Kafka."""
        if not jobs:
            return
        
        logger.info(f"Dispatching {len(jobs)} claimed aggregation jobs to Kafka.")
        for job in jobs:
            event = PortfolioAggregationRequiredEvent(
                portfolio_id=job.portfolio_id,
                aggregation_date=job.aggregation_date,
                correlation_id=job.correlation_id
            )
            headers = [('correlation_id', (job.correlation_id or "").encode('utf-8'))]
            self._producer.publish_message(
                topic=KAFKA_PORTFOLIO_AGGREGATION_REQUIRED_TOPIC,
                key=job.portfolio_id,
                value=event.model_dump(mode='json'),
                headers=headers
            )
        self._producer.flush(timeout=10)
        logger.info(f"Successfully flushed {len(jobs)} aggregation jobs.")

    async def run(self):
        """The main polling loop for the scheduler."""
        logger.info(f"AggregationScheduler started. Polling every {self._poll_interval} seconds.")
        while self._running:
            try:
                async for db in get_async_db_session():
                    async with db.begin():
                        repo = TimeseriesRepository(db)
                        
                        # First, recover any jobs that may have been orphaned by a crashed worker.
                        await repo.find_and_reset_stale_jobs()

                        # Now, find and claim new eligible jobs for processing.
                        claimed_jobs = await repo.find_and_claim_eligible_jobs(self._batch_size)
                
                if claimed_jobs:
                    logger.info(f"Scheduler claimed {len(claimed_jobs)} jobs for processing.")
                    await self._dispatch_jobs(claimed_jobs)
                else:
                    logger.info("Scheduler poll found no eligible jobs.")

            except Exception as e:
                logger.error("Error in scheduler polling loop.", exc_info=True)

            try:
                await asyncio.sleep(self._poll_interval)
            except asyncio.CancelledError:
                break
        
        logger.info("AggregationScheduler has stopped.")