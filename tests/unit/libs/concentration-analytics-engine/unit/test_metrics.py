# tests/unit/libs/concentration-analytics-engine/unit/test_metrics.py
import pytest
import pandas as pd
from decimal import Decimal

# We are importing a module that does not exist yet. This is expected in TDD.
from concentration_analytics_engine.metrics import (
    calculate_bulk_concentration,
)
from concentration_analytics_engine.exceptions import InsufficientDataError


@pytest.fixture
def sample_positions_df() -> pd.DataFrame:
    """Provides a sample DataFrame of portfolio positions."""
    data = {
        "security_id": ["SEC_AAPL", "SEC_MSFT", "SEC_GOOG", "SEC_AMZN", "SEC_BRK"],
        "market_value": [
            Decimal("40000.00"),  # 40%
            Decimal("25000.00"),  # 25%
            Decimal("15000.00"),  # 15%
            Decimal("10000.00"),  # 10%
            Decimal("10000.00"),  # 10%
        ],
    }
    return pd.DataFrame(data)


def test_calculate_bulk_concentration_happy_path(sample_positions_df):
    """
    GIVEN a valid DataFrame of positions
    WHEN calculate_bulk_concentration is called
    THEN it should return the correct single-position, Top-N, and HHI metrics.
    """
    # ARRANGE
    top_n_config = [3, 5]

    # ACT
    result = calculate_bulk_concentration(sample_positions_df, top_n_config)

    # ASSERT
    # Single Position (AAPL) = 40,000 / 100,000 = 0.40
    assert result["single_position_weight"] == pytest.approx(0.40)

    # Top 3 = 40% + 25% + 15% = 80%
    assert result["top_n_weights"]["3"] == pytest.approx(0.80)

    # Top 5 = 40% + 25% + 15% + 10% + 10% = 100%
    assert result["top_n_weights"]["5"] == pytest.approx(1.0)

    # HHI = (0.4^2 + 0.25^2 + 0.15^2 + 0.1^2 + 0.1^2) = 0.16 + 0.0625 + 0.0225 + 0.01 + 0.01 = 0.265
    assert result["hhi"] == pytest.approx(0.265)


def test_calculate_bulk_concentration_handles_empty_dataframe():
    """
    GIVEN an empty DataFrame
    WHEN calculate_bulk_concentration is called
    THEN it should raise an InsufficientDataError.
    """
    with pytest.raises(InsufficientDataError):
        calculate_bulk_concentration(pd.DataFrame(), [5])