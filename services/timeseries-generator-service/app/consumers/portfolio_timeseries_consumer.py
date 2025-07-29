import logging
import json
import asyncio
from pydantic import ValidationError
from datetime import date
from collections import defaultdict

from confluent_kafka import Message
from portfolio_common.kafka_consumer import BaseConsumer
from portfolio_common.events import PositionTimeseriesGeneratedEvent, PortfolioTimeseriesGeneratedEvent
from portfolio_common.db import get_db_session
from portfolio_common.database_models import Instrument
from portfolio_common.config import KAFKA_PORTFOLIO_TIMESERIES_GENERATED_TOPIC

from ..core.portfolio_timeseries_logic import PortfolioTimeseriesLogic
from ..repositories.timeseries_repository import TimeseriesRepository

logger = logging.getLogger(__name__)

class PortfolioTimeseriesConsumer(BaseConsumer):
    """
    Consumes position time series events and aggregates them into a daily
    portfolio time series record, handling potential race conditions.
    """

    async def process_message(self, msg: Message):
        try:
            event_data = json.loads(msg.value().decode('utf-8'))
            event = PositionTimeseriesGeneratedEvent.model_validate(event_data)
            
            # --- DEFINITIVE FIX: CONSOLIDATION DELAY ---
            # Wait for a short period to allow other parallel events for the same day to be processed.
            # This is a simple but effective way to handle race conditions in this scenario.
            await asyncio.sleep(5)
            
            logger.info(f"Aggregating portfolio time series for {event.portfolio_id} on {event.date}")
            
            with next(get_db_session()) as db:
                repo = TimeseriesRepository(db)
                
                portfolio = repo.get_portfolio(event.portfolio_id)
                if not portfolio:
                    logger.warning(f"Portfolio {event.portfolio_id} not found. Cannot aggregate.")
                    return

                position_timeseries_list = repo.get_all_position_timeseries_for_date(event.portfolio_id, event.date)
                portfolio_cashflows = repo.get_portfolio_level_cashflows_for_date(event.portfolio_id, event.date)
                
                instruments = {inst.security_id: inst for inst in db.query(Instrument).all()}
                
                fx_rates = {}
                portfolio_currency = portfolio.base_currency
                required_currencies = {instruments[pts.security_id].currency for pts in position_timeseries_list if pts.security_id in instruments}
                
                for currency in required_currencies:
                    if currency != portfolio_currency:
                        rate = repo.get_fx_rate(currency, portfolio_currency, event.date)
                        if rate:
                            fx_rates[currency] = rate

                new_portfolio_record = PortfolioTimeseriesLogic.calculate_daily_record(
                    portfolio=portfolio,
                    position_timeseries_list=position_timeseries_list,
                    portfolio_cashflows=portfolio_cashflows,
                    instruments=instruments,
                    fx_rates=fx_rates
                )

                repo.upsert_portfolio_timeseries(new_portfolio_record)

                if self._producer:
                    completion_event = PortfolioTimeseriesGeneratedEvent.model_validate(new_portfolio_record)
                    self._producer.publish_message(
                        topic=KAFKA_PORTFOLIO_TIMESERIES_GENERATED_TOPIC,
                        key=completion_event.portfolio_id,
                        value=completion_event.model_dump(mode='json')
                    )
                    self._producer.flush(timeout=5)

        except (json.JSONDecodeError, ValidationError) as e:
            logger.error(f"Message validation failed: {e}. Sending to DLQ.", exc_info=True)
            await self._send_to_dlq(msg, e)
        except Exception as e:
            logger.error(f"Unexpected error processing message: {e}", exc_info=True)
            await self._send_to_dlq(msg, e)