# Developer's Guide: Portfolio Review API

## 1. Summary

This guide provides developers with the necessary steps to locally run, test, and verify the Portfolio Review feature.

---

## 2. Local Verification Workflow

This workflow demonstrates how to ingest all the necessary data to generate a complete portfolio review report and then call the API endpoint.

### Step 1: Start the System

Ensure the entire analytics platform is running locally via Docker Compose.

```bash
# From the project root directory
docker compose up --build -d
````

Wait for all services to become healthy. You can check the status with `docker compose ps`.

### Step 2: Ingest Prerequisite Data

For the `/review` service to function, the database must contain a full set of data for a portfolio.

Execute the following `curl` commands in your terminal.

```bash
# --- Define Variables ---
export PORTFOLIO_ID="DEV_REVIEW_01"
export AS_OF_DATE="2025-08-30"
export HOST="http://localhost:8000"

# --- Ingest Static Data ---
# 1. Portfolio
curl -X 'POST' "$HOST/ingest/portfolios" -H 'Content-Type: application/json' -d '{"portfolios": [{"portfolioId": "'$PORTFOLIO_ID'", "baseCurrency": "USD", "openDate": "2025-01-01", "cifId": "DEV_REVIEW_CIF", "status": "ACTIVE", "riskExposure":"Growth", "investmentTimeHorizon":"Long", "portfolioType":"Discretionary", "bookingCenter":"SG"}]}'

# 2. Instruments
curl -X 'POST' "$HOST/ingest/instruments" -H 'Content-Type: application/json' -d '{"instruments": [{"securityId": "CASH_USD", "name": "US Dollar", "isin": "CASH_USD_ISIN", "instrumentCurrency": "USD", "productType": "Cash", "assetClass": "Cash"}, {"securityId": "SEC_AAPL_REVIEW", "name": "Apple Inc Review", "isin": "US_AAPL_REVIEW_ISIN", "instrumentCurrency": "USD", "productType": "Equity", "assetClass": "Equity"}]}'

# 3. Business Date (triggers valuation)
curl -X 'POST' "$HOST/ingest/business-dates" -H 'Content-Type: application/json' -d '{"business_dates": [{"businessDate": "'$AS_OF_DATE'"}]}'

# --- Ingest Transactional Data ---
# 4. Transactions
curl -X 'POST' "$HOST/ingest/transactions" -H 'Content-Type: application/json' -d '{"transactions": [{"transaction_id": "REVIEW_DEV_BUY_01", "portfolio_id": "'$PORTFOLIO_ID'", "security_id": "SEC_AAPL_REVIEW", "transaction_date": "2025-08-20T10:00:00Z", "transaction_type": "BUY", "quantity": 100, "price": 150, "gross_transaction_amount": 15000, "trade_currency": "USD", "currency": "USD"}]}'

# 5. Market Price
curl -X 'POST' "$HOST/ingest/market-prices" -H 'Content-Type: application/json' -d '{"market_prices": [{"securityId": "SEC_AAPL_REVIEW", "priceDate": "'$AS_OF_DATE'", "price": 160.0, "currency": "USD"}]}'
```

After ingesting this data, **wait for approximately 60-90 seconds** for the event-driven pipeline to fully process everything and generate the `portfolio_timeseries` data.

### Step 3: Call the Review API Endpoint

Once the pipeline has run, you can call the endpoint with a valid request body.

```bash
curl -X 'POST' \
  "http://localhost:8001/portfolios/$PORTFOLIO_ID/review" \
  -H 'Content-Type: application/json' \
  -d '{
  "as_of_date": "'$AS_OF_DATE'",
  "sections": [
    "OVERVIEW",
    "HOLDINGS"
  ]
}' | python -m json.tool
```

You should receive a `200 OK` response containing a detailed JSON payload with the `overview` and `holdings` sections populated.

-----

## 3\. Running Tests

To verify the correctness of the review logic, run the dedicated unit, integration, and E2E tests.

```bash
# Ensure your virtual environment is active
source .venv/Scripts/activate

# Run the unit test for the service orchestration
pytest tests/unit/services/query_service/services/test_review_service.py

# Run the integration test for the API router contract
pytest tests/integration/services/query_service/test_review_router.py

# Run the full end-to-end pipeline test
pytest tests/e2e/test_review_pipeline.py
```

 