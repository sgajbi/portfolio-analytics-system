import logging
import signal
import asyncio

from portfolio_common.config import KAFKA_BOOTSTRAP_SERVERS, KAFKA_PROCESSED_TRANSACTIONS_COMPLETED_TOPIC
from .consumers.transaction_event_consumer import TransactionEventConsumer

logger = logging.getLogger(__name__)

class ConsumerManager:
    """
    Manages the lifecycle of Kafka consumers for the position calculator.
    """
    def __init__(self):
        self.consumers = []
        self.tasks = []
        self._shutdown_event = asyncio.Event()
        
        self.consumers.append(
            TransactionEventConsumer(
                bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
                topic=KAFKA_PROCESSED_TRANSACTIONS_COMPLETED_TOPIC,
                group_id="position_calculator_group"
            )
        )
        logger.info(f"ConsumerManager initialized with {len(self.consumers)} consumer(s).")

    def _signal_handler(self, signum, frame):
        logger.info(f"Received shutdown signal: {signal.Signals(signum).name}. Initiating graceful shutdown...")
        self._shutdown_event.set()

    async def run(self):
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

        logger.info("Starting all consumer tasks...")
        self.tasks = [asyncio.create_task(c.run()) for c in self.consumers]
        
        logger.info("ConsumerManager is running. Press Ctrl+C to exit.")
        await self._shutdown_event.wait()
        
        logger.info("Shutdown event received. Stopping all consumers...")
        for consumer in self.consumers:
            consumer.shutdown()
        
        await asyncio.gather(*self.tasks, return_exceptions=True)
        logger.info("All consumer tasks have been successfully shut down.")