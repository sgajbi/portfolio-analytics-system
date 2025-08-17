# src/services/calculators/performance_calculator_service/app/consumer_manager.py
import logging
import signal
import asyncio
import uvicorn

from portfolio_common.config import (
    KAFKA_BOOTSTRAP_SERVERS,
    KAFKA_PORTFOLIO_TIMESERIES_GENERATED_TOPIC,
    KAFKA_PERSISTENCE_DLQ_TOPIC
)
from portfolio_common.kafka_utils import get_kafka_producer
from portfolio_common.outbox_dispatcher import OutboxDispatcher
from portfolio_common.kafka_admin import ensure_topics_exist

from .consumers.performance_consumer import PerformanceCalculatorConsumer
from .web import app as web_app

logger = logging.getLogger(__name__)

class ConsumerManager:
    def __init__(self):
        self.consumers = []
        self.tasks = []
        self._shutdown_event = asyncio.Event()

        self.consumers.append(
            PerformanceCalculatorConsumer(
                bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
                topic=KAFKA_PORTFOLIO_TIMESERIES_GENERATED_TOPIC,
                group_id="performance_calculator_group",
                dlq_topic=KAFKA_PERSISTENCE_DLQ_TOPIC,
                service_prefix="PERF"
            )
        )

        kafka_producer = get_kafka_producer()
        self.dispatcher = OutboxDispatcher(kafka_producer=kafka_producer)
        logger.info("ConsumerManager initialized with 1 consumer and 1 dispatcher.")

    def _signal_handler(self, signum, frame):
        logger.info(f"Received shutdown signal: {signal.Signals(signum).name}.")
        self._shutdown_event.set()

    async def run(self):
        required_topics = [consumer.topic for consumer in self.consumers]
        ensure_topics_exist(required_topics)

        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

        uvicorn_config = uvicorn.Config(web_app, host="0.0.0.0", port=8086, log_config=None)
        server = uvicorn.Server(uvicorn_config)

        self.tasks = [asyncio.create_task(c.run()) for c in self.consumers]
        self.tasks.append(asyncio.create_task(self.dispatcher.run()))
        self.tasks.append(asyncio.create_task(server.serve()))

        await self._shutdown_event.wait()

        logger.info("Shutting down...")
        for consumer in self.consumers:
            consumer.shutdown()
        self.dispatcher.stop()
        server.should_exit = True
        await asyncio.gather(*self.tasks, return_exceptions=True)
        logger.info("Shutdown complete.")