from typing import List, Literal, Optional

from pydantic import BaseModel, Field

from .business_date_dto import BusinessDate
from .fx_rate_dto import FxRate
from .instrument_dto import Instrument
from .market_price_dto import MarketPrice
from .portfolio_dto import Portfolio
from .transaction_dto import Transaction


class PortfolioBundleIngestionRequest(BaseModel):
    source_system: Optional[str] = Field(
        None,
        alias="sourceSystem",
        description="Upstream source system identifier for audit and lineage.",
        json_schema_extra={"example": "UI_UPLOAD"},
    )
    mode: Literal["UPSERT", "REPLACE"] = Field(
        "UPSERT",
        description="Ingestion mode for bundle semantics; current behavior is UPSERT-style event publication.",
    )
    business_dates: List[BusinessDate] = Field(default_factory=list, alias="businessDates")
    portfolios: List[Portfolio] = Field(default_factory=list)
    instruments: List[Instrument] = Field(default_factory=list)
    transactions: List[Transaction] = Field(default_factory=list)
    market_prices: List[MarketPrice] = Field(default_factory=list, alias="marketPrices")
    fx_rates: List[FxRate] = Field(default_factory=list, alias="fxRates")

    model_config = {
        "populate_by_name": True,
        "json_schema_extra": {
            "example": {
                "sourceSystem": "UI_UPLOAD",
                "mode": "UPSERT",
                "businessDates": [{"businessDate": "2026-01-02"}],
                "portfolios": [
                    {
                        "portfolioId": "PORT_001",
                        "baseCurrency": "USD",
                        "openDate": "2024-01-01",
                        "riskExposure": "Medium",
                        "investmentTimeHorizon": "Long",
                        "portfolioType": "Discretionary",
                        "bookingCenter": "Singapore",
                        "cifId": "CIF_12345",
                        "status": "Active",
                    }
                ],
                "instruments": [
                    {
                        "securityId": "SEC_AAPL",
                        "name": "Apple Inc.",
                        "isin": "US0378331005",
                        "instrumentCurrency": "USD",
                        "productType": "Equity",
                    }
                ],
                "transactions": [
                    {
                        "transaction_id": "TRN_001",
                        "portfolio_id": "PORT_001",
                        "instrument_id": "AAPL",
                        "security_id": "SEC_AAPL",
                        "transaction_date": "2026-01-02T10:00:00Z",
                        "transaction_type": "BUY",
                        "quantity": 10,
                        "price": 200,
                        "gross_transaction_amount": 2000,
                        "trade_currency": "USD",
                        "currency": "USD",
                    }
                ],
                "marketPrices": [
                    {
                        "securityId": "SEC_AAPL",
                        "priceDate": "2026-01-02",
                        "price": 200,
                        "currency": "USD",
                    }
                ],
                "fxRates": [
                    {
                        "fromCurrency": "USD",
                        "toCurrency": "SGD",
                        "rateDate": "2026-01-02",
                        "rate": 1.35,
                    }
                ],
            }
        },
    }
