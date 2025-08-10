# src/services/timeseries_generator_service/app/consumers/portfolio_timeseries_consumer.py
import logging
import json
from pydantic import ValidationError
from datetime import date
from typing import Optional
from sqlalchemy import update

from confluent_kafka import Message

from portfolio_common.kafka_consumer import BaseConsumer
from portfolio_common.logging_utils import correlation_id_var
from portfolio_common.events import PortfolioAggregationRequiredEvent, PortfolioTimeseriesGeneratedEvent
from portfolio_common.db import get_async_db_session
from portfolio_common.database_models import PortfolioAggregationJob
from portfolio_common.config import KAFKA_PORTFOLIO_TIMESERIES_GENERATED_TOPIC
from portfolio_common.outbox_repository import OutboxRepository

from ..core.portfolio_timeseries_logic import PortfolioTimeseriesLogic
from ..repositories.timeseries_repository import TimeseriesRepository

logger = logging.getLogger(__name__)

class PortfolioTimeseriesConsumer(BaseConsumer):
    """
    Consumes scheduled aggregation jobs, calculates the daily portfolio time series
    record, and updates the job status upon completion.
    """

    async def process_message(self, msg: Message):
        """
        Processes a single aggregation job event from the scheduler.
        """
        try:
            event_data = json.loads(msg.value().decode('utf-8'))
            event = PortfolioAggregationRequiredEvent.model_validate(event_data)
            correlation_id = correlation_id_var.get()
            
            work_key = (event.portfolio_id, event.aggregation_date)
            logger.info(f"Received aggregation job for {work_key}.")
            
            await self._perform_aggregation(
                portfolio_id=event.portfolio_id,
                a_date=event.aggregation_date,
                correlation_id=correlation_id
            )

        except (json.JSONDecodeError, ValidationError) as e:
            logger.error(f"Message validation for aggregation job failed: {e}. Sending to DLQ.", exc_info=True)
            await self._send_to_dlq_async(msg, e)
        except Exception as e:
            logger.error(f"Unexpected error processing aggregation job for {msg.key()}: {e}", exc_info=True)
            # Mark the job as FAILED before sending the trigger message to DLQ
            event = locals().get('event')
            if event:
                await self._update_job_status(event.portfolio_id, event.aggregation_date, 'FAILED')
            await self._send_to_dlq_async(msg, e)

    async def _perform_aggregation(self, portfolio_id: str, a_date: date, correlation_id: Optional[str]):
        """
        Contains the full aggregation logic for a single portfolio and date,
        executed within a single atomic transaction.
        """
        try:
            async for db in get_async_db_session():
                async with db.begin():  # Main atomic transaction
                    repo = TimeseriesRepository(db)
                    outbox_repo = OutboxRepository(db)
                    
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

                    completion_event = PortfolioTimeseriesGeneratedEvent.model_validate(new_portfolio_record)
                    
                    await outbox_repo.create_outbox_event(
                        aggregate_type='PortfolioTimeseries',
                        aggregate_id=str(portfolio_id),
                        event_type='PortfolioTimeseriesGenerated',
                        topic=KAFKA_PORTFOLIO_TIMESERIES_GENERATED_TOPIC,
                        payload=completion_event.model_dump(mode='json'),
                        correlation_id=correlation_id
                    )
                    
                    await self._update_job_status(portfolio_id, a_date, 'COMPLETE', db_session=db)
                    logger.info(f"Aggregation job for ({portfolio_id}, {a_date}) transactionally completed.")

        except Exception:
            logger.error(f"Aggregation failed for ({portfolio_id}, {a_date}). Marking job as FAILED.", exc_info=True)
            await self._update_job_status(portfolio_id, a_date, 'FAILED')
            
    
    async def _update_job_status(self, portfolio_id: str, a_date: date, status: str, db_session=None):
        """
        Updates a job's status. If no session is provided, it creates a new one.
        """
        update_stmt = update(PortfolioAggregationJob).where(
            PortfolioAggregationJob.portfolio_id == portfolio_id,
            PortfolioAggregationJob.aggregation_date == a_date
        ).values(status=status)

        if db_session:
            await db.execute(update_stmt)
        else:
            async for db in get_async_db_session():
                async with db.begin():
                    await db.execute(update_stmt)