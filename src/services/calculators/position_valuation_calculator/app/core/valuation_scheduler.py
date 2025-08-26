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
# NEW IMPORTS
from portfolio_common.monitoring import (
    REPROCESSING_ACTIVE_KEYS_TOTAL,
    SNAPSHOT_LAG_SECONDS,
    SCHEDULER_GAP_DAYS
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
        Checks all REPROCESSING keys, finds how far their snapshots are contiguous,
        and updates their watermark and status accordingly.
        """
        repo = ValuationRepository(db)
        position_state_repo = PositionStateRepository(db)

        latest_business_date = await repo.get_latest_business_date()
        if not latest_business_date:
            return

        reprocessing_states = await repo.get_reprocessing_states(self._batch_size)
        REPROCESSING_ACTIVE_KEYS_TOTAL.set(len(reprocessing_states)) # SET METRIC
        if not reprocessing_states:
            return

        advancable_dates = await repo.find_contiguous_snapshot_dates(reprocessing_states)
        
        updates_to_commit: List[Dict[str, Any]] = []
        for state in reprocessing_states:
            key = (state.portfolio_id, state.security_id)
            new_watermark = advancable_dates.get(key)

            if new_watermark and new_watermark > state.watermark_date:
                is_complete = new_watermark == latest_business_date
                new_status = 'CURRENT' if is_complete else 'REPROCESSING'
                updates_to_commit.append({
                    "portfolio_id": state.portfolio_id,
                    "security_id": state.security_id,
                    "watermark_date": new_watermark,
                    "status": new_status
                })
        
        if updates_to_commit:
            updated_count = await position_state_repo.bulk_update_states(updates_to_commit)
            logger.info(f"Advanced watermarks for {updated_count} position states.")

    async def _create_backfill_jobs(self, db):
        """
        Finds keys with a lagging watermark and creates valuation jobs to fill the gap,
        starting from the later of the portfolio's open date or the watermark date.
        """
        repo = ValuationRepository(db)
        job_repo = ValuationJobRepository(db)
        
        latest_business_date = await repo.get_latest_business_date()
        if not latest_business_date:
            # FIX: Changed from INFO to DEBUG to reduce log noise
            logger.debug("Scheduler: No business dates found, skipping backfill job creation.")
            return

        states_to_backfill = await repo.get_states_needing_backfill(latest_business_date, self._batch_size)
        
        if not states_to_backfill:
            logger.debug("Scheduler: No keys need backfilling.")
            return
        
        # --- NEW: Added INFO log for successful case ---
        logger.info(f"Scheduler: Found {len(states_to_backfill)} keys needing backfill up to {latest_business_date}.")

        # Fetch portfolio open dates for all states in a single query for efficiency
        portfolio_ids = list(set(s.portfolio_id for s in states_to_backfill))
        portfolios = await repo.get_portfolios_by_ids(portfolio_ids)
        open_dates_map = {p.portfolio_id: p.open_date for p in portfolios}

        for state in states_to_backfill:
            # --- OBSERVE METRICS ---
            gap_days = (latest_business_date - state.watermark_date).days
            SCHEDULER_GAP_DAYS.observe(gap_days)
            SNAPSHOT_LAG_SECONDS.observe(gap_days * 86400)
            # --- END METRICS ---
            
            portfolio_open_date = open_dates_map.get(state.portfolio_id)
            if not portfolio_open_date:
                logger.warning(f"Could not find open date for portfolio {state.portfolio_id}. Skipping backfill for key ({state.portfolio_id}, {state.security_id}).")
                continue

            # Determine the correct start date for backfilling, ensuring it's not before the portfolio existed.
            start_date = max(state.watermark_date, portfolio_open_date - timedelta(days=1))
            
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
                        
                        # Find and reset any jobs that have been stuck for too long
                        await repo.find_and_reset_stale_jobs()
                        # Create new jobs for any positions with a lagging watermark
                        await self._create_backfill_jobs(db)
                        # Claim a batch of pending jobs to be processed
                        claimed_jobs = await repo.find_and_claim_eligible_jobs(self._batch_size)
                        # Check for completed reprocessing and advance watermarks
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