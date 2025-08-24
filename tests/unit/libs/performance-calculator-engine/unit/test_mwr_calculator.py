# tests/unit/libs/performance-calculator-engine/unit/test_mwr_calculator.py
import pytest
from performance_calculator_engine.mwr_calculator import MWRCalculator

def test_mwr_calculator_can_be_instantiated():
    """
    Tests that the MWRCalculator class can be instantiated without errors.
    """
    try:
        calculator = MWRCalculator()
        assert calculator is not None
    except Exception as e:
        pytest.fail(f"Failed to instantiate MWRCalculator: {e}")