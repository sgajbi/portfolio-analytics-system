# src/services/calculators/position_valuation_calculator/app/core/valuation_scheduler.py
import logging
import asyncio
import os
from typing import List
from datetime import date, timedelta

from portfolio_common.db import get_async_db_session
from portfolio_common.kafka_utils import KafkaProducer, get_kafka_producer
from portfolio_common.config import KAFKA_VALUATION_REQUIRED_TOPIC
from portfolio_common.events import PortfolioValuationRequiredEvent
from portfolio_common.database_models import PortfolioValuationJob
from ..repositories.valuation_repository import ValuationRepository
from portfolio_common.valuation_job_repository import ValuationJobRepository


logger = logging.getLogger(__name__)

class ValuationScheduler:
    """
    A background task that acts as the system's daily heartbeat. It polls for the
    latest business date, finds all open positions, and creates valuation jobs
    for any days that have been missed, ensuring a complete time series.
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

    async def _create_daily_roll_forward_jobs(self, db):
        """
        Finds all open positions and creates valuation jobs for any days
        between their last snapshot and the latest business day, respecting
        recalculation locks.
        """
        repo = ValuationRepository(db)
        job_repo = ValuationJobRepository(db)
        
        latest_business_date = await repo.get_latest_business_date()
        
        if not latest_business_date:
            logger.info("Scheduler: No business dates found, skipping roll-forward job creation.")
            return

        open_positions = await repo.get_all_open_positions()
        if not open_positions:
            logger.info("Scheduler: No open positions found, skipping roll-forward job creation.")
            return

        # Check which of these positions are currently locked by a recalculation job
        open_position_tuples = [(pos['portfolio_id'], pos['security_id']) for pos in open_positions]
        locked_positions = await repo.are_recalculations_processing(open_position_tuples)
        locked_positions_set = set(locked_positions)

        if locked_positions_set:
            logger.info(
                f"Scheduler: Deferring roll-forward for {len(locked_positions_set)} positions "
                f"due to active recalculation jobs: {list(locked_positions_set)}"
            )
        
        # Filter out the locked positions
        unlocked_positions = [
            pos for pos in open_positions 
            if (pos['portfolio_id'], pos['security_id']) not in locked_positions_set
        ]

        logger.info(f"Scheduler: Checking {len(unlocked_positions)} unlocked open positions for roll-forward against latest business date {latest_business_date}.")
        
        for pos in unlocked_positions:
            portfolio_id = pos['portfolio_id']
            security_id = pos['security_id']

            last_snapshot_date = await repo.get_last_snapshot_date(portfolio_id, security_id)
            
            # If a position exists but has no snapshots yet, start from its first transaction date
            if not last_snapshot_date:
                last_snapshot_date = await repo.get_first_transaction_date(portfolio_id, security_id)
                if not last_snapshot_date:
                    continue # Should not happen if it's an open position, but defensive check

            if last_snapshot_date < latest_business_date:
                job_count = 0
                current_date = last_snapshot_date + timedelta(days=1)
                
                while current_date <= latest_business_date:
                    await job_repo.upsert_job(
                        portfolio_id=portfolio_id,
                        security_id=security_id,
                        valuation_date=current_date,
                        correlation_id=f"SCHEDULER_ROLL_FORWARD_{current_date.isoformat()}"
                    )
                    job_count += 1
                    current_date += timedelta(days=1)
                
                if job_count > 0:
                    logger.info(f"Scheduler: Created {job_count} roll-forward valuation jobs for {security_id} in {portfolio_id} up to {latest_business_date}.")

    
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
            claimed_jobs = []
            try:
                async for db in get_async_db_session():
                    async with db.begin():
                        repo = ValuationRepository(db)
                        
                        # 1. Recover any jobs that may have been orphaned.
                        await repo.find_and_reset_stale_jobs()
                    
                        # 2. Create any missing daily jobs for roll-forward.
                        await self._create_daily_roll_forward_jobs(db)
                        
                        # 3. Atomically find and claim new eligible jobs.
                        claimed_jobs = await repo.find_and_claim_eligible_jobs(self._batch_size)
                
                # 4. Dispatch the claimed jobs AFTER the transaction has been successfully committed.
                if claimed_jobs:
                    await self._dispatch_jobs(claimed_jobs)

            except Exception as e:
                logger.error("Error in valuation scheduler polling loop.", exc_info=True)

            try:
                await asyncio.sleep(self._poll_interval)
            except asyncio.CancelledError:
                break
        
        logger.info("ValuationScheduler has stopped.")