import logging
import asyncio
import contextlib

from .consumer_manager import ConsumerManager
from portfolio_common.logging_utils import setup_logging
from portfolio_common.kafka_utils import get_kafka_producer
from portfolio_common.outbox_dispatcher import OutboxDispatcher
from prometheus_fastapi_instrumentator import Instrumentator

from .core.aggregation_scheduler import AggregationScheduler
from .web import app as web_app


setup_logging()
logger = logging.getLogger(__name__)


async def main():
    """
    Run the Time Series Generator service components:
      - ConsumerManager (Kafka consumers)
      - OutboxDispatcher (publishes outbox events)
      - AggregationScheduler (emits PortfolioAggregationRequiredEvent jobs)
    """
    logger.info("Time Series Generator Service starting up...")

    Instrumentator().instrument(web_app).expose(web_app)
    logger.info("Prometheus metrics exposed at /metrics")

    manager = ConsumerManager()

    producer = get_kafka_producer()
    dispatcher = OutboxDispatcher(producer, poll_interval=2, batch_size=100)
    dispatcher_task = asyncio.create_task(dispatcher.run(), name="outbox-dispatcher")

    # NOTE: If the scheduler needs config (e.g., window, frequency), adjust below.
    scheduler = AggregationScheduler()
    scheduler_task = asyncio.create_task(scheduler.run(), name="aggregation-scheduler")

    try:
        await manager.run()
    except Exception as e:
        logger.critical("Time Series Generator Service encountered a critical error", exc_info=True)
        raise
    finally:
        dispatcher.stop()
        scheduler.stop() if hasattr(scheduler, "stop") else None

        for task in (dispatcher_task, scheduler_task):
            try:
                await asyncio.wait_for(task, timeout=5)
            except asyncio.TimeoutError:
                task.cancel()
                with contextlib.suppress(Exception):
                    await task

        logger.info("Time Series Generator Service has shut down.")


if __name__ == "__main__":
    asyncio.run(main())