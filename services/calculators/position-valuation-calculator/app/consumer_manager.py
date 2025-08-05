# services/calculators/position-valuation-calculator/app/consumer_manager.py
import logging
import signal
import asyncio
import uvicorn

from portfolio_common.config import (
    KAFKA_BOOTSTRAP_SERVERS, 
    KAFKA_POSITION_HISTORY_PERSISTED_TOPIC,
    KAFKA_MARKET_PRICE_PERSISTED_TOPIC
)
from .consumers.position_history_consumer import PositionHistoryConsumer
from .consumers.market_price_consumer import MarketPriceConsumer
from portfolio_common.kafka_admin import ensure_topics_exist
from portfolio_common.kafka_utils import get_kafka_producer
from portfolio_common.outbox_dispatcher import OutboxDispatcher
from .web import app as web_app

logger = logging.getLogger(__name__)

class ConsumerManager:
    """
    Manages the lifecycle of Kafka consumers, the outbox dispatcher,
    and the new health probe web server.
    """
    def __init__(self):
        self.consumers = []
        self.tasks = []
        self._shutdown_event = asyncio.Event()
        
        group_id = "position_valuation_group"
        service_prefix = "VAL"
        
        self.consumers.append(
            PositionHistoryConsumer(
                bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
                topic=KAFKA_POSITION_HISTORY_PERSISTED_TOPIC,
                group_id=f"{group_id}_positions",
                service_prefix=service_prefix 
            )
        )
        self.consumers.append(
            MarketPriceConsumer(
                bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
                topic=KAFKA_MARKET_PRICE_PERSISTED_TOPIC,
                group_id=f"{group_id}_prices",
                service_prefix=service_prefix 
            )
        )

        kafka_producer = get_kafka_producer()
        self.dispatcher = OutboxDispatcher(kafka_producer=kafka_producer)

        logger.info(f"ConsumerManager initialized with {len(self.consumers)} consumer(s).")

    def _signal_handler(self, signum, frame):
        """Sets the shutdown event when a signal is received."""
        logger.info(f"Received shutdown signal: {signal.Signals(signum).name}. Initiating graceful shutdown...")
        self._shutdown_event.set()

    async def run(self):
        """
        The main execution function.
        """
        required_topics = [consumer.topic for consumer in self.consumers]
        ensure_topics_exist(required_topics)

        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
        
        uvicorn_config = uvicorn.Config(web_app, host="0.0.0.0", port=8084, log_config=None)
        server = uvicorn.Server(uvicorn_config)

        logger.info("Starting all consumer tasks, the outbox dispatcher, and the web server...")
        self.tasks = [asyncio.create_task(c.run()) for c in self.consumers]
        self.tasks.append(asyncio.create_task(self.dispatcher.run()))
        self.tasks.append(asyncio.create_task(server.serve()))
        
        logger.info("ConsumerManager is running. Press Ctrl+C to exit.")
        await self._shutdown_event.wait()
        
        logger.info("Shutdown event received. Stopping all tasks...")
        for consumer in self.consumers:
            consumer.shutdown()
        
        self.dispatcher.stop()
        server.should_exit = True
        
        await asyncio.gather(*self.tasks, return_exceptions=True)
        logger.info("All consumer and dispatcher tasks have been successfully shut down.")