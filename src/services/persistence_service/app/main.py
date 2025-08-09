# services/persistence_service/app/main.py
import logging
import asyncio

from portfolio_common.logging_utils import setup_logging
from portfolio_common.kafka_utils import get_kafka_producer
from portfolio_common.outbox_dispatcher import OutboxDispatcher
from .consumer_manager import ConsumerManager

setup_logging()
logger = logging.getLogger(__name__)


async def main():
    """
    Initializes and runs the ConsumerManager and the OutboxDispatcher side-by-side.
    """
    logger.info("Persistence Service starting up...")
    manager = ConsumerManager()

    # Start the outbox dispatcher in the background
    producer = get_kafka_producer()
    dispatcher = OutboxDispatcher(producer, poll_interval=2, batch_size=100)
    dispatcher_task = asyncio.create_task(dispatcher.run(), name="outbox-dispatcher")

    try:
        await manager.run()
    except Exception:
        logger.critical("Persistence Service encountered a critical error", exc_info=True)
        raise
    finally:
        # Graceful shutdown of dispatcher
        dispatcher.stop()
        try:
            await asyncio.wait_for(dispatcher_task, timeout=5)
        except asyncio.TimeoutError:
            dispatcher_task.cancel()
            with contextlib.suppress(Exception):
                await dispatcher_task
        logger.info("Persistence Service has shut down.")


if __name__ == "__main__":
    import contextlib  # local import to avoid unused in module context
    asyncio.run(main())
