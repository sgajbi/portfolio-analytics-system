# src/services/calculators/position_valuation_calculator/app/core/reprocessing_worker.py
import logging
import asyncio
from datetime import date, timedelta, datetime

from portfolio_common.db import get_async_db_session
from ..repositories.valuation_repository import ValuationRepository
from portfolio_common.position_state_repository import PositionStateRepository
from portfolio_common.reprocessing_job_repository import ReprocessingJobRepository

logger = logging.getLogger(__name__)

class ReprocessingWorker:
    """
    A background worker that polls for and processes durable reprocessing jobs.
    """
    def __init__(self, poll_interval: int = 10, batch_size: int = 10):
        self._poll_interval = poll_interval
        self._batch_size = batch_size
        self._running = True

    def stop(self):
        logger.info("Reprocessing worker shutdown signal received.")
        self._running = False

    async def _process_batch(self):
        """Processes one batch of pending RESET_WATERMARKS jobs."""
        async for db in get_async_db_session():
            async with db.begin():
                job_repo = ReprocessingJobRepository(db)
                state_repo = PositionStateRepository(db)
                valuation_repo = ValuationRepository(db)

                claimed_jobs = await job_repo.find_and_claim_jobs('RESET_WATERMARKS', self._batch_size)
                
                for job in claimed_jobs:
                    try:
                        security_id = job.payload['security_id']
                        earliest_date = date.fromisoformat(job.payload['earliest_impacted_date'])
                        new_watermark = earliest_date - timedelta(days=1)
                        
                        affected_portfolios = await valuation_repo.find_portfolios_for_security(security_id)
                        
                        if affected_portfolios:
                            keys_to_update = [(p_id, security_id) for p_id in affected_portfolios]
                            updated_count = await state_repo.update_watermarks_if_older(
                                keys=keys_to_update,
                                new_watermark_date=new_watermark
                            )
                            logger.info(f"Job {job.id}: Fanned out watermark reset to {updated_count} portfolios for security {security_id}.")
                        else:
                            logger.info(f"Job {job.id}: No portfolios found for security {security_id}, skipping watermark reset.")
                        
                        await job_repo.update_job_status(job.id, 'COMPLETE')

                    except Exception as e:
                        logger.error(f"Failed to process reprocessing job {job.id}", exc_info=True)
                        await job_repo.update_job_status(job.id, 'FAILED', failure_reason=str(e))

    async def run(self):
        logger.info(f"ReprocessingWorker started. Polling every {self._poll_interval} seconds.")
        while self._running:
            try:
                await self._process_batch()
            except Exception:
                logger.error("Error in reprocessing worker polling loop.", exc_info=True)

            try:
                await asyncio.sleep(self._poll_interval)
            except asyncio.CancelledError:
                break
        
        logger.info("ReprocessingWorker has stopped.")