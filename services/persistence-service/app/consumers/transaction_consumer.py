# services/persistence-service/app/consumers/transaction_consumer.py
import logging
from confluent_kafka import Message
from portfolio_common.kafka_consumer import BaseConsumer

logger = logging.getLogger(__name__)

class TransactionPersistenceConsumer(BaseConsumer):
    """
    A concrete consumer for persisting raw transaction events.
    """
    async def process_message(self, msg: Message):
        """
        Processes a single raw transaction message from Kafka.
        For now, it only logs the message content.
        """
        key = msg.key().decode('utf-8') if msg.key() else "NoKey"
        value = msg.value().decode('utf-8')
        logger.info(
            f"Received message from topic '{msg.topic()}' with key '{key}'. "
            f"Value: {value[:300]}..." # Log a snippet of the value
        )