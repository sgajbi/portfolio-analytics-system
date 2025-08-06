# services/timeseries-generator-service/app/consumers/portfolio_timeseries_consumer.py
import logging
import json
import asyncio
from pydantic import ValidationError
from datetime import date
from typing import Dict, Tuple, Optional, List

from confluent_kafka import Message
from sqlalchemy.exc import IntegrityError
from sqlalchemy import select
from tenacity import retry, stop_after_attempt, wait_fixed, before_log, retry_if_exception_type

from portfolio_common.kafka_consumer import BaseConsumer
from portfolio_common.logging_utils import correlation_id_var
from portfolio_common.events import PositionTimeseriesGeneratedEvent, PortfolioTimeseriesGeneratedEvent
from portfolio_common.db import get_async_db_session
from portfolio_common.database_models import Instrument
from portfolio_common.config import KAFKA_PORTFOLIO_TIMESERIES_GENERATED_TOPIC

from ..core.portfolio_timeseries_logic import PortfolioTimeseriesLogic, FxRateNotFoundError
from ..repositories.timeseries_repository import TimeseriesRepository

logger = logging.getLogger(__name__)

class PortfolioTimeseriesConsumer(BaseConsumer):
    """
    Consumes position time series events and aggregates them into a daily
    portfolio time series record using a time-windowed batching approach to
    handle race conditions.
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._batch: Dict[Tuple[str, date], str] = {}
        self._batch_lock = asyncio.Lock()
        self._processing_interval = 5

    async def process_message(self, msg: Message):
        """
        Instead of processing immediately, adds the work to a batch.
        """
        try:
            event_data = json.loads(msg.value().decode('utf-8'))
            event = PositionTimeseriesGeneratedEvent.model_validate(event_data)
            correlation_id = correlation_id_var.get()
            
            async with self._batch_lock:
                self._batch[(event.portfolio_id, event.date)] = correlation_id
            
            self._consumer.commit(message=msg, asynchronous=False)

        except (json.JSONDecodeError, ValidationError) as e:
            logger.error(f"Message validation failed: {e}. Sending to DLQ.", exc_info=True)
            await self._send_to_dlq_async(msg, e)

    async def _process_batch(self):
        """
        Periodically processes the collected batch of work.
        """
        while self._running:
            await asyncio.sleep(self._processing_interval)
            
            async with self._batch_lock:
                if not self._batch:
                    continue
                current_work = self._batch.copy()
                self._batch.clear()

            logger.info(f"Processing batch of {len(current_work)} portfolio-date aggregations.")
            
            tasks = [
                self._aggregate_for_portfolio_date(portfolio_id, a_date, correlation_id)
                for (portfolio_id, a_date), correlation_id in current_work.items()
            ]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            for result in results:
                if isinstance(result, Exception):
                    logger.error(f"Failed to process aggregation batch item: {result}", exc_info=result)

    @retry(
        wait=wait_fixed(3),
        stop=stop_after_attempt(5),
        before=before_log(logger, logging.INFO),
        retry=retry_if_exception_type((IntegrityError, FxRateNotFoundError)),
        retry_error_callback=lambda _: None
    )
    async def _aggregate_for_portfolio_date(self, portfolio_id: str, a_date: date, correlation_id: Optional[str]):
        """
        Contains the full aggregation logic for a single portfolio and date.
        """
        async for db in get_async_db_session():
            async with db.begin():
                repo = TimeseriesRepository(db)
                
                portfolio = await repo.get_portfolio(portfolio_id)
                if not portfolio:
                    logger.warning(f"Portfolio {portfolio_id} not found. Cannot aggregate.")
                    return

                position_timeseries_list = await repo.get_all_position_timeseries_for_date(portfolio_id, a_date)
                portfolio_cashflows = await repo.get_portfolio_level_cashflows_for_date(portfolio_id, a_date)
                
                instrument_results = await db.execute(select(Instrument))
                instruments = {inst.security_id: inst for inst in instrument_results.scalars().all()}
                fx_rates = {}
                portfolio_currency = portfolio.base_currency
                required_currencies = {instruments[pts.security_id].currency for pts in position_timeseries_list if pts.security_id in instruments}
                
                for currency in required_currencies:
                    if currency != portfolio_currency:
                        rate = await repo.get_fx_rate(currency, portfolio_currency, a_date)
                        if rate:
                            fx_rates[currency] = rate

                new_portfolio_record = PortfolioTimeseriesLogic.calculate_daily_record(
                    portfolio=portfolio,
                    a_date=a_date,
                    position_timeseries_list=position_timeseries_list,
                    portfolio_cashflows=portfolio_cashflows,
                    instruments=instruments,
                    fx_rates=fx_rates
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

    async def run(self):
        """
        Overrides the BaseConsumer's run method to start the batch processor
        alongside the message polling loop.
        """
        self._initialize_consumer()
        loop = asyncio.get_running_loop()
        
        batch_processor_task = loop.create_task(self._process_batch())
        logger.info(f"Started background batch processor with a {self._processing_interval}s window.")

        logger.info(f"Starting to consume messages from topic '{self.topic}'...")
        while self._running:
            msg = await loop.run_in_executor(None, self._consumer.poll, 1.0)
            if msg is None: continue
            if msg.error():
                if msg.error().fatal():
                    logger.error(f"Fatal consumer error: {msg.error()}. Shutting down.", exc_info=True)
                    break
                else:
                    logger.warning(f"Non-fatal consumer error: {msg.error()}.")
                    continue
            
            await self.process_message(msg)
        
        batch_processor_task.cancel()
        self.shutdown()