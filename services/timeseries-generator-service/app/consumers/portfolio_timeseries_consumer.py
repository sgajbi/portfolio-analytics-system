# services/timeseries-generator-service/app/consumers/portfolio_timeseries_consumer.py
import logging
import json
import asyncio
from pydantic import ValidationError
from datetime import date
from typing import Optional
from sqlalchemy import update

from confluent_kafka import Message
from sqlalchemy.exc import IntegrityError
from tenacity import retry, stop_after_attempt, wait_fixed, before_log, retry_if_exception_type

from portfolio_common.kafka_consumer import BaseConsumer
from portfolio_common.logging_utils import correlation_id_var
from portfolio_common.events import PositionTimeseriesGeneratedEvent, PortfolioTimeseriesGeneratedEvent
from portfolio_common.db import get_async_db_session
from portfolio_common.database_models import PortfolioAggregationJob
from portfolio_common.config import KAFKA_PORTFOLIO_TIMESERIES_GENERATED_TOPIC

from ..core.portfolio_timeseries_logic import PortfolioTimeseriesLogic, FxRateNotFoundError
from ..repositories.timeseries_repository import TimeseriesRepository

logger = logging.getLogger(__name__)

class PortfolioTimeseriesConsumer(BaseConsumer):
    """
    Consumes position time series events. Uses a database table as a distributed
    lock to perform a final, idempotent aggregation into a daily portfolio time series record.
    """

    async def process_message(self, msg: Message):
        """
        Receives a signal that a portfolio/date might need aggregation. It attempts to
        claim a job from the portfolio_aggregation_jobs table, which acts as a
        distributed lock to prevent race conditions.
        """
        try:
            event_data = json.loads(msg.value().decode('utf-8'))
            event = PositionTimeseriesGeneratedEvent.model_validate(event_data)
            correlation_id = correlation_id_var.get()
            
            work_key = (event.portfolio_id, event.date)
            
            async for db in get_async_db_session():
                async with db.begin():
                    # Atomically claim the job. This is our distributed lock.
                    claim_stmt = update(PortfolioAggregationJob).where(
                        PortfolioAggregationJob.portfolio_id == event.portfolio_id,
                        PortfolioAggregationJob.aggregation_date == event.date,
                        PortfolioAggregationJob.status == 'PENDING'
                    ).values(
                        status='PROCESSING',
                        correlation_id=correlation_id
                    )
                    result = await db.execute(claim_stmt)

                    # If rowcount is 0, another consumer instance claimed this job. We can safely stop.
                    if result.rowcount == 0:
                        logger.info(f"Aggregation job for {work_key} already claimed or completed. Skipping.")
                        return

            # If we successfully claimed the job, proceed with aggregation in a new transaction.
            logger.info(f"Successfully claimed aggregation job for {work_key}. Starting aggregation.")
            await self._perform_aggregation(event.portfolio_id, event.date, correlation_id)

        except (json.JSONDecodeError, ValidationError) as e:
            logger.error(f"Message validation failed: {e}. Sending to DLQ.", exc_info=True)
            # We don't have a job to fail here, so just DLQ the trigger message
            await self._send_to_dlq_async(msg, e)
        except Exception as e:
            logger.error(f"Unexpected error when trying to claim aggregation job for {msg.key()}: {e}", exc_info=True)
            # Again, DLQ the trigger message as we cannot update the job status.
            await self._send_to_dlq_async(msg, e)

    @retry(
        wait=wait_fixed(3),
        stop=stop_after_attempt(5),
        before=before_log(logger, logging.INFO),
        retry=retry_if_exception_type((IntegrityError, FxRateNotFoundError)),
        reraise=True # Reraise the exception to be caught by the outer handler
    )
    async def _perform_aggregation(self, portfolio_id: str, a_date: date, correlation_id: Optional[str]):
        """
        Contains the full aggregation logic for a single portfolio and date.
        This is now a separate, retryable unit of work.
        """
        job_status_to_set = 'FAILED'
        try:
            async for db in get_async_db_session():
                async with db.begin():
                    repo = TimeseriesRepository(db)
                    
                    portfolio = await repo.get_portfolio(portfolio_id)
                    if not portfolio:
                        logger.error(f"Portfolio {portfolio_id} not found during aggregation. Failing job.")
                        return # The job will be marked as FAILED in the finally block.

                    # The core aggregation logic remains the same
                    position_timeseries_list = await repo.get_all_position_timeseries_for_date(portfolio_id, a_date)
                    portfolio_cashflows = await repo.get_portfolio_level_cashflows_for_date(portfolio_id, a_date)
                    
                    new_portfolio_record = await PortfolioTimeseriesLogic.calculate_daily_record(
                        portfolio=portfolio,
                        a_date=a_date,
                        position_timeseries_list=position_timeseries_list,
                        portfolio_cashflows=portfolio_cashflows,
                        repo=repo # Pass repo to the logic function
                    )

                    await repo.upsert_portfolio_timeseries(new_portfolio_record)

                    if self._producer:
                        completion_event = PortfolioTimeseriesGeneratedEvent.model_validate(new_portfolio_record)
                        headers = [('correlation_id', correlation_id.encode('utf-8'))] if correlation_id else None
                        
                        self._producer.publish_message(
                            topic=KAFKA_PORTFOLIO_TIMESERIES_GENERATED_TOPIC,
                            key=completion_event.portfolio_id,
                            value=completion_event.model_dump(mode='json'),
                            headers=headers
                        )
                        self._producer.flush(timeout=5)
                    
                    job_status_to_set = 'COMPLETE' # Mark for success
        
        finally:
            # Final step: Update the job status to COMPLETE or FAILED in a separate transaction
            async for db in get_async_db_session():
                async with db.begin():
                    await db.execute(
                        update(PortfolioAggregationJob).where(
                            PortfolioAggregationJob.portfolio_id == portfolio_id,
                            PortfolioAggregationJob.aggregation_date == a_date
                        ).values(status=job_status_to_set)
                    )
            logger.info(f"Aggregation job for ({portfolio_id}, {a_date}) marked as {job_status_to_set}.")