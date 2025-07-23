# services/ingestion-service/app/services/ingestion_service.py
from fastapi import Depends
from app.DTOs.transaction_dto import Transaction
from portfolio_common.kafka_utils import KafkaProducer, get_kafka_producer
from portfolio_common.config import KAFKA_RAW_TRANSACTIONS_TOPIC

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

def get_ingestion_service(
    kafka_producer: KafkaProducer = Depends(get_kafka_producer)
) -> IngestionService:
    """Dependency injector for the IngestionService."""
    return IngestionService(kafka_producer)