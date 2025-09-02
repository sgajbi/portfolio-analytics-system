# tests/unit/libs/concentration_analytics_engine/test_concentration_metrics.py
import pytest
import pandas as pd
from decimal import Decimal

from concentration_analytics_engine.metrics import calculate_bulk_concentration, calculate_issuer_concentration

@pytest.fixture
def sample_positions_df():
    data = [
        {"security_id": "S1", "market_value": Decimal("60000"), "issuer_id": "JPM", "issuer_name": "JPMorgan"},
        {"security_id": "S2", "market_value": Decimal("40000"), "issuer_id": "MSFT", "issuer_name": "Microsoft"},
        {"security_id": "S3", "market_value": Decimal("30000"), "issuer_id": "JPM", "issuer_name": "JPMorgan"},
        {"security_id": "S4", "market_value": Decimal("20000"), "issuer_id": None, "issuer_name": None}, # Unclassified
    ]
    return pd.DataFrame(data)

def test_bulk_concentration(sample_positions_df):
    """
    GIVEN a valid DataFrame of positions
    WHEN calculate_bulk_concentration is called
    THEN it returns the correct HHI, single position, and Top-N weights.
    """
    # Total MV = 150k. Weights: S1=0.4, S2=0.2666, S3=0.2, S4=0.1333
    
    # ACT
    result = calculate_bulk_concentration(sample_positions_df, top_n=[1, 2])
    
    # ASSERT
    # HHI = (0.4^2) + (0.2666...^2) + (0.2^2) + (0.1333...^2) = 0.16 + 0.0711... + 0.04 + 0.0177... = 0.2888...
    assert result["hhi"] == pytest.approx(0.2888, abs=1e-4)
    assert result["single_position_weight"] == pytest.approx(0.4)
    assert result["top_n_weights"]["1"] == pytest.approx(0.4)
    assert result["top_n_weights"]["2"] == pytest.approx(0.4 + 0.2666, abs=1e-4)

def test_issuer_concentration(sample_positions_df):
    """
    GIVEN a valid DataFrame of positions
    WHEN calculate_issuer_concentration is called
    THEN it correctly groups by issuer and calculates exposure.
    """
    # JPM exposure = 90k (60%)
    # MSFT exposure = 40k (26.6%)
    # Unclassified = 20k (13.3%)

    # ACT
    result = calculate_issuer_concentration(sample_positions_df, top_n=3)

    # ASSERT
    assert len(result) == 3
    
    jpm_result = next(item for item in result if item["issuer_id"] == "JPM")
    assert jpm_result["issuer_name"] == "JPMorgan"
    assert jpm_result["exposure"] == pytest.approx(90000)
    assert jpm_result["weight"] == pytest.approx(0.6)

    unclassified_result = next(item for item in result if item["issuer_id"] == "UNCLASSIFIED")
    assert unclassified_result["issuer_name"] == "Unclassified"
    assert unclassified_result["exposure"] == pytest.approx(20000)
    assert unclassified_result["weight"] == pytest.approx(20000 / 150000)

def test_issuer_concentration_with_missing_issuer_name():
    """
    GIVEN a DataFrame where a position has an issuer_id but no issuer_name
    WHEN calculate_issuer_concentration is called
    THEN it should robustly fall back to using the issuer_id as the name.
    """
    # ARRANGE
    data = [
        {"security_id": "S1", "market_value": Decimal("1000"), "issuer_id": "KNOWN_ID", "issuer_name": None},
    ]
    df = pd.DataFrame(data)

    # ACT
    result = calculate_issuer_concentration(df, top_n=1)

    # ASSERT
    assert len(result) == 1
    assert result[0]["issuer_id"] == "KNOWN_ID"
    # This is the key assertion: the name falls back to the ID
    assert result[0]["issuer_name"] == "KNOWN_ID"
    assert result[0]["weight"] == pytest.approx(1.0)

def test_concentration_on_empty_dataframe():
    """
    GIVEN an empty DataFrame
    WHEN concentration metrics are calculated
    THEN they should return zeroed-out, valid structures.
    """
    # ARRANGE
    empty_df = pd.DataFrame(columns=["security_id", "market_value", "issuer_id", "issuer_name"])

    # ACT
    bulk_result = calculate_bulk_concentration(empty_df, top_n=[1, 2])
    issuer_result = calculate_issuer_concentration(empty_df, top_n=5)

    # ASSERT
    assert bulk_result["hhi"] == 0.0
    assert bulk_result["single_position_weight"] == 0.0
    assert bulk_result["top_n_weights"]["1"] == 0.0
    assert issuer_result == []