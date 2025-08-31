# tests/unit/libs/concentration-analytics-engine/unit/test_metrics.py
import pytest
import pandas as pd
from decimal import Decimal

# We are importing a module that does not exist yet. This is expected in TDD.
from concentration_analytics_engine.metrics import (
    calculate_bulk_concentration,
    calculate_issuer_concentration,
)
from concentration_analytics_engine.exceptions import InsufficientDataError


@pytest.fixture
def sample_positions_df() -> pd.DataFrame:
    """Provides a sample DataFrame of portfolio positions for bulk concentration."""
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

# --- NEW FIXTURE ---
@pytest.fixture
def sample_issuer_positions_df() -> pd.DataFrame:
    """Provides a sample DataFrame with issuer information."""
    data = {
        "security_id": ["BOND_JPM_1", "STOCK_JPM_2", "STOCK_MSFT", "STOCK_GOOG", "FUND_VANGUARD"],
        "market_value": [
            Decimal("15000.00"), # JPM
            Decimal("10000.00"), # JPM
            Decimal("20000.00"), # MSFT
            Decimal("30000.00"), # GOOG
            Decimal("25000.00"), # Vanguard (treated as issuer)
        ],
        "ultimate_parent_issuer_id": ["JPM", "JPM", "MSFT", "GOOG", "VANGUARD"],
        "issuer_name": ["JPMorgan Chase", "JPMorgan Chase", "Microsoft Corp", "Alphabet Inc", "The Vanguard Group"]
    } # Total MV = 100,000
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

# --- NEW TESTS ---

def test_calculate_issuer_concentration_happy_path(sample_issuer_positions_df):
    """
    GIVEN a DataFrame with issuer data
    WHEN calculate_issuer_concentration is called
    THEN it should correctly group by parent issuer and calculate exposures.
    """
    # ACT
    result = calculate_issuer_concentration(sample_issuer_positions_df, top_n=3)

    # ASSERT
    assert len(result) == 3 # Should return top 3
    
    # Expected order: GOOG (30k), JPM (25k), VANGUARD (25k), MSFT (20k)
    # The two JPM positions should be aggregated.
    
    goog_exposure = next(item for item in result if item['issuer_name'] == "Alphabet Inc")
    jpm_exposure = next(item for item in result if item['issuer_name'] == "JPMorgan Chase")
    vanguard_exposure = next(item for item in result if item['issuer_name'] == "The Vanguard Group")

    assert result[0] == goog_exposure
    assert result[1] == jpm_exposure or result[1] == vanguard_exposure # Order can be tied
    assert result[2] == jpm_exposure or result[2] == vanguard_exposure

    assert jpm_exposure['exposure'] == pytest.approx(25000.0)
    assert jpm_exposure['weight'] == pytest.approx(0.25)
    
    assert goog_exposure['exposure'] == pytest.approx(30000.0)
    assert goog_exposure['weight'] == pytest.approx(0.30)

def test_calculate_issuer_concentration_handles_missing_issuer_id(sample_issuer_positions_df):
    """
    GIVEN a DataFrame where a position is missing an issuer ID
    WHEN calculate_issuer_concentration is called
    THEN it should group that position under an 'Unclassified' issuer.
    """
    # ARRANGE
    sample_issuer_positions_df.loc[sample_issuer_positions_df['security_id'] == 'STOCK_MSFT', 'ultimate_parent_issuer_id'] = None
    sample_issuer_positions_df.loc[sample_issuer_positions_df['security_id'] == 'STOCK_MSFT', 'issuer_name'] = None


    # ACT
    result = calculate_issuer_concentration(sample_issuer_positions_df, top_n=4)

    # ASSERT
    assert len(result) == 4
    unclassified_exposure = next(item for item in result if item['issuer_name'] == "Unclassified")
    assert unclassified_exposure is not None
    assert unclassified_exposure['exposure'] == pytest.approx(20000.0)
    assert unclassified_exposure['weight'] == pytest.approx(0.20)