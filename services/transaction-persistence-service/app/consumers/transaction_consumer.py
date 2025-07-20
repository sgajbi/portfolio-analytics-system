# services/transaction-persistence-service/app/consumers/transaction_consumer.py

import json
import logging
from confluent_kafka import Consumer, KafkaException, Message
from common.config import KAFKA_BOOTSTRAP_SERVERS, KAFKA_RAW_TRANSACTIONS_TOPIC, KAFKA_RAW_TRANSACTIONS_COMPLETED_TOPIC
from common.db import get_db_session # Corrected import
from common.kafka_utils import get_kafka_producer
from app.models.transaction_event import TransactionEvent
from app.repositories.transaction_db_repo import TransactionDBRepository
from pydantic import ValidationError

logger = logging.getLogger(__name__)

class TransactionConsumer:
    def __init__(self, bootstrap_servers: str = KAFKA_BOOTSTRAP_SERVERS,
                 topic: str = KAFKA_RAW_TRANSACTIONS_TOPIC,
                 group_id: str = "transaction_persistence_group"):
        """
        Initializes the Kafka Consumer for raw transactions.
        :param bootstrap_servers: Kafka broker addresses.
        :param topic: The Kafka topic to consume from.
        :param group_id: Consumer group ID.
        """
        self.topic = topic
        self.consumer_config = {
            'bootstrap.servers': bootstrap_servers,
            'group.id': group_id,
            'auto.offset.reset': 'earliest', # Start consuming from the beginning if no offset is stored
            'enable.auto.commit': False,     # Manual commit for better control
            'session.timeout.ms': 10000,     # Session timeout for group rebalance
        }
        self.consumer = None
        self.producer = get_kafka_producer() # Initialize Kafka Producer for publishing completion events

    def _initialize_consumer(self):
        """Initializes the Confluent Kafka Consumer."""
        try:
            self.consumer = Consumer(self.consumer_config)
            self.consumer.subscribe([self.topic])
            logger.info(f"Kafka consumer initialized for topic '{self.topic}' on brokers: {self.consumer_config['bootstrap.servers']}")
        except KafkaException as e:
            logger.error(f"Failed to initialize Kafka consumer: {e}")
            self.consumer = None
            raise # Re-raise to indicate a critical setup failure

    def start_consuming(self):
        """Starts the message consumption loop."""
        if not self.consumer:
            self._initialize_consumer()
            if not self.consumer: # Check again if initialization failed
                logger.error("Consumer is not initialized. Cannot start consuming.")
                return

        logger.info(f"Starting to consume messages from topic '{self.topic}'...")
        running = True
        try:
            while running:
                msg = self.consumer.poll(timeout=1.0) # Poll for messages with a timeout
                if msg is None:
                    continue
                if msg.error():
                    # Corrected line below: Use .fatal() instead of .is_fatal()
                    if msg.error().fatal():
                        logger.error(f"Fatal consumer error: {msg.error()}")
                        running = False
                    elif msg.error().code() == -190: # RD_KAFKA_RESP_ERR__PARTITION_EOF
                        # Normal, expected error when no more messages in partition
                        # logger.debug(f"End of partition reached {msg.topic()} [{msg.partition()}] at offset {msg.offset()}")
                        pass
                    else:
                        logger.error(f"Kafka consumer error: {msg.error()}")
                    continue

                try:
                    self._process_message(msg)
                    # Manually commit offset after successful processing
                    self.consumer.commit(message=msg, asynchronous=False)
                    logger.info(f"Committed offset {msg.offset()} for message in topic '{msg.topic()}' partition {msg.partition()}")
                except Exception as e:
                    logger.error(f"Error processing message from topic '{msg.topic()}' offset {msg.offset()}: {e}", exc_info=True)
                    # Depending on policy, you might want to log this message to a dead-letter queue
                    # or skip committing to reprocess it later. For now, we log and continue.

        except KeyboardInterrupt:
            logger.info("Consumer stopped by user interrupt.")
        finally:
            if self.consumer:
                logger.info("Closing Kafka consumer.")
                self.consumer.close()
            # Ensure producer flushes any remaining messages on shutdown
            if self.producer:
                remaining = self.producer.flush(timeout=5)
                if remaining > 0:
                    logger.warning(f"Kafka producer flush timed out with {remaining} messages remaining in queue during shutdown.")
                else:
                    logger.info("Kafka producer flushed successfully during shutdown.")


    def _process_message(self, msg: Message):
        """Processes a single Kafka message."""
        key = msg.key().decode('utf-8') if msg.key() else "NoKey"
        value = msg.value().decode('utf-8')

        logger.info(f"Received message from topic '{msg.topic()}' "
                    f"[{msg.partition()}] @ offset {msg.offset()} "
                    f"with key '{key}'")

        try:
            # 1. Parse and validate message value using Pydantic model
            transaction_data = json.loads(value)

            # CRITICAL FIX: Ensure transaction_data is a dictionary.
            # If the Kafka message value was a JSON string that encoded another JSON string,
            # json.loads might return a string which is itself a JSON string.
            if isinstance(transaction_data, str):
                logger.warning("Detected transaction_data is a string after first JSON decode. Attempting second decode.")
                transaction_data = json.loads(transaction_data) # Attempt to decode again


            transaction_event = TransactionEvent(**transaction_data)
            logger.info(f"Validated transaction event: {transaction_event.transaction_id}")

            # 2. Persist to PostgreSQL using the repository (now idempotent)
            # Get a new DB session for each message processing to avoid stale sessions
            with next(get_db_session()) as db:
                repo = TransactionDBRepository(db)
                # Use the new idempotent method
                db_transaction = repo.create_or_update_transaction(transaction_event)
                # Log a success message for consistency, as the transaction is now 'handled'
                # if not db_transaction.id: # Check if it was newly inserted or existing (depends on repo logic)
                #    logger.info(f"Transaction {transaction_event.transaction_id} found existing in DB, no new insertion.")
                # else:
                #    logger.info(f"Transaction {transaction_event.transaction_id} persisted to PostgreSQL.")

                # 3. Publish raw_transactions_completed event to Kafka
                # This step now executes even if the transaction already existed,
                # as it's considered "completed" (persisted).
                completed_event_value = transaction_event.model_dump_json() # Use the validated event as payload
                self.producer.publish_message(
                    topic=KAFKA_RAW_TRANSACTIONS_COMPLETED_TOPIC,
                    key=transaction_event.transaction_id, # Use transaction_id as key for event
                    value=completed_event_value
                )
                logger.info(f"Published transaction completion event for '{transaction_event.transaction_id}' to topic '{KAFKA_RAW_TRANSACTIONS_COMPLETED_TOPIC}'.")


        except json.JSONDecodeError as e:
            logger.error(f"Failed to decode JSON from message value for key '{key}': {e}. Value: {value[:200]}...")
        except ValidationError as e:
            logger.error(f"Message validation failed for key '{key}': {e}. Value: {value[:200]}...")
        except Exception as e:
            logger.error(f"Unhandled error during message processing for key '{key}': {e}", exc_info=True)