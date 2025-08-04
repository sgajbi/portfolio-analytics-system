# services/calculators/position-valuation-calculator/app/consumer_manager.py
import logging
import signal
import asyncio

from portfolio_common.config import (
    KAFKA_BOOTSTRAP_SERVERS, 
    KAFKA_POSITION_HISTORY_PERSISTED_TOPIC,
    KAFKA_MARKET_PRICE_PERSISTED_TOPIC
)
from app.consumers.position_history_consumer import PositionHistoryConsumer
from app.consumers.market_price_consumer import MarketPriceConsumer
from portfolio_common.kafka_admin import ensure_topics_exist
from portfolio_common.kafka_utils import get_kafka_producer
from portfolio_common.outbox_dispatcher import OutboxDispatcher

logger = logging.getLogger(__name__)

class ConsumerManager:
    """
    Manages the lifecycle of Kafka consumers for the position valuation service.
    It instantiates, runs, and gracefully shuts down all consumer tasks.
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

        # NEW: Instantiate the dispatcher
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
        Sets up signal handling and runs consumer tasks.
        """
        required_topics = [consumer.topic for consumer in self.consumers]
        ensure_topics_exist(required_topics)

        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

        if not self.consumers:
            logger.warning("No consumers configured. Service will idle.")
            await self._shutdown_event.wait()
            logger.info("Shutdown event received. Exiting.")
            return

        logger.info("Starting all consumer tasks and the outbox dispatcher...")
        self.tasks = [asyncio.create_task(c.run()) for c in self.consumers]
        self.tasks.append(asyncio.create_task(self.dispatcher.run()))
        
        logger.info("ConsumerManager is running. Press Ctrl+C to exit.")
        await self._shutdown_event.wait()
        
        logger.info("Shutdown event received. Stopping all consumers and the dispatcher...")
        for consumer in self.consumers:
            consumer.shutdown()
        
        self.dispatcher.stop()
        
        await asyncio.gather(*self.tasks, return_exceptions=True)
        logger.info("All consumer and dispatcher tasks have been successfully shut down.")