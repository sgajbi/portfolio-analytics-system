# tests/unit/services/ingestion-service/services/test_ingestion_service.py
import pytest
from unittest.mock import MagicMock
from datetime import date, datetime
from decimal import Decimal

from portfolio_common.kafka_utils import KafkaProducer
from portfolio_common.logging_utils import correlation_id_var
from src.services.ingestion_service.app.services.ingestion_service import IngestionService
from src.services.ingestion_service.app.DTOs.portfolio_dto import Portfolio
from src.services.ingestion_service.app.DTOs.transaction_dto import Transaction
from src.services.ingestion_service.app.DTOs.instrument_dto import Instrument
from src.services.ingestion_service.app.DTOs.market_price_dto import MarketPrice
from src.services.ingestion_service.app.DTOs.fx_rate_dto import FxRate

pytestmark = pytest.mark.asyncio

@pytest.fixture
def mock_kafka_producer() -> MagicMock:
    """Provides a mock KafkaProducer."""
    return MagicMock(spec=KafkaProducer)

@pytest.fixture
def ingestion_service(mock_kafka_producer: MagicMock) -> IngestionService:
    """Provides an IngestionService instance with a mocked producer."""
    return IngestionService(mock_kafka_producer)

async def test_publish_portfolios(ingestion_service: IngestionService, mock_kafka_producer: MagicMock):
    """Verifies that portfolios are published to the correct topic with the portfolioId as the key."""
    # ARRANGE
    portfolios = [
        Portfolio(portfolioId="P1", baseCurrency="USD", openDate=date(2025,1,1), riskExposure="a", investmentTimeHorizon="b", portfolioType="c", bookingCenter="d", cifId="e", status="f")
    ]
    
    # ACT
    await ingestion_service.publish_portfolios(portfolios)
    
    # ASSERT
    mock_kafka_producer.publish_message.assert_called_once()
    call_args = mock_kafka_producer.publish_message.call_args.kwargs
    assert call_args['topic'] == "raw_portfolios"
    assert call_args['key'] == "P1"
    assert call_args['value']['portfolioId'] == "P1"

async def test_publish_transactions(ingestion_service: IngestionService, mock_kafka_producer: MagicMock):
    """Verifies that transactions are published to the correct topic with the portfolio_id as the key."""
    # ARRANGE
    transactions = [
        Transaction(transaction_id="T1", portfolio_id="P1", instrument_id="I1", security_id="S1", transaction_date=datetime.now(), transaction_type="BUY", quantity=1, price=1, gross_transaction_amount=1, trade_currency="USD", currency="USD")
    ]
    
    # ACT
    await ingestion_service.publish_transactions(transactions)
    
    # ASSERT
    mock_kafka_producer.publish_message.assert_called_once()
    call_args = mock_kafka_producer.publish_message.call_args.kwargs
    assert call_args['topic'] == "raw_transactions"
    assert call_args['key'] == "P1"
    assert call_args['value']['transaction_id'] == "T1"

async def test_publish_with_correlation_id(ingestion_service: IngestionService, mock_kafka_producer: MagicMock):
    """Verifies that the correlation ID from the context is added to Kafka message headers."""
    # ARRANGE
    portfolios = [
        Portfolio(portfolioId="P1", baseCurrency="USD", openDate=date(2025,1,1), riskExposure="a", investmentTimeHorizon="b", portfolioType="c", bookingCenter="d", cifId="e", status="f")
    ]
    token = correlation_id_var.set("test-corr-id-123")
    
    # ACT
    try:
        await ingestion_service.publish_portfolios(portfolios)
    finally:
        correlation_id_var.reset(token)
        
    # ASSERT
    call_args = mock_kafka_producer.publish_message.call_args.kwargs
    headers = dict(call_args['headers'])
    assert headers['correlation_id'] == b'test-corr-id-123'