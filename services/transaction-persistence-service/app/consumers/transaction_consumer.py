# services/transaction-persistence-service/app/consumers/transaction_consumer.py

import json
import logging
from confluent_kafka import Consumer, KafkaException, Message
from common.config import KAFKA_BOOTSTRAP_SERVERS, KAFKA_RAW_TRANSACTIONS_TOPIC, KAFKA_RAW_TRANSACTIONS_COMPLETED_TOPIC
from common.db import get_db_session
from common.kafka_utils import get_kafka_producer
from app.models.transaction_event import TransactionEvent
from app.repositories.transaction_db_repo import TransactionDBRepository
from pydantic import ValidationError
from tenacity import retry, stop_after_attempt, wait_fixed, before_log

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class TransactionConsumer:
    def __init__(self, bootstrap_servers: str = KAFKA_BOOTSTRAP_SERVERS,
                 topic: str = KAFKA_RAW_TRANSACTIONS_TOPIC,
                 group_id: str = "transaction_persistence_group"):
        self.topic = topic
        self.consumer_config = {
            'bootstrap.servers': bootstrap_servers,
            'group.id': group_id,
            'auto.offset.reset': 'earliest',
            'enable.auto.commit': False,
            'session.timeout.ms': 10000,
        }
        self.consumer = None
        self.producer = get_kafka_producer()

    @retry(stop=stop_after_attempt(10), wait=wait_fixed(5), before=before_log(logger, logging.INFO))
    def _initialize_consumer(self):
        if self.consumer:
            self.consumer.close()
        self.consumer = Consumer(self.consumer_config)
        self.consumer.subscribe([self.topic])
        logger.info(f"Kafka consumer initialized and subscribed to topic '{self.topic}'")

    def start_consuming(self):
        try:
            self._initialize_consumer()
        except Exception as e:
            logger.critical(f"Failed to initialize Kafka consumer: {e}")
            return

        logger.info(f"Starting to consume messages from topic '{self.topic}'...")
        try:
            while True:
                msg = self.consumer.poll(timeout=1.0)
                if msg is None: continue
                if msg.error():
                    if msg.error().fatal():
                        logger.error(f"Fatal consumer error: {msg.error()}")
                        break
                    else:
                        logger.warning(f"Consumer error: {msg.error()}. Retrying...")
                        continue
                try:
                    self._process_message(msg)
                    self.consumer.commit(message=msg, asynchronous=False)
                except Exception as e:
                    logger.error(f"Error processing message offset {msg.offset()}: {e}", exc_info=True)
        finally:
            self.consumer.close()

    def _process_message(self, msg: Message):
        key = msg.key().decode('utf-8') if msg.key() else "NoKey"
        value = msg.value().decode('utf-8')
        logger.info(f"Received message from topic '{msg.topic()}' with key '{key}'")

        try:
            transaction_data = json.loads(value)
            # This handles the double-encoding from the (now fixed) ingestion service
            if isinstance(transaction_data, str):
                logger.warning("Detected double-encoded JSON, decoding again.")
                transaction_data = json.loads(transaction_data)

            transaction_event = TransactionEvent(**transaction_data)
            logger.info(f"Validated transaction event: {transaction_event.transaction_id}")

            with next(get_db_session()) as db:
                repo = TransactionDBRepository(db)
                repo.create_or_update_transaction(transaction_event)
                
                # --- THIS IS THE FIX ---
                # Use model_dump() to get a dictionary for the next message
                completed_event_payload = transaction_event.model_dump()

                self.producer.publish_message(
                    topic=KAFKA_RAW_TRANSACTIONS_COMPLETED_TOPIC,
                    key=transaction_event.transaction_id,
                    value=completed_event_payload # Pass the dictionary
                )
                logger.info(f"Published completion event for '{transaction_event.transaction_id}'")
        except (json.JSONDecodeError, ValidationError) as e:
            logger.error(f"Message validation failed for key '{key}': {e}")
        except Exception as e:
            logger.error(f"Unhandled error for key '{key}': {e}", exc_info=True)
            raise