# libs/portfolio-common/portfolio_common/kafka_consumer.py
import logging
import asyncio
from abc import ABC, abstractmethod
from confluent_kafka import Consumer, KafkaException, Message
from tenacity import retry, stop_after_attempt, wait_fixed, before_log

logger = logging.getLogger(__name__)

class BaseConsumer(ABC):
    """
    An abstract base class for creating robust, retrying Kafka consumers.

    It handles the common boilerplate of connecting, subscribing, polling,
    and committing, while delegating the message processing logic to subclasses.
    """
    def __init__(self, bootstrap_servers: str, topic: str, group_id: str):
        self.topic = topic
        self._consumer = None
        self._consumer_config = {
            'bootstrap.servers': bootstrap_servers,
            'group.id': group_id,
            'auto.offset.reset': 'earliest',
            'enable.auto.commit': False,
            'session.timeout.ms': 10000,
            'heartbeat.interval.ms': 3000
        }
        self._running = True

    @retry(stop=stop_after_attempt(5), wait=wait_fixed(5), before=before_log(logger, logging.INFO))
    def _initialize_consumer(self):
        """Initializes and subscribes the Kafka consumer with retries."""
        logger.info(f"Initializing consumer for topic '{self.topic}' with group '{self._consumer_config['group.id']}'...")
        self._consumer = Consumer(self._consumer_config)
        self._consumer.subscribe([self.topic])
        logger.info(f"Consumer successfully subscribed to topic '{self.topic}'.")

    @abstractmethod
    async def process_message(self, msg: Message):
        """
        Abstract method to be implemented by subclasses.
        This contains the business logic for processing a single Kafka message.
        """
        pass

    async def run(self):
        """
        The main consumer loop. Polls for messages, processes them, and commits offsets.
        """
        self._initialize_consumer()
        logger.info(f"Starting to consume messages from topic '{self.topic}'...")
        while self._running:
            try:
                msg = self._consumer.poll(timeout=1.0)

                if msg is None:
                    await asyncio.sleep(0.1) # Yield control to the event loop
                    continue
                if msg.error():
                    # Handle fatal errors
                    if msg.error().fatal():
                        logger.error(f"Fatal consumer error on topic {self.topic}: {msg.error()}. Shutting down consumer task.")
                        break
                    else:
                        logger.warning(f"Non-fatal consumer error on topic {self.topic}: {msg.error()}.")
                        continue

                # Process the message using the subclass's implementation
                await self.process_message(msg)
                self._consumer.commit(message=msg, asynchronous=False)

            except Exception as e:
                logger.error(f"Unexpected error in consumer loop for topic {self.topic}: {e}", exc_info=True)
                # Avoid a fast-spinning loop on unexpected errors
                await asyncio.sleep(5)
        
        self.shutdown()

    def shutdown(self):
        """Gracefully shuts down the consumer."""
        logger.info(f"Shutting down consumer for topic '{self.topic}'...")
        self._running = False
        if self._consumer:
            self._consumer.close()
        logger.info(f"Consumer for topic '{self.topic}' has been closed.")