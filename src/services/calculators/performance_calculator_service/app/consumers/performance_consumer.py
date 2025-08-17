# src/services/calculators/performance_calculator_service/app/consumers/performance_consumer.py
import logging
import json
from decimal import Decimal

from pydantic import ValidationError
from confluent_kafka import Message
from sqlalchemy.exc import DBAPIError
from tenacity import retry, stop_after_attempt, wait_fixed, before_log, retry_if_exception_type

from portfolio_common.kafka_consumer import BaseConsumer
from portfolio_common.logging_utils import correlation_id_var
from portfolio_common.events import PortfolioTimeseriesGeneratedEvent, PerformanceCalculatedEvent
from portfolio_common.db import get_async_db_session
from portfolio_common.idempotency_repository import IdempotencyRepository
from portfolio_common.outbox_repository import OutboxRepository
from portfolio_common.config import KAFKA_PERFORMANCE_CALCULATED_TOPIC
from portfolio_common.database_models import DailyPerformanceMetric

from performance_calculator_engine.calculator import PerformanceEngine
from performance_calculator_engine.constants import METRIC_BASIS_NET, METRIC_BASIS_GROSS
from ..repositories.performance_repository import PerformanceRepository
from ..repositories.timeseries_repository import TimeseriesRepository


logger = logging.getLogger(__name__)
SERVICE_NAME = "performance-calculator"

class DataNotFoundError(Exception):
    """Custom exception for retryable data fetching errors."""
    pass


class PerformanceCalculatorConsumer(BaseConsumer):
    """
    Consumes portfolio timeseries events, calculates daily performance metrics,
    persists them, and emits a completion event to the outbox.
    """
    @retry(
        wait=wait_fixed(3),
        stop=stop_after_attempt(5),
        before=before_log(logger, logging.INFO),
        retry=retry_if_exception_type((DBAPIError, DataNotFoundError)),
        reraise=True
    )
    async def process_message(self, msg: Message):
        event_id = f"{msg.topic()}-{msg.partition()}-{msg.offset()}"
        correlation_id = correlation_id_var.get()
        
        try:
            event_data = json.loads(msg.value().decode('utf-8'))
            event = PortfolioTimeseriesGeneratedEvent.model_validate(event_data)

            async for db in get_async_db_session():
                async with db.begin():
                    idempotency_repo = IdempotencyRepository(db)
                    if await idempotency_repo.is_event_processed(event_id, SERVICE_NAME):
                        logger.warning(f"Event {event_id} already processed. Skipping.")
                        return

                    ts_repo = TimeseriesRepository(db)
                    perf_repo = PerformanceRepository(db)
                    outbox_repo = OutboxRepository(db)

                    # Fetch required data for calculation
                    current_day_ts = await ts_repo.get_portfolio_timeseries_for_date(event.portfolio_id, event.date)
                    previous_day_ts = await ts_repo.get_last_portfolio_timeseries_before(event.portfolio_id, event.date)
                    
                    if not current_day_ts:
                        raise DataNotFoundError(f"Timeseries data for {event.portfolio_id} on {event.date} not found. Retrying.")

                    # Calculate metrics using the engine
                    daily_returns = PerformanceEngine.calculate_daily_metrics(
                        current_day_ts.to_dict(),
                        previous_day_ts.to_dict() if previous_day_ts else None
                    )

                    # Prepare records for persistence
                    metrics_to_save = []
                    for basis, daily_return in daily_returns.items():
                        linking_factor = Decimal(1) + (daily_return / Decimal(100))
                        metrics_to_save.append(
                            DailyPerformanceMetric(
                                portfolio_id=event.portfolio_id,
                                date=event.date,
                                return_basis=basis,
                                daily_return_pct=daily_return,
                                linking_factor=linking_factor
                            )
                        )
                    
                    await perf_repo.upsert_daily_metrics(metrics_to_save)

                    # Create completion event
                    completion_event = PerformanceCalculatedEvent(portfolio_id=event.portfolio_id, date=event.date)
                    await outbox_repo.create_outbox_event(
                        aggregate_type='PerformanceMetric',
                        aggregate_id=str(event.portfolio_id),
                        event_type='PerformanceCalculated',
                        topic=KAFKA_PERFORMANCE_CALCULATED_TOPIC,
                        payload=completion_event.model_dump(mode='json'),
                        correlation_id=correlation_id
                    )

                    await idempotency_repo.mark_event_processed(
                        event_id, event.portfolio_id, SERVICE_NAME, correlation_id
                    )
        
        except (json.JSONDecodeError, ValidationError) as e:
            logger.error(f"Message validation failed. Sending to DLQ.", exc_info=True)
            await self._send_to_dlq_async(msg, e)
        except (DBAPIError, DataNotFoundError) as e:
            logger.warning(f"A recoverable error occurred: {e}. Retrying...")
            raise
        except Exception as e:
            logger.error(f"Unexpected error processing message. Sending to DLQ.", exc_info=True)
            await self._send_to_dlq_async(msg, e)