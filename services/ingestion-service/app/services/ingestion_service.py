# services/ingestion-service/app/services/ingestion_service.py
from fastapi import Depends
from typing import List
from app.DTOs.transaction_dto import Transaction
from app.DTOs.instrument_dto import Instrument # NEW IMPORT
from portfolio_common.kafka_utils import KafkaProducer, get_kafka_producer
from portfolio_common.config import KAFKA_RAW_TRANSACTIONS_TOPIC, KAFKA_INSTRUMENTS_TOPIC # NEW IMPORT

class IngestionService:
    def __init__(self, kafka_producer: KafkaProducer):
        self._kafka_producer = kafka_producer

    async def publish_transaction(self, transaction: Transaction) -> None:
        """Publishes a single transaction to the raw transactions topic."""
        transaction_payload = transaction.model_dump()
        self._kafka_producer.publish_message(
            topic=KAFKA_RAW_TRANSACTIONS_TOPIC,
            key=transaction.transaction_id,
            value=transaction_payload
        )

    async def publish_transactions(self, transactions: List[Transaction]) -> None:
        """Publishes a list of transactions to the raw transactions topic."""
        for transaction in transactions:
            transaction_payload = transaction.model_dump()
            self._kafka_producer.publish_message(
                topic=KAFKA_RAW_TRANSACTIONS_TOPIC,
                key=transaction.transaction_id,
                value=transaction_payload
            )

    # NEW: Add a method to publish multiple instruments
    async def publish_instruments(self, instruments: List[Instrument]) -> None:
        """Publishes a list of instruments to the instruments topic."""
        for instrument in instruments:
            # Use security_id as the key for partitioning in Kafka
            instrument_payload = instrument.model_dump()
            self._kafka_producer.publish_message(
                topic=KAFKA_INSTRUMENTS_TOPIC,
                key=instrument.security_id,
                value=instrument_payload
            )

def get_ingestion_service(
    kafka_producer: KafkaProducer = Depends(get_kafka_producer)
) -> IngestionService:
    """Dependency injector for the IngestionService."""
    return IngestionService(kafka_producer)