# tests/unit/services/recalculation_service/core/test_recalculation_logic.py
import pytest
from unittest.mock import AsyncMock, patch, MagicMock, ANY
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession
from portfolio_common.database_models import Transaction
from src.services.recalculation_service.app.core.recalculation_logic import RecalculationLogic
from src.services.recalculation_service.app.repositories.recalculation_repository import RecalculationRepository

pytestmark = pytest.mark.asyncio


@pytest.fixture
def mock_dependencies():
    """A fixture to patch all external dependencies for the logic test."""
    mock_repo_instance = AsyncMock(spec=RecalculationRepository)
    mock_kafka_producer = MagicMock()
    mock_kafka_producer.publish_message = MagicMock()
    
    with patch(
        "src.services.recalculation_service.app.core.recalculation_logic.get_kafka_producer",
        return_value=mock_kafka_producer
    ), patch(
        "src.services.recalculation_service.app.core.recalculation_logic.RecalculationRepository",
        return_value=mock_repo_instance
    ):
        yield {
            "repo": mock_repo_instance,
            "kafka_producer": mock_kafka_producer
        }


async def test_execute_republishes_with_correct_headers(mock_dependencies):
    """
    GIVEN a recalculation job
    WHEN RecalculationLogic.execute is called
    THEN it should republish transaction events with both 'correlation_id' and 'recalculation_id' headers.
    """
    # ARRANGE
    mock_repo = mock_dependencies["repo"]
    mock_kafka_producer = mock_dependencies["kafka_producer"]
    
    # Mock the return value of the repository method with a fully valid Transaction object
    mock_transactions = [
        Transaction(
            transaction_id="TXN1",
            portfolio_id="P1",
            instrument_id="I1",
            security_id="S1",
            transaction_date=datetime(2025, 1, 1),
            transaction_type="BUY",
            quantity=Decimal("1"),
            price=Decimal("1"),
            gross_transaction_amount=Decimal("1"),
            trade_currency="USD",
            currency="USD",
            trade_fee=Decimal("0")
        )
    ]
    mock_repo.get_all_transactions_for_security.return_value = mock_transactions
    
    job_id = 99
    correlation_id = "test-correlation-id"

    # ACT
    await RecalculationLogic.execute(
        db_session=AsyncMock(spec=AsyncSession),
        job_id=job_id,
        portfolio_id="P1",
        security_id="S1",
        from_date=date(2025, 1, 1),
        correlation_id=correlation_id
    )

    # ASSERT
    mock_kafka_producer.publish_message.assert_called_once()
    
    # Check the headers of the call
    call_args = mock_kafka_producer.publish_message.call_args.kwargs
    headers_dict = {key: value.decode('utf-8') for key, value in call_args['headers']}
    
    assert headers_dict['correlation_id'] == correlation_id
    assert headers_dict['recalculation_id'] == str(job_id)