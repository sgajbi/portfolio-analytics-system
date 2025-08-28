# src/services/calculators/position_valuation_calculator/app/core/valuation_scheduler.py
import logging
import asyncio
import os
from typing import List, Dict, Any
from datetime import date, timedelta

from portfolio_common.db import get_async_db_session
from portfolio_common.kafka_utils import KafkaProducer, get_kafka_producer
from portfolio_common.config import KAFKA_VALUATION_REQUIRED_TOPIC
from portfolio_common.events import PortfolioValuationRequiredEvent
from portfolio_common.database_models import PortfolioValuationJob, PositionState
from ..repositories.valuation_repository import ValuationRepository
from portfolio_common.valuation_job_repository import ValuationJobRepository
from portfolio_common.position_state_repository import PositionStateRepository
from portfolio_common.monitoring import (
    REPROCESSING_ACTIVE_KEYS_TOTAL,
    SNAPSHOT_LAG_SECONDS,
    SCHEDULER_GAP_DAYS,
    VALUATION_JOBS_CREATED_TOTAL
)


logger = logging.getLogger(__name__)

class ValuationScheduler:
    """
    A background task that drives all valuation activity. It polls the position_state
    table to find keys that need backfilling, creates the necessary valuation jobs,
    dispatches them, and advances watermarks upon completion.
    """
    def __init__(self, poll_interval: int = 30, batch_size: int = 100):
        self._poll_interval = int(os.getenv("VALUATION_SCHEDULER_POLL_INTERVAL", poll_interval))
        self._batch_size = batch_size
        self._running = True
        self._producer: KafkaProducer = get_kafka_producer()

    def stop(self):
        """Signals the scheduler to gracefully shut down."""
        logger.info("Valuation scheduler shutdown signal received.")
        self._running = False

    async def _advance_watermarks(self, db):
        """
        Checks all lagging keys, finds how far their snapshots are contiguous,
        and updates their watermark and status accordingly.
        """
        repo = ValuationRepository(db)
        position_state_repo = PositionStateRepository(db)

        latest_business_date = await repo.get_latest_business_date()
        if not latest_business_date:
            return

        lagging_states = await repo.get_lagging_states(latest_business_date, self._batch_size)
        
        # This metric is now more accurate, reflecting all states being worked on.
        reprocessing_count = sum(1 for s in lagging_states if s.status == 'REPROCESSING')
        REPROCESSING_ACTIVE_KEYS_TOTAL.set(reprocessing_count)
        
        if not lagging_states:
            return

        advancable_dates = await repo.find_contiguous_snapshot_dates(lagging_states)
        
        updates_to_commit: List[Dict[str, Any]] = []
        for state in lagging_states:
            key = (state.portfolio_id, state.security_id)
            new_watermark = advancable_dates.get(key)

            if new_watermark and new_watermark > state.watermark_date:
                is_complete = new_watermark == latest_business_date
                new_status = 'CURRENT' if is_complete else state.status # Keep REPROCESSING status if not yet complete
                updates_to_commit.append({
                    "portfolio_id": state.portfolio_id,
                    "security_id": state.security_id,
                    "watermark_date": new_watermark,
                    "status": new_status
                })
        
        if updates_to_commit:
            updated_count = await position_state_repo.bulk_update_states(updates_to_commit)
            # --- RFC CHANGE B: Add explicit logging ---
            log_examples = [
                f"({u['portfolio_id']},{u['security_id']})->{u['watermark_date']}"
                for u in updates_to_commit[:3]
            ]
            logger.info(
                f"ValuationScheduler: advanced {updated_count} watermarks.",
                extra={"examples": log_examples}
            )
            # --- END RFC CHANGE ---

    async def _create_backfill_jobs(self, db):
        """
        Finds keys with a lagging watermark and creates valuation jobs to fill the gap,
        starting from the later of the watermark date or the position's first open date.
        """
        repo = ValuationRepository(db)
        job_repo = ValuationJobRepository(db)
        
        latest_business_date = await repo.get_latest_business_date()
        if not latest_business_date:
            logger.debug("Scheduler: No business dates found, skipping backfill job creation.")
            return

        states_to_backfill = await repo.get_states_needing_backfill(latest_business_date, self._batch_size)
        
        if not states_to_backfill:
            logger.debug("Scheduler: No keys need backfilling.")
            return
        
        logger.info(f"Scheduler: Found {len(states_to_backfill)} keys needing backfill up to {latest_business_date}.")

        keys_to_check = [(s.portfolio_id, s.security_id, s.epoch) for s in states_to_backfill]
        first_open_dates = await repo.get_first_open_dates_for_keys(keys_to_check)

        for state in states_to_backfill:
            # --- RFC CHANGE B: Add observability metrics ---
            gap_days = (latest_business_date - state.watermark_date).days
            SCHEDULER_GAP_DAYS.observe(gap_days)
            SNAPSHOT_LAG_SECONDS.observe(gap_days * 86400)
            # --- END RFC CHANGE ---
            
            key = (state.portfolio_id, state.security_id, state.epoch)
            first_open_date = first_open_dates.get(key)

            if not first_open_date:
                logger.warning(f"No position history found for key {key}. Skipping backfill job creation.")
                continue

            # Determine the correct start date for backfilling.
            start_date = max(state.watermark_date, first_open_date - timedelta(days=1))
            
            job_count = 0
            current_date = start_date + timedelta(days=1)
            
            # Create jobs up to the latest business date
            while current_date <= latest_business_date:
                await job_repo.upsert_job(
                    portfolio_id=state.portfolio_id,
                    security_id=state.security_id,
                    valuation_date=current_date,
                    epoch=state.epoch,
                    correlation_id=f"SCHEDULER_BACKFILL_{current_date.isoformat()}"
                )
                job_count += 1
                current_date += timedelta(days=1)
            
            if job_count > 0:
                VALUATION_JOBS_CREATED_TOTAL.labels(
                    portfolio_id=state.portfolio_id, security_id=state.security_id
                ).inc(job_count)
                logger.info(f"Scheduler: Created {job_count} backfill valuation jobs for {state.security_id} in {state.portfolio_id} for epoch {state.epoch}.")

    
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
                epoch=job.epoch,
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
                        
                        await repo.find_and_reset_stale_jobs()
                        await self._create_backfill_jobs(db)
                        claimed_jobs = await repo.find_and_claim_eligible_jobs(self._batch_size)
                        
                        await self._advance_watermarks(db)
                
                if claimed_jobs:
                    await self._dispatch_jobs(claimed_jobs)

            except Exception as e:
                logger.error("Error in scheduler polling loop.", exc_info=True)

            try:
                await asyncio.sleep(self._poll_interval)
            except asyncio.CancelledError:
                break
        
        logger.info("ValuationScheduler has stopped.")