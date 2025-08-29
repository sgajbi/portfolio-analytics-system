# src/libs/risk-analytics-engine/src/risk_analytics_engine/exceptions.py

class RiskAnalyticsError(Exception):
    """Base exception for all errors raised by the risk analytics engine."""
    def __init__(self, message="An unspecified error occurred in the risk analytics engine."):
        self.message = message
        super().__init__(self.message)


class InsufficientDataError(RiskAnalyticsError):
    """Raised when the input data series is too short for a calculation."""
    def __init__(self, message="Insufficient data provided for risk calculation."):
        self.message = message
        super().__init__(self.message)