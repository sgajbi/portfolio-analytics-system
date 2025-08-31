# tests/unit/services/query_service/services/test_review_service.py
import pytest
from unittest.mock import AsyncMock, patch
from datetime import date
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession
from src.services.query_service.app.services.review_service import ReviewService
from src.services.query_service.app.dtos.review_dto import PortfolioReviewRequest, ReviewSection
from portfolio_common.database_models import Portfolio
from src.services.query_service.app.dtos.summary_dto import (
    SummaryResponse as SummarySubResponse, ResponseScope, WealthSummary, PnlSummary,
    IncomeSummary, ActivitySummary, AllocationSummary, AllocationGroup
)
from src.services.query_service.app.dtos.position_dto import PortfolioPositionsResponse, Position
from src.services.query_service.app.dtos.transaction_dto import PaginatedTransactionResponse, TransactionRecord

pytestmark = pytest.mark.asyncio

@pytest.fixture
def mock_dependencies():
    """Mocks all service dependencies for the ReviewService."""
    mock_portfolio_service = AsyncMock()
    mock_summary_service = AsyncMock()
    mock_performance_service = AsyncMock()
    mock_risk_service = AsyncMock()
    mock_position_service = AsyncMock()
    mock_transaction_service = AsyncMock()
    # ADDED: Mock for instrument service is now needed for transaction grouping
    mock_instrument_service = AsyncMock()

    # Configure mock return values
    mock_portfolio_service.get_portfolio_by_id.return_value = Portfolio(
        risk_exposure="Growth", portfolio_type="Discretionary"
    )
    mock_summary_service.get_portfolio_summary.return_value = SummarySubResponse(
        scope=ResponseScope(portfolio_id="P1", as_of_date=date(2025,8,30), period_start_date=date(2025,1,1), period_end_date=date(2025,8,30)),
        wealth=WealthSummary(total_market_value=Decimal("100000"), total_cash=Decimal("10000")),
        pnlSummary=PnlSummary(net_new_money=1, realized_pnl=2, unrealized_pnl_change=3, total_pnl=5),
        incomeSummary=IncomeSummary(total_dividends=1, total_interest=1),
        activitySummary=ActivitySummary(total_deposits=1,total_withdrawals=1,total_transfers_in=1,total_transfers_out=1,total_fees=1),
        allocation=AllocationSummary(byAssetClass=[AllocationGroup(group="Equity", market_value=90000, weight=0.9)])
    )
    # UPDATED: The Position object now includes asset_class
    mock_position_service.get_portfolio_positions.return_value = PortfolioPositionsResponse(
        portfolio_id="P1", positions=[Position(security_id="CASH_USD", quantity=1, instrument_name="Cash", position_date=date(2025,8,30), cost_basis=1, asset_class="Cash")]
    )
    mock_transaction_service.get_transactions.return_value = PaginatedTransactionResponse(
        portfolio_id="P1", total=1, skip=0, limit=1000, transactions=[TransactionRecord(transaction_id="T1", security_id="SEC_AAPL", transaction_date=date(2025,8,29), transaction_type="BUY", instrument_id="I1", quantity=1, price=1, gross_transaction_amount=1, currency="USD")]
    )
    # ADDED: Mock return value for instrument service
    mock_instrument_service.get_instruments_by_ids.return_value = []


    with patch("src.services.query_service.app.services.review_service.PortfolioService", return_value=mock_portfolio_service), \
         patch("src.services.query_service.app.services.review_service.SummaryService", return_value=mock_summary_service), \
         patch("src.services.query_service.app.services.review_service.PerformanceService", return_value=mock_performance_service), \
         patch("src.services.query_service.app.services.review_service.RiskService", return_value=mock_risk_service), \
         patch("src.services.query_service.app.services.review_service.PositionService", return_value=mock_position_service), \
         patch("src.services.query_service.app.services.review_service.TransactionService", return_value=mock_transaction_service), \
         patch("src.services.query_service.app.services.review_service.InstrumentService", return_value=mock_instrument_service): # ADDED: Patch instrument service
        
        service = ReviewService(AsyncMock(spec=AsyncSession))
        yield {
            "service": service, "portfolio": mock_portfolio_service, "summary": mock_summary_service,
            "performance": mock_performance_service, "risk": mock_risk_service,
            "position": mock_position_service, "transaction": mock_transaction_service,
            "instrument": mock_instrument_service # ADDED: Include in returned dict
        }

async def test_get_portfolio_review_orchestrates_correctly(mock_dependencies):
    """
    GIVEN a request for all sections
    WHEN get_portfolio_review is called
    THEN it should call all dependent services and assemble the response.
    """
    # ARRANGE
    service = mock_dependencies["service"]
    request = PortfolioReviewRequest(
        as_of_date=date(2025, 8, 30),
        sections=list(ReviewSection) # Request all sections
    )
    
    # ACT
    response = await service.get_portfolio_review("P1", request)

    # ASSERT
    # Verify all services were called
    for key in ["portfolio", "summary", "performance", "risk", "position", "transaction"]:
        assert mock_dependencies[key].mock_calls is not None
        
    # VERIFY: The instrument service is now only called for transactions
    mock_dependencies["instrument"].get_instruments_by_ids.assert_awaited_once()

    # Verify response assembly
    assert response.overview is not None
    assert response.overview.total_market_value == 100000
    assert response.overview.risk_profile == "Growth"
    
    assert response.allocation is not None
    assert response.allocation.by_asset_class[0].group == "Equity"
    
    assert response.holdings is not None
    assert "Cash" in response.holdings.holdings_by_asset_class
    assert response.holdings.holdings_by_asset_class["Cash"][0].security_id == "CASH_USD"
    
    assert response.transactions is not None
    assert "Unclassified" in response.transactions.transactions_by_asset_class
    assert response.transactions.transactions_by_asset_class["Unclassified"][0].transaction_id == "T1"