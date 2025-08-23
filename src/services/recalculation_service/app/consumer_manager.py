# src/services/recalculation_service/app/consumer_manager.py
import logging
import signal
import asyncio
import uvicorn

from portfolio_common.kafka_admin import ensure_topics_exist
from .web import app as web_app
from .consumers.recalculation_consumer import RecalculationJobConsumer

logger = logging.getLogger(__name__)

class ConsumerManager:
    """
    Manages the lifecycle of the recalculation job consumer and the health probe web server
    for the Recalculation Service.
    """
    def __init__(self):
        self.tasks = []
        self._shutdown_event = asyncio.Event()

        # Instantiate our new polling consumer
        self.recalculation_consumer = RecalculationJobConsumer()

        logger.info("ConsumerManager initialized with 1 recalculation job consumer.")

    def _signal_handler(self, signum, frame):
        logger.info(f"Received shutdown signal: {signal.Signals(signum).name}. Initiating graceful shutdown...")
        self._shutdown_event.set()

    async def run(self):
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

        uvicorn_config = uvicorn.Config(web_app, host="0.0.0.0", port=8086, log_config=None)
        server = uvicorn.Server(uvicorn_config)

        logger.info("Starting recalculation consumer and the web server...")
        
        # Add both the consumer and the web server as managed asyncio tasks
        self.tasks.append(asyncio.create_task(self.recalculation_consumer.run()))
        self.tasks.append(asyncio.create_task(server.serve()))
         
        logger.info("ConsumerManager is running. Press Ctrl+C to exit.")
        await self._shutdown_event.wait()
        
        logger.info("Shutdown event received. Stopping all tasks...")
        
        # Signal the consumer to stop its loop
        self.recalculation_consumer.stop()
       
        server.should_exit = True
        
        await asyncio.gather(*self.tasks, return_exceptions=True)
        logger.info("All tasks have been successfully shut down.")