# services/persistence-service/app/consumer_manager.py
import logging
import signal
import asyncio
from portfolio_common.config import (
    KAFKA_BOOTSTRAP_SERVERS, 
    KAFKA_RAW_TRANSACTIONS_TOPIC,
    KAFKA_INSTRUMENTS_TOPIC,
    KAFKA_MARKET_PRICES_TOPIC,
    KAFKA_FX_RATES_TOPIC,
    KAFKA_RAW_PORTFOLIOS_TOPIC,
    KAFKA_PERSISTENCE_DLQ_TOPIC
)
from .consumers.transaction_consumer import TransactionPersistenceConsumer
from .consumers.instrument_consumer import InstrumentConsumer
from .consumers.market_price_consumer import MarketPriceConsumer
from .consumers.fx_rate_consumer import FxRateConsumer
from .consumers.portfolio_consumer import PortfolioConsumer

logger = logging.getLogger(__name__)

class ConsumerManager:
    """
    Manages the lifecycle of Kafka consumers for various topics.
    It instantiates, runs, and gracefully shuts down all consumer tasks.
    """
    def __init__(self):
        self.consumers = []
        self.tasks = []
        self._shutdown_event = asyncio.Event()
        
        dlq_topic = KAFKA_PERSISTENCE_DLQ_TOPIC
        service_prefix = "PST"
        
        self.consumers.append(
            PortfolioConsumer(
                bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
                topic=KAFKA_RAW_PORTFOLIOS_TOPIC,
                group_id="persistence_group_portfolios",
                dlq_topic=dlq_topic,
                service_prefix=service_prefix
            )
        )
        self.consumers.append(
            TransactionPersistenceConsumer(
                bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
                topic=KAFKA_RAW_TRANSACTIONS_TOPIC,
                group_id="persistence_group_transactions",
                dlq_topic=dlq_topic,
                service_prefix=service_prefix
            )
        )
        self.consumers.append(
            InstrumentConsumer(
                bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
                topic=KAFKA_INSTRUMENTS_TOPIC,
                group_id="persistence_group_instruments",
                dlq_topic=dlq_topic,
                service_prefix=service_prefix
            )
        )
        self.consumers.append(
            MarketPriceConsumer(
                bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
                topic=KAFKA_MARKET_PRICES_TOPIC,
                group_id="persistence_group_market_prices",
                dlq_topic=dlq_topic,
                service_prefix=service_prefix
            )
        )
        self.consumers.append(
            FxRateConsumer(
                bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
                topic=KAFKA_FX_RATES_TOPIC,
                group_id="persistence_group_fx_rates",
                dlq_topic=dlq_topic,
                service_prefix=service_prefix
            )
        )

        logger.info("ConsumerManager initialized", extra={"num_consumers": len(self.consumers)})

    def _signal_handler(self, signum, frame):
        """Sets the shutdown event when a signal is received."""
        logger.info("Shutdown signal received", extra={"signal": signal.Signals(signum).name})
        self._shutdown_event.set()

    async def run(self):
        """
        The main execution function.
        Sets up signal handling and runs consumer tasks.
        """
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

        logger.info("Starting all consumer tasks...")
        self.tasks = [asyncio.create_task(c.run()) for c in self.consumers]
        
        logger.info("ConsumerManager is running. Press Ctrl+C to exit.")
        await self._shutdown_event.wait()
        
        logger.info("Shutdown event received. Stopping all consumers...")
        for consumer in self.consumers:
            consumer.shutdown() # Tell each consumer to stop its loop
        
        # Wait for all tasks to complete
        await asyncio.gather(*self.tasks, return_exceptions=True)
        logger.info("All consumer tasks have been successfully shut down.")