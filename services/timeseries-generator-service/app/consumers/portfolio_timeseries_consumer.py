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
from portfolio_common.outbox_repository import OutboxRepository

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
                    ).returning(PortfolioAggregationJob.id) # Return ID to confirm success
                    
                    result = await db.execute(claim_stmt)
                    job_id = result.scalar_one_or_none()

                    # If job_id is None, another consumer instance claimed this job. We can safely stop.
                    if not job_id:
                        logger.info(f"Aggregation job for {work_key} already claimed or completed. Skipping.")
                        return

            # If we successfully claimed the job, proceed with aggregation.
            logger.info(f"Successfully claimed aggregation job for {work_key}. Starting aggregation.")
            await self._perform_aggregation(event.portfolio_id, event.date, correlation_id)

        except (json.JSONDecodeError, ValidationError) as e:
            logger.error(f"Message validation failed: {e}. Sending to DLQ.", exc_info=True)
            await self._send_to_dlq_async(msg, e)
        except Exception as e:
            logger.error(f"Unexpected error when trying to claim aggregation job for {msg.key()}: {e}", exc_info=True)
            await self._send_to_dlq_async(msg, e)

    @retry(
        wait=wait_fixed(3),
        stop=stop_after_attempt(3), # Reduced retries as failures should be marked in DB
        before=before_log(logger, logging.INFO),
        retry=retry_if_exception_type(FxRateNotFoundError),
        reraise=True
    )
    async def _perform_aggregation(self, portfolio_id: str, a_date: date, correlation_id: Optional[str]):
        """
        Contains the full aggregation logic for a single portfolio and date,
        executed within a single atomic transaction.
        """
        try:
            async for db in get_async_db_session():
                async with db.begin(): # Main atomic transaction
                    repo = TimeseriesRepository(db)
                    outbox_repo = OutboxRepository()
                    
                    portfolio = await repo.get_portfolio(portfolio_id)
                    if not portfolio:
                        raise ValueError(f"Portfolio {portfolio_id} not found during aggregation.")

                    position_timeseries_list = await repo.get_all_position_timeseries_for_date(portfolio_id, a_date)
                    portfolio_cashflows = await repo.get_portfolio_level_cashflows_for_date(portfolio_id, a_date)
                    
                    new_portfolio_record = await PortfolioTimeseriesLogic.calculate_daily_record(
                        portfolio=portfolio,
                        a_date=a_date,
                        position_timeseries_list=position_timeseries_list,
                        portfolio_cashflows=portfolio_cashflows,
                        repo=repo
                    )

                    await repo.upsert_portfolio_timeseries(new_portfolio_record)

                    # Create outbox event for completion
                    completion_event = PortfolioTimeseriesGeneratedEvent.model_validate(new_portfolio_record)
                    outbox_repo.create_outbox_event(
                        db_session=db,
                        aggregate_type='PortfolioTimeseries',
                        aggregate_id=f"{portfolio_id}:{a_date.isoformat()}",
                        event_type='PortfolioTimeseriesGenerated',
                        topic=KAFKA_PORTFOLIO_TIMESERIES_GENERATED_TOPIC,
                        payload=completion_event.model_dump(mode='json'),
                        correlation_id=correlation_id
                    )
                    
                    # Mark the job as COMPLETE
                    await db.execute(
                        update(PortfolioAggregationJob).where(
                            PortfolioAggregationJob.portfolio_id == portfolio_id,
                            PortfolioAggregationJob.aggregation_date == a_date
                        ).values(status='COMPLETE')
                    )
                    logger.info(f"Aggregation job for ({portfolio_id}, {a_date}) transactionally completed.")

        except Exception as e:
            # If any part of the try block fails, the transaction is rolled back.
            # We now mark the job as FAILED in a new, separate transaction.
            logger.error(f"Aggregation failed for ({portfolio_id}, {a_date}). Marking job as FAILED.", exc_info=True)
            async for db in get_async_db_session():
                async with db.begin():
                    await db.execute(
                        update(PortfolioAggregationJob).where(
                            PortfolioAggregationJob.portfolio_id == portfolio_id,
                            PortfolioAggregationJob.aggregation_date == a_date
                        ).values(status='FAILED')
                    )
            raise # Re-raise to allow tenacity to handle it