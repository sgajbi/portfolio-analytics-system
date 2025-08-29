# src/libs/portfolio-common/portfolio_common/kafka_consumer.py
import logging
import json
import traceback
import asyncio
import functools
import time
import inspect
from datetime import datetime, timezone
from abc import ABC, abstractmethod
from typing import Optional, Dict
from confluent_kafka import Consumer, KafkaException, Message

from .kafka_utils import get_kafka_producer
from .logging_utils import correlation_id_var, generate_correlation_id
from .exceptions import RetryableConsumerError

logger = logging.getLogger(__name__)


class BaseConsumer(ABC):
    """
    An abstract base class for creating robust, retrying Kafka consumers
    with Dead-Letter Queue (DLQ) support and Prometheus metrics.
    """
    def __init__(
        self,
        bootstrap_servers: str,
        topic: str,
        group_id: str,
        dlq_topic: Optional[str] = None,
        service_prefix: str = "SVC",
        metrics: Optional[Dict] = None
    ):
        self.topic = topic
        self.dlq_topic = dlq_topic
        self.service_prefix = service_prefix
        self._metrics = metrics
        self._consumer = None
        self._producer = None
        self._consumer_config = {
            'bootstrap.servers': bootstrap_servers,
            'group.id': group_id,
            'auto.offset.reset': 'earliest',
            'enable.auto.commit': False,
            'session.timeout.ms': 30000,
            'heartbeat.interval.ms': 3000
        }
        self._running = True

        if self.dlq_topic:
            self._producer = get_kafka_producer()
            logger.info(f"DLQ enabled for consumer of topic '{self.topic}'. Failing messages will be sent to '{self.dlq_topic}'.")

    def _initialize_consumer(self):
        """Initializes and subscribes the Kafka consumer."""
        logger.info(f"Initializing consumer for topic '{self.topic}' with group '{self._consumer_config['group.id']}'...")
        self._consumer = Consumer(self._consumer_config)
        self._consumer.subscribe([self.topic])
        logger.info(f"Consumer successfully subscribed to topic '{self.topic}'.")

    async def _send_to_dlq_async(self, msg: Message, error: Exception):
        """
        Sends a message that failed processing to the Dead-Letter Queue.
        """
        if self._metrics:
            self._metrics["dlqd"].labels(
                topic=self.topic, 
                consumer_group=self._consumer_config['group.id']
            ).inc()

        if not self._producer or not self.dlq_topic:
            return

        try:
            correlation_id = correlation_id_var.get()
            
            dlq_payload = {
                "correlation_id": correlation_id,
                "original_topic": msg.topic(),
                "original_key": msg.key().decode('utf-8') if msg.key() else None,
                "original_value": msg.value().decode('utf-8'),
                "error_timestamp": datetime.now(timezone.utc).isoformat(),
                "error_reason": str(error),
                "error_traceback": traceback.format_exc()
            }
            
            dlq_headers = msg.headers() or []
            dlq_headers.append(('correlation_id', (correlation_id or "").encode('utf-8')))

            self._producer.publish_message(
                topic=self.dlq_topic,
                key=msg.key().decode('utf-8') if msg.key() else "NoKey",
                value=dlq_payload,
                headers=dlq_headers
            )
            self._producer.flush(timeout=5)
            logger.warning(f"Message with key '{dlq_payload['original_key']}' sent to DLQ '{self.dlq_topic}'.")
        except Exception as e:
            logger.error(f"FATAL: Could not send message to DLQ. Error: {e}", exc_info=True)

    @abstractmethod
    def process_message(self, msg: Message):
        """
        Abstract method to be implemented by subclasses. Can be sync or async.
        """
        pass

    async def run(self):
        """
        The main consumer loop. Polls for messages, processes them, handles errors,
        and commits offsets.
        """
        self._initialize_consumer()
        loop = asyncio.get_running_loop()
        logger.info(f"Starting to consume messages from topic '{self.topic}'...")
        while self._running:
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
            
            token = None
            start_time = time.monotonic()
            processed_successfully = False
            try:
                corr_id = None
                if msg.headers():
                    for key, value in msg.headers():
                        if key == 'correlation_id':
                            corr_id = value.decode('utf-8') if value else None
                            break
                
                if not corr_id:
                    corr_id = generate_correlation_id(self.service_prefix)
                    logger.warning(f"No correlation ID in message from topic '{msg.topic()}'. Generated new ID: {corr_id}")

                token = correlation_id_var.set(corr_id)
                
                if inspect.iscoroutinefunction(self.process_message):
                    await self.process_message(msg)
                else:
                    await loop.run_in_executor(
                        None,
                        functools.partial(self.process_message, msg)
                    )
                
                self._consumer.commit(message=msg, asynchronous=False)
                processed_successfully = True

            except RetryableConsumerError as e:
                # For transient errors, we log and do NOT commit, allowing Kafka to redeliver.
                logger.warning(f"Retryable error occurred: {e}. Offset will not be committed.", exc_info=False)
            
            except Exception as e:
                # For terminal errors (poison pills), we send to DLQ and then commit.
                logger.error(f"Terminal error processing message for topic {self.topic}: {e}", exc_info=True)
                await self._send_to_dlq_async(msg, e)
                self._consumer.commit(message=msg, asynchronous=False)

            finally:
                duration = time.monotonic() - start_time
                if self._metrics:
                    labels = {
                        "topic": self.topic, 
                        "consumer_group": self._consumer_config['group.id']
                    }
                    self._metrics["latency"].labels(**labels).observe(duration)
                    if processed_successfully:
                        self._metrics["processed"].labels(**labels).inc()

                if token:
                    correlation_id_var.reset(token)
        
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