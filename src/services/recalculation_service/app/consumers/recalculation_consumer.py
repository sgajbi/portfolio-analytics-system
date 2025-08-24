# src/services/recalculation_service/app/consumers/recalculation_consumer.py
import logging
import asyncio
from typing import List

from portfolio_common.db import get_async_db_session
from ..core.recalculation_logic import RecalculationLogic
from ..repositories.recalculation_repository import RecalculationRepository, CoalescedRecalculationJob

logger = logging.getLogger(__name__)

class RecalculationJobConsumer:
    """
    A background worker that polls the recalculation_jobs table,
    claims and coalesces all eligible jobs for a security, and executes the 
    full recalculation for that portfolio/security pair.
    """
    def __init__(self, poll_interval: int = 10, batch_size: int = 1):
        self._poll_interval = poll_interval
        # batch_size is now managed by the repository logic, but we keep the parameter for consistency
        self._batch_size = batch_size
        self._running = True

    def stop(self):
        logger.info("Recalculation job consumer shutdown signal received.")
        self._running = False

    async def run(self):
        logger.info(f"RecalculationJobConsumer started. Polling every {self._poll_interval} seconds.")
        while self._running:
            coalesced_job: CoalescedRecalculationJob = None
            try:
                async for db in get_async_db_session():
                    repo = RecalculationRepository(db)
                    
                    async with db.begin():
                        # Atomically find and lock the next available job(s)
                        coalesced_job = await repo.find_and_claim_coalesced_job()

                    if coalesced_job:
                        primary_job = coalesced_job.claimed_jobs[0]
                        job_ids = [job.id for job in coalesced_job.claimed_jobs]
                        
                        logger.info(
                            f"Claimed {len(job_ids)} recalculation jobs for "
                            f"{primary_job.portfolio_id}/{primary_job.security_id}, coalesced from job {primary_job.id}."
                        )
                        
                        # Perform the full recalculation within a single, new transaction
                        async with db.begin():
                            await RecalculationLogic.execute(
                                db_session=db,
                                job_id=primary_job.id, # Used for tracing in headers
                                portfolio_id=primary_job.portfolio_id,
                                security_id=primary_job.security_id,
                                from_date=coalesced_job.earliest_from_date,
                                correlation_id=primary_job.correlation_id
                            )
                            # Mark all claimed jobs as complete only after the logic succeeds
                            await repo.update_job_status(job_ids, "COMPLETE")
                        
                        logger.info(f"Successfully completed and committed recalculation for jobs: {job_ids}.")
                    else:
                        logger.debug("No eligible recalculation jobs found in this poll cycle.")

            except Exception as e:
                job_ids_to_fail = [j.id for j in coalesced_job.claimed_jobs] if coalesced_job else []
                logger.error(
                    "Error in recalculation consumer polling loop.",
                    extra={"job_ids": job_ids_to_fail},
                    exc_info=True
                )
                # If jobs were claimed but failed during logic execution, mark them as FAILED
                if job_ids_to_fail:
                    try:
                        async for db in get_async_db_session():
                            async with db.begin():
                                repo = RecalculationRepository(db)
                                await repo.update_job_status(job_ids_to_fail, "FAILED")
                    except Exception as repo_exc:
                        logger.error(f"Failed to even mark jobs {job_ids_to_fail} as FAILED.", exc_info=repo_exc)

            try:
                await asyncio.sleep(self._poll_interval)
            except asyncio.CancelledError:
                break
        
        logger.info("RecalculationJobConsumer has stopped.")