# libs/portfolio-common/portfolio_common/kafka_consumer.py
import logging
import json
import traceback
import asyncio
from datetime import datetime, timezone
from abc import ABC, abstractmethod
from typing import Optional
from confluent_kafka import Consumer, KafkaException, Message

from .kafka_utils import get_kafka_producer
from tenacity import retry, stop_after_attempt, wait_fixed, before_log

logger = logging.getLogger(__name__)

class BaseConsumer(ABC):
    """
    An abstract base class for creating robust, retrying Kafka consumers
    with Dead-Letter Queue (DLQ) support.
    """
    def __init__(self, bootstrap_servers: str, topic: str, group_id: str, dlq_topic: Optional[str] = None):
        self.topic = topic
        self.dlq_topic = dlq_topic
        self._consumer = None
        self._producer = None
        self._consumer_config = {
            'bootstrap.servers': bootstrap_servers,
            'group.id': group_id,
            'auto.offset.reset': 'earliest',
            'enable.auto.commit': False,
            'session.timeout.ms': 10000,
            'heartbeat.interval.ms': 3000
        }
        self._running = True

        if self.dlq_topic:
            self._producer = get_kafka_producer()
            logger.info(f"DLQ enabled for consumer of topic '{self.topic}'. Failing messages will be sent to '{self.dlq_topic}'.")

    @retry(stop=stop_after_attempt(5), wait=wait_fixed(5), before=before_log(logger, logging.INFO))
    def _initialize_consumer(self):
        """Initializes and subscribes the Kafka consumer with retries."""
        logger.info(f"Initializing consumer for topic '{self.topic}' with group '{self._consumer_config['group.id']}'...")
        self._consumer = Consumer(self._consumer_config)
        self._consumer.subscribe([self.topic])
        logger.info(f"Consumer successfully subscribed to topic '{self.topic}'.")

    async def _send_to_dlq(self, msg: Message, error: Exception):
        """
        Sends a message that failed processing to the Dead-Letter Queue.
        """
        if not self._producer or not self.dlq_topic:
            return

        try:
            dlq_payload = {
                "original_topic": msg.topic(),
                "original_key": msg.key().decode('utf-8') if msg.key() else None,
                "original_value": msg.value().decode('utf-8'),
                "error_timestamp": datetime.now(timezone.utc).isoformat(),
                "error_reason": str(error),
                "error_traceback": traceback.format_exc()
            }
            self._producer.publish_message(
                topic=self.dlq_topic,
                key=msg.key().decode('utf-8') if msg.key() else "NoKey",
                value=dlq_payload
            )
            self._producer.flush(timeout=5)
            logger.warning(f"Message with key '{dlq_payload['original_key']}' sent to DLQ '{self.dlq_topic}'.")
        except Exception as e:
            logger.error(f"FATAL: Could not send message to DLQ. Error: {e}", exc_info=True)

    @abstractmethod
    async def process_message(self, msg: Message):
        """
        Abstract method to be implemented by subclasses.
        This contains the business logic for processing a single Kafka message.
        """
        pass

    async def run(self):
        """
        The main consumer loop.
        Polls for messages, processes them, and commits offsets.
        """
        self._initialize_consumer()
        loop = asyncio.get_running_loop()
        logger.info(f"Starting to consume messages from topic '{self.topic}'...")
        while self._running:
            # --- THIS IS THE CRITICAL FIX ---
            # Run the blocking poll() in a thread to not block the event loop.
            msg = await loop.run_in_executor(
                None, self._consumer.poll, 1.0
            )

            if msg is None:
                continue
            if msg.error():
                if msg.error().fatal():
                    logger.error(f"Fatal consumer error on topic {self.topic}: {msg.error()}. Shutting down.", exc_info=True)
                    break
                else:
                    logger.warning(f"Non-fatal consumer error on topic {self.topic}: {msg.error()}.")
                    continue
            
            await self.process_message(msg)
        
            self._consumer.commit(message=msg, asynchronous=False)
        
        self.shutdown()

    def shutdown(self):
        """Gracefully shuts down the consumer."""
        logger.info(f"Shutting down consumer for topic '{self.topic}'...")
        self._running = False
        if self._consumer:
            self._consumer.close()
        if self._producer:
            self._producer.flush()
        logger.info(f"Consumer for topic '{self.topic}' has been closed.")