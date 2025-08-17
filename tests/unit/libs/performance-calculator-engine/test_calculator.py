# tests/unit/libs/performance-calculator-engine/test_calculator.py
import pytest
import json
from pathlib import Path
from decimal import Decimal

from performance_calculator_engine.calculator import PortfolioPerformanceCalculator
from performance_calculator_engine.exceptions import InvalidInputDataError

@pytest.fixture
def sample_input_data():
    """Loads the sample input data from the JSON file."""
    p = Path(__file__).parent / "sampleInput.json"
    with open(p, 'r') as f:
        return json.load(f)

def test_calculator_with_valid_net_data(sample_input_data):
    """
    Tests that the calculator produces the correct daily and cumulative returns
    for a standard NET basis calculation.
    """
    # ARRANGE
    config = {
        "performance_start_date": sample_input_data["performance_start_date"],
        "metric_basis": sample_input_data["metric_basis"],
        "report_start_date": sample_input_data["report_start_date"],
        "report_end_date": sample_input_data["report_end_date"],
        "period_type": sample_input_data["period_type"],
    }
    calculator = PortfolioPerformanceCalculator(config)

    # ACT
    results = calculator.calculate_performance(sample_input_data["daily_data"])

    # ASSERT
    assert len(results) == 5
    
    # Verify daily returns for a few key days
    # Day 1: (101000 - 100000) / 100000 = 1.0%
    assert pytest.approx(results[0]['daily ror %']) == 1.0
    # Day 3: (108000 - 5000 - 102500 - 10) / (102500 + 5000) = 0.456%
    assert pytest.approx(results[2]['daily ror %'], abs=1e-3) == 0.456
    # Day 4: (106500 - 108000 - (-2000) - 12) / 108000 = 0.45185%
    assert pytest.approx(results[3]['daily ror %'], abs=1e-3) == 0.451

    # Verify final cumulative return
    # (1.01 * 1.01485 * 1.00456 * 1.00451 * 1.00469) - 1 = 3.93%
    assert pytest.approx(results[4]['Final Cumulative ROR %'], abs=1e-2) == 3.93

def test_calculator_raises_for_empty_data(sample_input_data):
    """
    Tests that the calculator raises an InvalidInputDataError if the daily_data list is empty.
    """
    # ARRANGE
    config = {
        "performance_start_date": sample_input_data["performance_start_date"],
        "metric_basis": sample_input_data["metric_basis"],
        "report_start_date": sample_input_data["report_start_date"],
        "report_end_date": sample_input_data["report_end_date"],
        "period_type": sample_input_data["period_type"],
    }
    calculator = PortfolioPerformanceCalculator(config)

    # ACT & ASSERT
    with pytest.raises(InvalidInputDataError, match="Daily data list cannot be empty."):
        calculator.calculate_performance([])