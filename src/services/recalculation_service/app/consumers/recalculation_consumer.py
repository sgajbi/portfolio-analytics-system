# src/services/recalculation_service/app/consumers/recalculation_consumer.py
import logging
import asyncio
from typing import List

from portfolio_common.db import get_async_db_session
from ..core.recalculation_logic import RecalculationLogic
from ..repositories.recalculation_repository import RecalculationRepository

logger = logging.getLogger(__name__)

class RecalculationJobConsumer:
    """
    A background worker that polls the recalculation_jobs table,
    claims an eligible job, and executes the full recalculation
    for that portfolio/security pair.
    """
    def __init__(self, poll_interval: int = 10, batch_size: int = 1):
        self._poll_interval = poll_interval
        self._batch_size = batch_size
        self._running = True

    def stop(self):
        logger.info("Recalculation job consumer shutdown signal received.")
        self._running = False

    async def run(self):
        logger.info(f"RecalculationJobConsumer started. Polling every {self._poll_interval} seconds.")
        while self._running:
            job_to_process = None
            try:
                async for db in get_async_db_session():
                    repo = RecalculationRepository(db)
                    
                    async with db.begin():
                        # Atomically find and lock the next available job
                        job_to_process = await repo.find_and_claim_job()

                    if job_to_process:
                        logger.info(
                            f"Claimed recalculation job {job_to_process.id} for "
                            f"{job_to_process.portfolio_id}/{job_to_process.security_id}"
                        )
                        
                        # Perform the full recalculation within a single, new transaction
                        async with db.begin():
                            await RecalculationLogic.execute(
                                db_session=db,
                                job_id=job_to_process.id,
                                portfolio_id=job_to_process.portfolio_id,
                                security_id=job_to_process.security_id,
                                from_date=job_to_process.from_date,
                                correlation_id=job_to_process.correlation_id
                            )
                            # Mark the job as complete only after the logic succeeds
                            await repo.update_job_status(job_to_process.id, "COMPLETE")
                        
                        logger.info(f"Successfully completed and committed recalculation for job {job_to_process.id}.")
                    else:
                        logger.debug("No eligible recalculation jobs found in this poll cycle.")

            except Exception as e:
                logger.error(
                    "Error in recalculation consumer polling loop.",
                    extra={"job_id": job_to_process.id if job_to_process else "N/A"},
                    exc_info=True
                )
                # If a job was claimed but failed during logic execution, mark it as FAILED
                if job_to_process:
                    try:
                        async for db in get_async_db_session():
                            async with db.begin():
                                repo = RecalculationRepository(db)
                                await repo.update_job_status(job_to_process.id, "FAILED")
                    except Exception as repo_exc:
                        logger.error(f"Failed to even mark job {job_to_process.id} as FAILED.", exc_info=repo_exc)

            try:
                await asyncio.sleep(self._poll_interval)
            except asyncio.CancelledError:
                break
        
        logger.info("RecalculationJobConsumer has stopped.")