import pytest
from pydantic import ValidationError

from src.services.query_service.app.dtos.lookup_dto import LookupItem, LookupResponse


def test_lookup_item_requires_id_and_label():
    with pytest.raises(ValidationError):
        LookupItem.model_validate({"id": "portfolio"})


def test_lookup_response_defaults_to_empty_items():
    response = LookupResponse.model_validate({})
    assert response.items == []


def test_lookup_response_accepts_lookup_items():
    response = LookupResponse.model_validate(
        {"items": [{"id": "P1", "label": "Growth Portfolio"}]}
    )
    assert len(response.items) == 1
    assert response.items[0].id == "P1"
    assert response.items[0].label == "Growth Portfolio"
