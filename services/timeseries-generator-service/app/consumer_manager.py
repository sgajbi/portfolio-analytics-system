# services/timeseries-generator-service/app/consumer_manager.py
import logging
import signal
import asyncio
import uvicorn

from portfolio_common.config import (
    KAFKA_BOOTSTRAP_SERVERS,
    KAFKA_DAILY_POSITION_SNAPSHOT_PERSISTED_TOPIC,
    KAFKA_POSITION_TIMESERIES_GENERATED_TOPIC,
    KAFKA_PERSISTENCE_DLQ_TOPIC
)
from .consumers.position_timeseries_consumer import PositionTimeseriesConsumer
from .consumers.portfolio_timeseries_consumer import PortfolioTimeseriesConsumer
from portfolio_common.kafka_admin import ensure_topics_exist
from .web import app as web_app

logger = logging.getLogger(__name__)

class ConsumerManager:
    """
    Manages the lifecycle of Kafka consumers for the time series generator.
    """
    def __init__(self):
        self.consumers = []
        self.tasks = []
        self._shutdown_event = asyncio.Event()

        dlq_topic = KAFKA_PERSISTENCE_DLQ_TOPIC
        service_prefix = "TS"
        
        self.consumers.append(
            PositionTimeseriesConsumer(
                bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
                topic=KAFKA_DAILY_POSITION_SNAPSHOT_PERSISTED_TOPIC,
                group_id="timeseries_generator_group_positions",
                dlq_topic=dlq_topic,
                service_prefix=service_prefix
            )
        )

        self.consumers.append(
            PortfolioTimeseriesConsumer(
                bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
                topic=KAFKA_POSITION_TIMESERIES_GENERATED_TOPIC,
                group_id="timeseries_generator_group_portfolios",
                dlq_topic=dlq_topic,
                service_prefix=service_prefix
            )
        )

        logger.info(f"ConsumerManager initialized with {len(self.consumers)} consumer(s).")

    def _signal_handler(self, signum, frame):
        logger.info(f"Received shutdown signal: {signal.Signals(signum).name}. Initiating graceful shutdown...")
        self._shutdown_event.set()

    async def run(self):
        required_topics = [consumer.topic for consumer in self.consumers]
        ensure_topics_exist(required_topics)

        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
        
        uvicorn_config = uvicorn.Config(web_app, host="0.0.0.0", port=8085, log_config=None)
        server = uvicorn.Server(uvicorn_config)

        logger.info("Starting all consumer tasks and the web server...")
        self.tasks = [asyncio.create_task(c.run()) for c in self.consumers]
        self.tasks.append(asyncio.create_task(server.serve()))

        logger.info("ConsumerManager is running. Press Ctrl+C to exit.")
        await self._shutdown_event.wait()

        logger.info("Shutdown event received. Stopping all tasks...")
        for consumer in self.consumers:
            consumer.shutdown()
        server.should_exit = True

        await asyncio.gather(*self.tasks, return_exceptions=True)
        logger.info("All tasks have been successfully shut down.")