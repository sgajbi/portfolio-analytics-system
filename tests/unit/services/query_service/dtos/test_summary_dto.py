# tests/unit/services/query_service/dtos/test_summary_dto.py
import pytest
from pydantic import ValidationError
from datetime import date

from src.services.query_service.app.dtos.summary_dto import SummaryRequest

def test_summary_request_valid():
    """
    GIVEN a valid raw request dictionary
    WHEN it is parsed by the SummaryRequest model
    THEN it should succeed without errors.
    """
    payload = {
        "as_of_date": "2025-08-29",
        "period": {
            "type": "YTD"
        },
        "sections": [
            "WEALTH",
            "ALLOCATION"
        ],
        "allocation_dimensions": [
            "ASSET_CLASS",
            "CURRENCY"
        ]
    }
    
    request = SummaryRequest.model_validate(payload)
    
    assert request.as_of_date == date(2025, 8, 29)
    assert request.period.type == "YTD"
    assert len(request.sections) == 2
    assert len(request.allocation_dimensions) == 2

def test_summary_request_invalid_section_fails():
    """
    GIVEN a request dictionary with an invalid section name
    WHEN it is parsed by the SummaryRequest model
    THEN it should raise a ValidationError.
    """
    payload = {
        "as_of_date": "2025-08-29",
        "period": {"type": "YTD"},
        "sections": ["WEALTH", "INVALID_SECTION"]
    }
    
    with pytest.raises(ValidationError):
        SummaryRequest.model_validate(payload)

def test_summary_request_invalid_dimension_fails():
    """
    GIVEN a request dictionary with an invalid allocation dimension
    WHEN it is parsed by the SummaryRequest model
    THEN it should raise a ValidationError.
    """
    payload = {
        "as_of_date": "2025-08-29",
        "period": {"type": "YTD"},
        "sections": ["ALLOCATION"],
        "allocation_dimensions": ["ASSET_CLASS", "INVALID_DIMENSION"]
    }
    
    with pytest.raises(ValidationError):
        SummaryRequest.model_validate(payload)

def test_summary_request_missing_required_field_fails():
    """
    GIVEN a request dictionary missing a required field (e.g., as_of_date)
    WHEN it is parsed by the SummaryRequest model
    THEN it should raise a ValidationError.
    """
    payload = {
        # as_of_date is missing
        "period": {"type": "YTD"},
        "sections": ["WEALTH"]
    }

    with pytest.raises(ValidationError):
        SummaryRequest.model_validate(payload)