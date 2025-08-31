# src/libs/concentration-analytics-engine/src/concentration_analytics_engine/exceptions.py

class ConcentrationAnalyticsError(Exception):
    """Base exception for all errors raised by the concentration analytics engine."""
    def __init__(self, message="An unspecified error occurred in the concentration analytics engine."):
        self.message = message
        super().__init__(self.message)


class InsufficientDataError(ConcentrationAnalyticsError):
    """Raised when the input data series is too short for a calculation."""
    def __init__(self, message="Insufficient data provided for concentration calculation."):
        self.message = message
        super().__init__(self.message)