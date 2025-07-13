# common/kafka_utils.py
import logging
from confluent_kafka import Producer, KafkaException
from common.config import KAFKA_BOOTSTRAP_SERVERS
import json

logger = logging.getLogger(__name__)

class KafkaProducer:
    def __init__(self, bootstrap_servers: str = KAFKA_BOOTSTRAP_SERVERS):
        """
        Initializes the Kafka Producer.
        :param bootstrap_servers: Kafka broker addresses.
        """
        self.producer = None
        self.bootstrap_servers = bootstrap_servers
        self._initialize_producer()

    def _initialize_producer(self):
        """Initializes the Confluent Kafka Producer."""
        try:
            self.producer = Producer({
                'bootstrap.servers': self.bootstrap_servers,
                'client.id': 'portfolio-analytics-producer', # Unique client ID
                'acks': 'all', # Ensure all in-sync replicas have received the message
                'retries': 3,  # Number of retries for failed message delivery
                'linger.ms': 5, # Batch messages for 5ms before sending
            })
            logger.info(f"Kafka producer initialized for brokers: {self.bootstrap_servers}")
        except KafkaException as e:
            logger.error(f"Failed to initialize Kafka producer: {e}")
            self.producer = None # Ensure producer is None if initialization fails
            raise # Re-raise to indicate a critical setup failure

    def publish_message(self, topic: str, key: str, value: dict):
        """
        Publishes a message to a Kafka topic.
        :param topic: The Kafka topic to publish to.
        :param key: The message key (used for partitioning).
        :param value: The message value (dictionary, will be JSON serialized).
        """
        if not self.producer:
            logger.error(f"Kafka producer not initialized. Cannot publish message to topic {topic}.")
            raise RuntimeError("Kafka producer is not initialized.")

        try:
            # Convert dictionary value to JSON string
            json_value = json.dumps(value)
            
            def delivery_report(err, msg):
                """Callback function for successful/failed message delivery."""
                if err is not None:
                    logger.error(f"Message delivery failed for topic {msg.topic()} key {msg.key()}: {err}")
                else:
                    logger.info(f"Message delivered to topic '{msg.topic()}' "
                                f"[{msg.partition()}] @ offset {msg.offset()} "
                                f"with key '{msg.key().decode('utf-8')}'")

            # Produce message asynchronously
            self.producer.produce(
                topic,
                key=key.encode('utf-8'),
                value=json_value.encode('utf-8'),
                callback=delivery_report
            )
            # Poll for any delivered messages or events
            self.producer.poll(0) # Non-blocking poll
        except KafkaException as e:
            logger.error(f"Failed to produce message to topic {topic} with key {key}: {e}")
            raise # Re-raise for calling service to handle
        except Exception as e:
            logger.error(f"An unexpected error occurred during message production: {e}")
            raise

    def flush(self, timeout: int = 10):
        """
        Flushes any outstanding messages in the producer's queue.
        Should be called before application exit to ensure all messages are sent.
        :param timeout: Maximum time in seconds to wait for message delivery.
        :return: The number of messages still in the queue.
        """
        if self.producer:
            remaining_messages = self.producer.flush(timeout)
            if remaining_messages > 0:
                logger.warning(f"{remaining_messages} messages still in queue after flush timeout.")
            return remaining_messages
        return 0

# Global producer instance (optional, for simple single-producer needs)
# For more complex scenarios, especially in FastAPI, you might prefer dependency injection.
# However, for a shared utility, a single instance can be practical if properly managed.
_kafka_producer_instance = None

def get_kafka_producer() -> KafkaProducer:
    """
    Provides a singleton instance of the KafkaProducer.
    """
    global _kafka_producer_instance
    if _kafka_producer_instance is None:
        _kafka_producer_instance = KafkaProducer()
    return _kafka_producer_instance