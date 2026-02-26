# Developer's Guide: Portfolio Summary

## 1. Summary

This guide provides developers with the necessary steps to locally run, test, and verify the Portfolio Summary feature.

---

## 2. Local Verification Workflow

This workflow demonstrates how to ingest the necessary data to generate a meaningful summary and then call the API endpoint.

### Step 1: Start the System

Ensure the entire analytics platform is running locally via Docker Compose.

```bash
# From the project root directory
docker compose up --build -d
````

Wait for all services to become healthy. You can check the status with `docker compose ps`.

### Step 2: Ingest Prerequisite Data

For the summary service to function, the database must contain a portfolio and its corresponding positions, transactions, and cashflows.

Execute the following `curl` commands in your Git Bash terminal.

```bash
# Ingest a test portfolio
curl -X 'POST' \
  'http://localhost:8200/ingest/portfolios' \
  -H 'Content-Type: application/json' \
  -d '{
  "portfolios": [{"portfolioId": "SUMMARY_DEV_01", "baseCurrency": "USD", "openDate": "2025-01-01", "cifId": "SUM_DEV_CIF", "status": "ACTIVE", "riskExposure":"High", "investmentTimeHorizon":"Long", "portfolioType":"Discretionary", "bookingCenter":"SG"}]
}'

# Ingest instruments, including one with full data and one with missing data (for "Unclassified" testing)
curl -X 'POST' \
  'http://localhost:8200/ingest/instruments' \
  -H 'Content-Type: application/json' \
  -d '{
  "instruments": [
    {"securityId": "CASH_USD", "name": "US Dollar", "isin": "CASH_USD_ISIN", "instrumentCurrency": "USD", "productType": "Cash", "assetClass": "Cash"},
    {"securityId": "SUM_SEC_01", "name": "Summary Dev Stock", "isin": "US_SUM_DEV", "instrumentCurrency": "USD", "productType": "Equity", "assetClass": "Equity", "sector": "Technology"},
    {"securityId": "SUM_SEC_02", "name": "Unclassified Stock", "isin": "US_UNCLASS", "instrumentCurrency": "USD", "productType": "Equity", "assetClass": null, "sector": null}
  ]
}'

# Ingest a business date to trigger valuation
curl -X 'POST' \
  'http://localhost:8200/ingest/business-dates' \
  -H 'Content-Type: application/json' \
  -d '{
  "business_dates": [{"businessDate": "2025-08-29"}]
}'

# Ingest transactions to create positions
curl -X 'POST' \
  'http://localhost:8200/ingest/transactions' \
  -H 'Content-Type: application/json' \
  -d '{
  "transactions": [
    {"transaction_id": "SUM_TXN_01", "portfolio_id": "SUMMARY_DEV_01", "security_id": "CASH_USD", "transaction_date": "2025-08-01T10:00:00Z", "transaction_type": "DEPOSIT", "quantity": 100000, "price": 1, "gross_transaction_amount": 100000, "trade_currency": "USD", "currency": "USD"},
    {"transaction_id": "SUM_TXN_02", "portfolio_id": "SUMMARY_DEV_01", "security_id": "SUM_SEC_01", "transaction_date": "2025-08-05T10:00:00Z", "transaction_type": "BUY", "quantity": 100, "price": 200, "gross_transaction_amount": 20000, "trade_currency": "USD", "currency": "USD"},
    {"transaction_id": "SUM_TXN_03", "portfolio_id": "SUMMARY_DEV_01", "security_id": "SUM_SEC_02", "transaction_date": "2025-08-06T10:00:00Z", "transaction_type": "BUY", "quantity": 50, "price": 50, "gross_transaction_amount": 2500, "trade_currency": "USD", "currency": "USD"}
  ]
}'

# Ingest market prices for valuation
curl -X 'POST' \
  'http://localhost:8200/ingest/market-prices' \
  -H 'Content-Type: application/json' \
  -d '{
  "market_prices": [
    {"securityId": "SUM_SEC_01", "priceDate": "2025-08-29", "price": 210.0, "currency": "USD"},
    {"securityId": "SUM_SEC_02", "priceDate": "2025-08-29", "price": 55.0, "currency": "USD"},
    {"securityId": "CASH_USD", "priceDate": "2025-08-29", "price": 1.0, "currency": "USD"}
  ]
}'
```

After ingesting this data, **wait for approximately 60-90 seconds** for the event-driven pipeline to process everything and generate the valued `daily_position_snapshots`.

### Step 3: Call the Summary API Endpoint

Once the pipeline has run, you can call the endpoint with a valid request body.

```bash
curl -X 'POST' \
  'http://localhost:8201/portfolios/SUMMARY_DEV_01/summary' \
  -H 'Content-Type: application/json' \
  -d '{
  "as_of_date": "2025-08-29",
  "period": { "type": "MTD" },
  "sections": [ "WEALTH", "ALLOCATION" ],
  "allocation_dimensions": [ "ASSET_CLASS", "SECTOR" ]
}' | python -m json.tool

```

You should receive a `200 OK` response. In the `allocation` section, note that for the `by_sector` breakdown, "Unclassified Stock" correctly falls into the "Unclassified" group.

-----

## 3\. Running Tests

To verify the correctness of the summary logic, run the dedicated unit, integration, and E2E tests.

```bash
# Ensure your virtual environment is active
source .venv/Scripts/activate

# Run all unit tests for the summary service
pytest tests/unit/services/query_service/services/test_summary_service.py

# Run the integration test for the query-service endpoint
pytest tests/integration/services/query_service/test_summary_router.py

# Run the full end-to-end pipeline test
pytest tests/e2e/test_summary_pipeline.py
```
 
