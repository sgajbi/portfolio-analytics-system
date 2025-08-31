# tests/unit/services/query_service/dtos/test_concentration_dto.py
import pytest
from pydantic import ValidationError
from datetime import date

from src.services.query_service.app.dtos.concentration_dto import ConcentrationRequest

def test_concentration_request_valid_payload():
    """
    GIVEN a valid request payload dictionary
    WHEN it is parsed by the ConcentrationRequest model
    THEN it should succeed without errors and create the correct objects.
    """
    payload = {
        "scope": {
            "as_of_date": "2025-08-31",
            "reporting_currency": "EUR"
        },
        "metrics": ["ISSUER", "BULK"],
        "options": {
            "lookthrough_enabled": False,
            "issuer_top_n": 5,
            "bulk_top_n": [3, 5, 10]
        }
    }
    
    request = ConcentrationRequest.model_validate(payload)
    
    assert request.scope.as_of_date == date(2025, 8, 31)
    assert request.scope.reporting_currency == "EUR"
    assert request.metrics == ["ISSUER", "BULK"]
    assert request.options.issuer_top_n == 5
    assert request.options.bulk_top_n == [3, 5, 10]

def test_concentration_request_invalid_metric_fails():
    """
    GIVEN a payload with an unknown metric name
    WHEN it is parsed
    THEN it should raise a ValidationError.
    """
    payload = {
        "scope": {"as_of_date": "2025-08-31"},
        "metrics": ["ISSUER", "INVALID_METRIC"]
    }
    
    with pytest.raises(ValidationError):
        ConcentrationRequest.model_validate(payload)

def test_concentration_request_missing_required_scope_field_fails():
    """
    GIVEN a payload missing a required field in the scope
    WHEN it is parsed
    THEN it should raise a ValidationError.
    """
    payload = {
        "scope": {}, # as_of_date is missing
        "metrics": ["BULK"]
    }

    with pytest.raises(ValidationError):
        ConcentrationRequest.model_validate(payload)