# Developer's Guide: Concentration Analytics API

## 1. Summary

This guide provides developers with the necessary steps to locally run, test, and verify the Concentration Analytics feature.

---

## 2. Local Verification Workflow

This workflow demonstrates how to ingest all the necessary data to generate a complete concentration report and then call the API endpoint.

### Step 1: Start the System

Ensure the entire analytics platform is running locally via Docker Compose.

```bash
# From the project root directory
docker compose up --build -d
````

Wait for all services to become healthy. You can check the status with `docker compose ps`.

### Step 2: Ingest Prerequisite Data

For the `/concentration` service to function, the database must contain a full set of data for a portfolio, including issuer information for the instruments.

Execute the following `curl` commands in your terminal.

```bash
# --- Define Variables ---
export PORTFOLIO_ID="DEV_CONC_01"
export AS_OF_DATE="2025-08-31"
export HOST="http://localhost:8000"

# --- Ingest Static Data ---
# 1. Portfolio
curl -X 'POST' "$HOST/ingest/portfolios" -H 'Content-Type: application/json' -d '{"portfolios": [{"portfolioId": "'$PORTFOLIO_ID'", "baseCurrency": "USD", "openDate": "2025-01-01", "cifId": "DEV_CONC_CIF", "status": "ACTIVE", "riskExposure":"Growth", "investmentTimeHorizon":"Long", "portfolioType":"Discretionary", "bookingCenter":"SG"}]}'

# 2. Instruments (with Issuer Data)
curl -X 'POST' "$HOST/ingest/instruments" -H 'Content-Type: application/json' -d '{"instruments": [{"securityId": "SEC_A", "name": "Stock A", "isin": "ISIN_A", "instrumentCurrency": "USD", "productType": "Equity", "issuerId": "ISS_XYZ", "ultimateParentIssuerId": "PARENT_XYZ"}, {"securityId": "SEC_B", "name": "Stock B", "isin": "ISIN_B", "instrumentCurrency": "USD", "productType": "Equity", "issuerId": "ISS_ABC", "ultimateParentIssuerId": "PARENT_ABC"}]}'

# 3. Business Date (triggers valuation)
curl -X 'POST' "$HOST/ingest/business-dates" -H 'Content-Type: application/json' -d '{"business_dates": [{"businessDate": "'$AS_OF_DATE'"}]}'

# --- Ingest Transactional Data ---
# 4. Transactions
curl -X 'POST' "$HOST/ingest/transactions" -H 'Content-Type: application/json' -d '{"transactions": [{"transaction_id": "CONC_DEV_BUY_A", "portfolio_id": "'$PORTFOLIO_ID'", "instrument_id": "A", "security_id": "SEC_A", "transaction_date": "'$AS_OF_DATE'T10:00:00Z", "transaction_type": "BUY", "quantity": 100, "price": 1, "gross_transaction_amount": 100, "trade_currency": "USD", "currency": "USD"}, {"transaction_id": "CONC_DEV_BUY_B", "portfolio_id": "'$PORTFOLIO_ID'", "instrument_id": "B", "security_id": "SEC_B", "transaction_date": "'$AS_OF_DATE'T10:00:00Z", "transaction_type": "BUY", "quantity": 100, "price": 1, "gross_transaction_amount": 100, "trade_currency": "USD", "currency": "USD"}]}'

# 5. Market Prices
curl -X 'POST' "$HOST/ingest/market-prices" -H 'Content-Type: application/json' -d '{"market_prices": [{"securityId": "SEC_A", "priceDate": "'$AS_OF_DATE'", "price": 800.0, "currency": "USD"}, {"securityId": "SEC_B", "priceDate": "'$AS_OF_DATE'", "price": 200.0, "currency": "USD"}]}'
```

After ingesting this data, **wait for approximately 60-90 seconds** for the event-driven pipeline to fully process everything and generate the valued `daily_position_snapshots`.

### Step 3: Call the Concentration API Endpoint

Once the pipeline has run, you can call the endpoint with a valid request body.

```bash
curl -X 'POST' \
  "http://localhost:8001/portfolios/$PORTFOLIO_ID/concentration" \
  -H 'Content-Type: application/json' \
  -d '{
  "scope": {
    "as_of_date": "'$AS_OF_DATE'"
  },
  "metrics": [
    "ISSUER",
    "BULK"
  ]
}' | python -m json.tool
```

You should receive a `200 OK` response containing a detailed JSON payload with the `bulk_concentration` and `issuer_concentration` sections populated.

-----

## 3\. Running Tests

To verify the correctness of the concentration logic, run the dedicated unit, integration, and E2E tests.

```bash
# Ensure your virtual environment is active
source .venv/Scripts/activate

# Run all unit tests for the concentration-analytics-engine
pytest tests/unit/libs/concentration-analytics-engine/

# Run the unit test for the service layer orchestration
pytest tests/unit/services/query_service/services/test_concentration_service.py

# Run the integration test for the API router contract
pytest tests/integration/services/query_service/test_concentration_router.py

# Run the full end-to-end pipeline test
pytest tests/e2e/test_concentration_pipeline.py
```
 