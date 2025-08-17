# src/libs/performance-calculator-engine/src/performance_calculator_engine/exceptions.py

class PerformanceCalculatorError(Exception):
    """Base exception for all performance calculator errors."""
    def __init__(self, message="An unspecified error occurred in the performance calculator."):
        self.message = message
        super().__init__(self.message)


class InvalidInputDataError(PerformanceCalculatorError):
    """Raised when the input daily data is invalid or malformed."""
    def __init__(self, message="Invalid input data provided for performance calculation."):
        self.message = message
        super().__init__(self.message)


class CalculationLogicError(PerformanceCalculatorError):
    """Raised when there's an error in the core calculation logic."""
    def __init__(self, message="An error occurred during performance calculation logic."):
        self.message = message
        super().__init__(self.message)


class MissingConfigurationError(PerformanceCalculatorError):
    """Raised when required configuration for the calculator is missing."""
    def __init__(self, message="Missing required configuration for performance calculator."):
        self.message = message
        super().__init__(self.message)