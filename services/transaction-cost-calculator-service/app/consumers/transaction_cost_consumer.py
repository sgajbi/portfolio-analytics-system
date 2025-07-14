import json
import logging
from confluent_kafka import Consumer, KafkaException, Message
from common.config import KAFKA_BOOTSTRAP_SERVERS
from common.events import (
    TransactionEvent,
    TransactionCostCalculatedEvent,
    KAFKA_RAW_TRANSACTIONS_COMPLETED_TOPIC,
    KAFKA_CALCULATED_TRANSACTIONS_TOPIC
)
from app.repositories.transaction_cost_repo import TransactionCostRepository
from common.kafka_utils import KafkaProducer # Use the KafkaProducer class

logger = logging.getLogger(__name__)

class TransactionCostConsumer:
    def __init__(self, bootstrap_servers: str, topic: str, group_id: str = "transaction_cost_calculator_group"):
        self.topic = topic
        self.consumer_config = {
            'bootstrap.servers': bootstrap_servers,
            'group.id': group_id,
            'auto.offset.reset': 'earliest',
            'enable.auto.commit': False,
            'session.timeout.ms': 10000,
        }
        self.consumer = None
        self.cost_repository = TransactionCostRepository()
        self.producer = KafkaProducer(bootstrap_servers) # Initialize KafkaProducer

    def _initialize_consumer(self):
        try:
            self.consumer = Consumer(self.consumer_config)
            self.consumer.subscribe([self.topic])
            logger.info(f"Kafka consumer initialized for topic '{self.topic}' on brokers: {self.consumer_config['bootstrap.servers']}")
        except KafkaException as e:
            logger.error(f"Failed to initialize Kafka consumer: {e}")
            self.consumer = None
            raise

    def start_consuming(self):
        if not self.consumer:
            self._initialize_consumer()
            if not self.consumer:
                logger.error("Consumer is not initialized. Cannot start consuming.")
                return

        logger.info(f"Starting to consume messages from topic '{self.topic}'...")
        running = True
        try:
            while running:
                msg = self.consumer.poll(timeout=1.0)
                if msg is None:
                    continue
                if msg.error():
                    if msg.error().is_fatal():
                        logger.error(f"Fatal consumer error: {msg.error()}")
                        running = False
                    else:
                        logger.error(f"Kafka consumer error: {msg.error()}")
                    continue

                try:
                    self._process_message(msg)
                    self.consumer.commit(message=msg, asynchronous=False)
                    logger.info(f"Committed offset {msg.offset()} for message in topic '{msg.topic()}' partition {msg.partition()}")
                except Exception as e:
                    logger.error(f"Error processing message from topic '{msg.topic()}' offset {msg.offset()}: {e}", exc_info=True)

        except KeyboardInterrupt:
            logger.info("Consumer stopped by user interrupt.")
        finally:
            if self.consumer:
                logger.info("Closing Kafka consumer.")
                self.consumer.close()
            self.producer.flush() # Ensure all produced messages are sent

    def _process_message(self, msg: Message):
        key = msg.key().decode('utf-8') if msg.key() else "NoKey"
        value = msg.value().decode('utf-8')

        logger.info(f"Received message from topic '{msg.topic()}' "
                    f"[{msg.partition()}] @ offset {msg.offset()} "
                    f"with key '{key}'")

        try:
            # 1. Parse the incoming message as a TransactionEvent
            transaction_data = json.loads(value)
            transaction_event = TransactionEvent(**transaction_data)
            logger.info(f"Transaction Cost Calculator: Received transaction {transaction_event.transaction_id} for processing.")

            # 2. Calculate Transaction Cost (simple example: 0.1% of transaction value + trade fee)
            transaction_value = transaction_event.quantity * transaction_event.price
            brokerage_fee_percentage = 0.001 # 0.1%
            calculated_cost = (transaction_value * brokerage_fee_percentage) + transaction_event.trade_fee
            cost_currency = transaction_event.currency # Assume cost is in transaction currency

            logger.info(f"Calculated cost for TRN {transaction_event.transaction_id}: {calculated_cost:.4f} {cost_currency}")

            # 3. Persist the calculated cost
            persisted_cost = self.cost_repository.create_transaction_cost(
                transaction_id=transaction_event.transaction_id,
                portfolio_id=transaction_event.portfolio_id,
                instrument_id=transaction_event.instrument_id,
                transaction_date=transaction_event.transaction_date,
                cost_amount=calculated_cost,
                cost_currency=cost_currency
            )

            if persisted_cost:
                logger.info(f"Transaction cost for '{transaction_event.transaction_id}' persisted successfully.")

                # 4. Publish an event that cost calculation is complete
                cost_completion_event = TransactionCostCalculatedEvent(
                    transaction_id=transaction_event.transaction_id,
                    portfolio_id=transaction_event.portfolio_id,
                    instrument_id=transaction_event.instrument_id,
                    transaction_date=transaction_event.transaction_date,
                    cost_amount=calculated_cost,
                    cost_currency=cost_currency
                )
                self.producer.publish_message(
                    KAFKA_CALCULATED_TRANSACTIONS_TOPIC,
                    key=transaction_event.transaction_id,
                    value=cost_completion_event.model_dump()
                )
                logger.info(f"Published transaction cost completion event for '{transaction_event.transaction_id}' to topic '{KAFKA_CALCULATED_TRANSACTIONS_TOPIC}'.")
            else:
                logger.warning(f"Failed to persist transaction cost for '{transaction_event.transaction_id}'.")


        except json.JSONDecodeError:
            logger.error(f"Could not decode JSON from message value: {value}")
        except Exception as e:
            logger.error(f"Error processing message for key '{key}': {e}", exc_info=True)