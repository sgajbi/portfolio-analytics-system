# tests/e2e/test_5_day_workflow.py
import pytest

# Mark all tests in this file as being part of the 'dependency' group for ordering
pytestmark = pytest.mark.dependency()

def test_full_5_day_workflow():
    """
    This test will orchestrate the full 5-day workflow, including:
    1. Ingesting all prerequisite data (portfolios, instruments).
    2. Ingesting transactions and prices day-by-day.
    3. Polling for and verifying the state of positions and transactions at each stage.
    4. Ingesting back-dated data.
    5. Verifying the final, recalculated state of the portfolio.
    """
    pytest.skip("Test case for the full 5-day workflow is not yet implemented.")