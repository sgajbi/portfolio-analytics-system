from portfolio_common.openapi_enrichment import enrich_openapi_schema


def test_enrich_openapi_schema_populates_missing_operation_docs() -> None:
    schema = {
        "paths": {
            "/health/live": {"get": {"responses": {"200": {"description": "ok"}}}},
            "/metrics": {"get": {"responses": {"200": {"description": "ok"}}}},
        },
        "components": {"schemas": {}},
    }

    enriched = enrich_openapi_schema(schema, service_name="query_service")
    assert enriched["paths"]["/health/live"]["get"]["summary"]
    assert enriched["paths"]["/health/live"]["get"]["description"]
    assert enriched["paths"]["/health/live"]["get"]["tags"] == ["Health"]
    assert enriched["paths"]["/metrics"]["get"]["tags"] == ["Monitoring"]


def test_enrich_openapi_schema_populates_schema_field_description_and_example() -> None:
    schema = {
        "paths": {},
        "components": {
            "schemas": {
                "PositionRecord": {
                    "type": "object",
                    "properties": {
                        "portfolioId": {"type": "string"},
                        "asOfDate": {"type": "string", "format": "date"},
                        "marketValue": {"type": "number"},
                    },
                }
            }
        },
    }

    enriched = enrich_openapi_schema(schema, service_name="query_service")
    props = enriched["components"]["schemas"]["PositionRecord"]["properties"]
    assert props["portfolioId"]["description"]
    assert props["portfolioId"]["example"] == "DEMO_DPM_EUR_001"
    assert props["asOfDate"]["example"] == "2026-02-27"
    assert isinstance(props["marketValue"]["example"], float)
