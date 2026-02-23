from src.services.query_service.app.dependencies import pagination_params, sorting_params


def test_pagination_params_default_values():
    result = pagination_params(skip=0, limit=100)
    assert result == {"skip": 0, "limit": 100}


def test_pagination_params_custom_values():
    result = pagination_params(skip=25, limit=250)
    assert result == {"skip": 25, "limit": 250}


def test_sorting_params_default_values():
    result = sorting_params(sort_by=None, sort_order="desc")
    assert result == {"sort_by": None, "sort_order": "desc"}


def test_sorting_params_custom_values():
    result = sorting_params(sort_by="transaction_date", sort_order="asc")
    assert result == {"sort_by": "transaction_date", "sort_order": "asc"}
