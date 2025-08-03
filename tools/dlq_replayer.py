# tools/dlq_replayer.py
import argparse
import asyncio
import json
import logging
import sys
import os
from typing import Optional

# Ensure the script can find the portfolio-common library
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from confluent_kafka import Message
from portfolio_common.kafka_consumer import BaseConsumer
from portfolio_common.kafka_utils import get_kafka_producer, KafkaProducer
from portfolio_common.logging_utils import setup_logging

# Setup basic logging for the tool
setup_logging()
logger = logging.getLogger(__name__)

class DLQReplayConsumer(BaseConsumer):
    """
    A consumer designed to read from a DLQ, extract the original message,
    and attempt to republish it to its original topic.
    """
    def __init__(self, limit: Optional[int] = None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._producer: KafkaProducer = get_kafka_producer()
        self._limit = limit
        self._processed_count = 0

    def process_message(self, msg: Message, loop: asyncio.AbstractEventLoop):
        """
        Processes a single message from the DLQ.
        """
        try:
            dlq_data = json.loads(msg.value().decode('utf-8'))
            
            # Extract original message details from the DLQ wrapper
            original_topic = dlq_data.get("original_topic")
            original_key = dlq_data.get("original_key")
            original_value_str = dlq_data.get("original_value")
            original_value = json.loads(original_value_str) # Re-parse the nested JSON
            correlation_id = dlq_data.get("correlation_id")

            if not all([original_topic, original_key, original_value]):
                logger.error("DLQ message is missing required original message fields. Skipping.", extra={"dlq_key": msg.key()})
                return

            logger.info(
                f"Replaying message from DLQ. Original Key: {original_key}, Original Topic: {original_topic}",
                extra={"correlation_id": correlation_id}
            )

            headers = [('correlation_id', (correlation_id or "").encode('utf-8'))]

            # Republish to the original topic
            self._producer.publish_message(
                topic=original_topic,
                key=original_key,
                value=original_value,
                headers=headers
            )
            self._producer.flush(timeout=5)
            logger.info(f"Successfully replayed message for key '{original_key}'.")

            # Commit the offset in the DLQ so it's not replayed again
            self._consumer.commit(message=msg, asynchronous=False)

        except json.JSONDecodeError:
            logger.error("Failed to parse DLQ message value as JSON. Skipping.", extra={"dlq_key": msg.key()}, exc_info=True)
        except Exception:
            logger.error("An unexpected error occurred during replay. Message will not be committed.", extra={"dlq_key": msg.key()}, exc_info=True)
        finally:
            self._processed_count += 1
            if self._limit and self._processed_count >= self._limit:
                logger.info(f"Reached processing limit of {self._limit}. Shutting down.")
                self.shutdown()

async def main():
    parser = argparse.ArgumentParser(description="Kafka DLQ Replayer Tool")
    parser.add_argument(
        "--dlq-topic",
        required=True,
        help="The Dead Letter Queue topic to consume from."
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="The maximum number of messages to process in one run."
    )
    args = parser.parse_args()

    logger.info(f"Starting DLQ Replayer for topic: {args.dlq_topic} with a limit of {args.limit or 'unlimited'}")

    # Use a unique group_id for each run to ensure it starts from the beginning
    # In a real scenario, you might want a persistent group_id to track progress
    group_id = f"dlq-replayer-{os.getpid()}"

    consumer = DLQReplayConsumer(
        bootstrap_servers=os.getenv("KAFKA_BOOTSTRAP_SERVERS", "kafka:9093"),
        topic=args.dlq_topic,
        group_id=group_id,
        limit=args.limit
    )

    await consumer.run()
    logger.info("DLQ Replayer has finished.")

if __name__ == "__main__":
    asyncio.run(main())