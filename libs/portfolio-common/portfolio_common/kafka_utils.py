# common/kafka_utils.py
import logging
from confluent_kafka import Producer, KafkaException
from .config import KAFKA_BOOTSTRAP_SERVERS # <-- CORRECTED IMPORT
import json

logger = logging.getLogger(__name__)

class KafkaProducer:
    def __init__(self, bootstrap_servers: str = KAFKA_BOOTSTRAP_SERVERS):
        self.producer = None
        self.bootstrap_servers = bootstrap_servers
        self._initialize_producer()

    def _initialize_producer(self):
        try:
            self.producer = Producer({
                'bootstrap.servers': self.bootstrap_servers,
                'client.id': 'portfolio-analytics-producer',
                'acks': 'all',
                'retries': 3,
                'linger.ms': 5,
            })
            logger.info(f"Kafka producer initialized for brokers: {self.bootstrap_servers}")
        except KafkaException as e:
            logger.error(f"Failed to initialize Kafka producer: {e}")
            self.producer = None
            raise

    def publish_message(self, topic: str, key: str, value: dict):
        if not self.producer:
            logger.error(f"Kafka producer not initialized. Cannot publish message to topic {topic}.")
            raise RuntimeError("Kafka producer is not initialized.")

        try:
            # Add `default=str` to handle non-serializable types like date/datetime
            json_value = json.dumps(value, default=str)

            def delivery_report(err, msg):
                if err is not None:
                    logger.error(f"Message delivery failed for topic {msg.topic()} key {msg.key()}: {err}")
                else:
                    logger.info(f"Message delivered to topic '{msg.topic()}' "
                                f"[{msg.partition()}] @ offset {msg.offset()} "
                                f"with key '{msg.key().decode('utf-8')}'")

            self.producer.produce(
                topic,
                key=key.encode('utf-8'),
                value=json_value.encode('utf-8'),
                callback=delivery_report
            )
            self.producer.poll(0)
        except Exception as e:
            logger.error(f"An unexpected error occurred during message production: {e}", exc_info=True)
            raise

    def flush(self, timeout: int = 10):
        if self.producer:
            return self.producer.flush(timeout)
        return 0

_kafka_producer_instance = None

def get_kafka_producer() -> KafkaProducer:
    global _kafka_producer_instance
    if _kafka_producer_instance is None:
        _kafka_producer_instance = KafkaProducer()
    return _kafka_producer_instance