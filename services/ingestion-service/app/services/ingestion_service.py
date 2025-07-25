# services/ingestion-service/app/services/ingestion_service.py
from fastapi import Depends
from typing import List
from app.DTOs.transaction_dto import Transaction
from app.DTOs.instrument_dto import Instrument
from app.DTOs.market_price_dto import MarketPrice
from app.DTOs.fx_rate_dto import FxRate # NEW IMPORT
from portfolio_common.kafka_utils import KafkaProducer, get_kafka_producer
from portfolio_common.config import (
    KAFKA_RAW_TRANSACTIONS_TOPIC, 
    KAFKA_INSTRUMENTS_TOPIC, 
    KAFKA_MARKET_PRICES_TOPIC,
    KAFKA_FX_RATES_TOPIC # NEW IMPORT
)

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

    async def publish_instruments(self, instruments: List[Instrument]) -> None:
        """Publishes a list of instruments to the instruments topic."""
        for instrument in instruments:
            instrument_payload = instrument.model_dump(by_alias=True)
            self._kafka_producer.publish_message(
                topic=KAFKA_INSTRUMENTS_TOPIC,
                key=instrument.security_id,
                value=instrument_payload
            )

    async def publish_market_prices(self, market_prices: List[MarketPrice]) -> None:
        """Publishes a list of market prices to the market prices topic."""
        for price in market_prices:
            price_payload = price.model_dump(by_alias=True)
            self._kafka_producer.publish_message(
                topic=KAFKA_MARKET_PRICES_TOPIC,
                key=price.security_id,
                value=price_payload
            )

    # NEW: Add a method to publish multiple FX rates
    async def publish_fx_rates(self, fx_rates: List[FxRate]) -> None:
        """Publishes a list of FX rates to the fx_rates topic."""
        for rate in fx_rates:
            key = f"{rate.from_currency}-{rate.to_currency}"
            rate_payload = rate.model_dump(by_alias=True)
            self._kafka_producer.publish_message(
                topic=KAFKA_FX_RATES_TOPIC,
                key=key,
                value=rate_payload
            )

def get_ingestion_service(
    kafka_producer: KafkaProducer = Depends(get_kafka_producer)
) -> IngestionService:
    """Dependency injector for the IngestionService."""
    return IngestionService(kafka_producer)