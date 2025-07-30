# services/ingestion-service/app/services/ingestion_service.py
from fastapi import Depends
from typing import List

from app.DTOs.transaction_dto import Transaction
from app.DTOs.instrument_dto import Instrument
from app.DTOs.market_price_dto import MarketPrice
from app.DTOs.fx_rate_dto import FxRate
from app.DTOs.portfolio_dto import Portfolio
from portfolio_common.kafka_utils import KafkaProducer, get_kafka_producer
from portfolio_common.config import (
    KAFKA_RAW_TRANSACTIONS_TOPIC, 
    KAFKA_INSTRUMENTS_TOPIC, 
    KAFKA_MARKET_PRICES_TOPIC,
    KAFKA_FX_RATES_TOPIC,
    KAFKA_RAW_PORTFOLIOS_TOPIC
)
from ..context import correlation_id_cv # --- Updated Import ---

class IngestionService:
    def __init__(self, kafka_producer: KafkaProducer):
        self._kafka_producer = kafka_producer

    def _get_headers(self):
        """Constructs Kafka headers with the current correlation ID."""
        corr_id = correlation_id_cv.get()
        if corr_id:
            return [('X-Correlation-ID', corr_id.encode('utf-8'))]
        return None

    async def publish_portfolios(self, portfolios: List[Portfolio]) -> None:
        """Publishes a list of portfolios to the raw portfolios topic."""
        headers = self._get_headers()
        for portfolio in portfolios:
            portfolio_payload = portfolio.model_dump(by_alias=True)
            self._kafka_producer.publish_message(
                topic=KAFKA_RAW_PORTFOLIOS_TOPIC,
                key=portfolio.portfolio_id,
                value=portfolio_payload,
                headers=headers
            )

    async def publish_transaction(self, transaction: Transaction) -> None:
        """Publishes a single transaction to the raw transactions topic."""
        headers = self._get_headers()
        transaction_payload = transaction.model_dump()
        self._kafka_producer.publish_message(
            topic=KAFKA_RAW_TRANSACTIONS_TOPIC,
            key=transaction.transaction_id,
            value=transaction_payload,
            headers=headers
        )

    async def publish_transactions(self, transactions: List[Transaction]) -> None:
        """Publishes a list of transactions to the raw transactions topic."""
        headers = self._get_headers()
        for transaction in transactions:
            transaction_payload = transaction.model_dump()
            self._kafka_producer.publish_message(
                topic=KAFKA_RAW_TRANSACTIONS_TOPIC,
                key=transaction.transaction_id,
                value=transaction_payload,
                headers=headers
            )

    async def publish_instruments(self, instruments: List[Instrument]) -> None:
        """Publishes a list of instruments to the instruments topic."""
        headers = self._get_headers()
        for instrument in instruments:
            instrument_payload = instrument.model_dump(by_alias=True)
            self._kafka_producer.publish_message(
                topic=KAFKA_INSTRUMENTS_TOPIC,
                key=instrument.security_id,
                value=instrument_payload,
                headers=headers
            )

    async def publish_market_prices(self, market_prices: List[MarketPrice]) -> None:
        """Publishes a list of market prices to the market prices topic."""
        headers = self._get_headers()
        for price in market_prices:
            price_payload = price.model_dump(by_alias=True)
            self._kafka_producer.publish_message(
                topic=KAFKA_MARKET_PRICES_TOPIC,
                key=price.security_id,
                value=price_payload,
                headers=headers
            )

    async def publish_fx_rates(self, fx_rates: List[FxRate]) -> None:
        """Publishes a list of FX rates to the fx_rates topic."""
        headers = self._get_headers()
        for rate in fx_rates:
            key = f"{rate.from_currency}-{rate.to_currency}"
            rate_payload = rate.model_dump(by_alias=True)
            self._kafka_producer.publish_message(
                topic=KAFKA_FX_RATES_TOPIC,
                key=key,
                value=rate_payload,
                headers=headers
            )

def get_ingestion_service(
    kafka_producer: KafkaProducer = Depends(get_kafka_producer)
) -> IngestionService:
    """Dependency injector for the IngestionService."""
    return IngestionService(kafka_producer)