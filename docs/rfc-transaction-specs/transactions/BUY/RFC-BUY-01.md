# RFC-BUY-01 Canonical BUY Transaction Specification

## 1. Document Metadata

* **Document ID:** RFC-BUY-01
* **Title:** Canonical BUY Transaction Specification
* **Version:** 1.0.0
* **Status:** Draft
* **Owner:** lotus-core engineering
* **Reviewers:** Platform Architecture, lotus-risk engineering
* **Approvers:** lotus-core maintainers
* **Last Updated:** 2026-03-01
* **Effective Date:** 2026-03-01 (pending formal approval)

### 1.1 Change Log

| Version | Date  | Author | Summary                             |
| ------- | ----- | ------ | ----------------------------------- |
| 1.0.0   | 2026-03-01 | lotus-core engineering  | Initial canonical BUY specification |

### 1.2 Purpose

This document defines the canonical, target-state specification for processing a `BUY` transaction in a private-banking / wealth-tech platform.

This RFC is the source of truth for:

* business semantics
* implementation behavior
* AI-assisted code generation
* automated testing
* validation and regression control
* BA analysis
* operations and support runbooks
* reconciliation and audit

Any implementation of `BUY` must conform to this specification unless an approved exception is explicitly documented.

### 1.3 Scope

This RFC applies to all booked `BUY` transactions that acquire exposure in financial instruments, including but not limited to:

* equities
* ETFs
* mutual funds
* fixed income / bonds
* money market instruments
* structured products
* other purchased securities or positions

This RFC covers:

* input contract
* validation
* enrichment
* policy resolution
* calculation
* position impact
* lot creation
* cash impact
* accrued-interest handling
* timing semantics
* linkage semantics
* query visibility
* observability
* test requirements

### 1.4 Out of Scope

This RFC does not define:

* pre-trade order capture
* pre-trade suitability decisioning
* order routing and execution management
* sell-side disposal logic
* cancel / correct / rebook flows
* corporate action transformations
* transfer processing not directly linked to the `BUY`
* external settlement messaging workflows beyond required integration fields

Where out-of-scope processes interact with `BUY`, only the required interfaces, identifiers, and linkage expectations are defined here.

---

## 2. Referenced Shared Standards

This RFC must be read together with the shared transaction-processing standards in the repository.

### 2.1 Foundational shared standards

The following shared documents are normative for `BUY` unless explicitly overridden here:

* `shared/01-document-governance.md`
* `shared/02-glossary.md`
* `shared/03-normative-rules-and-precedence.md`
* `shared/04-common-processing-lifecycle.md`
* `shared/05-common-validation-and-failure-semantics.md`
* `shared/06-common-calculation-conventions.md`
* `shared/07-accounting-cash-and-linkage.md`
* `shared/08-timing-semantics.md`
* `shared/09-idempotency-replay-and-reprocessing.md`
* `shared/10-query-audit-and-observability.md`
* `shared/11-test-strategy-and-gap-assessment.md`
* `shared/12-canonical-modeling-guidelines.md`

### 2.2 Override rule

This RFC defines all `BUY`-specific behavior.

If a shared document defines a generic rule and this RFC defines a `BUY`-specific specialization, the `BUY`-specific rule in this RFC takes precedence for `BUY` processing only.

---

## 3. BUY Business Definition

A `BUY` transaction represents the acquisition of additional units of an instrument by a portfolio.

A `BUY` must:

* increase exposure
* increase quantity
* create or increase cost basis
* create one or more acquisition lots
* create or link a corresponding cash outflow
* preserve sufficient information for accounting, performance, income, reporting, reconciliation, and audit

A `BUY` must not:

* create realized gain or realized loss
* be treated as earned income
* break holding continuity unless reopening from zero quantity
* create unlinked cash-side or ledger-side effects

### 3.1 Non-negotiable semantic invariant

A `BUY` acquires exposure, increases quantity, creates cost basis, creates settlement cash consumption, and must never realize profit or loss at booking.

### 3.2 Instrument-neutral rule

The same semantic model must apply across all supported instruments, with policy-driven variations for:

* fee handling
* accrued-interest handling
* timing
* cash-entry mode
* precision and reconciliation behavior

### 3.3 Fixed-income rule

For accrued-interest-bearing instruments:

* accrued interest paid must be captured explicitly
* accrued interest paid must not be treated as earned income
* accrued interest paid must initialize an accrued-income offset state
* the offset must remain available for future net-income calculations

---

## 4. BUY Semantic Invariants

The following invariants are mandatory for every valid `BUY`.

### 4.1 Semantic invariants

* A `BUY` must increase long exposure.
* A `BUY` must increase quantity by a positive amount.
* A `BUY` must create acquisition cost.
* A `BUY` must create settlement cash consumption.
* A `BUY` must create or reference at least one acquisition lot.
* A `BUY` must not create realized capital P&L.
* A `BUY` must not create realized FX P&L.
* A `BUY` must not be classified as income.
* A `BUY` must not consume an accrued-income offset.

### 4.2 Numeric invariants

* `quantity_delta > 0`
* `book_cost_local >= 0`
* `book_cost_base >= 0`
* `dirty_settlement_amount_local >= 0`
* `dirty_settlement_amount_base >= 0`
* realized capital P&L local = `0`
* realized FX P&L local = `0`
* realized total P&L local = `0`
* realized capital P&L base = `0`
* realized FX P&L base = `0`
* realized total P&L base = `0`

### 4.3 Linkage invariants

* Every `BUY` must have a stable `economic_event_id`.
* Every `BUY` must have a stable `linked_transaction_group_id`.
* If cash is auto-generated, the linked cash entry must exist.
* If cash is upstream-provided, the external cash expectation must be explicit and linkable.
* Security-side and cash-side effects must be reconcilable to the same economic event.

### 4.4 Audit invariants

* Every derived value must be reproducible from source data, linked data, and policy configuration.
* The active policy id and version must be identifiable for every processed `BUY`.
* Source-system identity and traceability must be preserved.

---

## 5. BUY Processing Flow

The engine must process a `BUY` in the following deterministic sequence.

### 5.1 Receive and ingest

The engine must:

* accept a raw `BUY` payload
* classify it as a `BUY`
* attach source-system metadata
* attach or generate required identifiers
* preserve raw payload lineage where platform policy requires it

### 5.2 Validate

The engine must validate:

* required fields
* field types
* enum values
* signs and ranges
* precision constraints
* policy-required fields
* linkage rules
* referential integrity rules
* reconciliation rules for supplied vs derived amounts

Validation outcomes must be explicit and deterministic.

### 5.3 Normalize and enrich

The engine must:

* normalize identifiers
* normalize currencies
* normalize enum values
* derive allowed values when policy permits
* populate policy defaults
* classify fields by source: `UPSTREAM`, `DERIVED`, `CONFIGURED`, `LINKED`, or `STATEFUL`

### 5.4 Resolve policy

The engine must resolve and attach:

* calculation policy id
* calculation policy version
* fee-capitalization policy
* accrued-interest treatment policy
* cash-entry mode
* timing policy
* precision policy
* duplicate/replay policy

No material calculation may proceed without an active, identifiable policy.

### 5.5 Calculate

The engine must perform calculations in canonical order:

1. determine principal
2. determine fee buckets
3. determine accrued-interest amounts
4. determine book cost
5. determine dirty settlement amount
6. convert relevant amounts to base currency
7. determine position deltas
8. determine lot effects
9. initialize accrued-income offset state
10. emit explicit zero realized P&L values
11. determine cashflow instruction or linked cash expectation

### 5.6 Create business effects

The engine must produce:

* position delta
* lot creation or update
* cashflow effect or linked cash instruction
* accrued-income offset state
* linkage state
* auditable derived values

### 5.7 Persist and publish

The engine must:

* persist the enriched transaction
* persist derived states
* publish downstream events where applicable
* make the transaction and derived state available to query/read-model consumers according to platform consistency guarantees

### 5.8 Support and traceability

The engine must:

* emit structured logs
* include correlation identifiers
* include economic-event linkage
* expose processing state
* expose failure reason if processing is incomplete

---

## 6. BUY Canonical Data Model

### 6.1 Top-level model

The canonical logical model must be `BuyTransaction`.

### 6.2 Required model composition

`BuyTransaction` must be composed of:

* `TransactionIdentity`
* `TransactionLifecycle`
* `InstrumentReference`
* `ExecutionDetails`
* `SettlementDetails`
* `QuantityDetails`
* `PriceDetails`
* `PrincipalAmountDetails`
* `FeeDetails`
* `AccruedInterestDetails`
* `FxDetails`
* `ClassificationDetails`
* `PositionEffect`
* `CostBasisEffect`
* `RealizedPnlDetails`
* `CashflowInstruction`
* `LinkageDetails`
* `AuditMetadata`
* `AdvisoryMetadata`
* `PolicyMetadata`

### 6.3 Source classification requirement

Each field in the logical model must be classifiable as one of:

* `UPSTREAM`
* `DERIVED`
* `CONFIGURED`
* `LINKED`
* `STATEFUL`

### 6.4 Mutability classification requirement

Each field must have one of the following mutability classifications:

* `IMMUTABLE`
* `DERIVED_ONCE`
* `RECOMPUTED`
* `STATEFUL_BALANCE`

### 6.5 Required field groups and attributes

#### 6.5.1 TransactionIdentity

| Field                         | Type              | Required | Source             | Mutability | Description                                                                   | Sample            |
| ----------------------------- | ----------------- | -------: | ------------------ | ---------- | ----------------------------------------------------------------------------- | ----------------- |
| `transaction_id`              | `str`             |      Yes | UPSTREAM / DERIVED | IMMUTABLE  | Unique identifier of this transaction record                                  | `TXN-2026-000123` |
| `economic_event_id`           | `str`             |      Yes | DERIVED            | IMMUTABLE  | Shared identifier for all linked entries representing the same economic event | `EVT-2026-00987`  |
| `linked_transaction_group_id` | `str`             |      Yes | DERIVED            | IMMUTABLE  | Groups related entries such as the `BUY` and linked cash entry                | `LTG-2026-00456`  |
| `transaction_type`            | `TransactionType` |      Yes | UPSTREAM           | IMMUTABLE  | Canonical transaction type enum                                               | `BUY`             |

#### 6.5.2 TransactionLifecycle

| Field               | Type               | Required | Source                | Mutability | Description                    | Sample                 |
| ------------------- | ------------------ | -------: | --------------------- | ---------- | ------------------------------ | ---------------------- |
| `trade_date`        | `date`             |      Yes | UPSTREAM              | IMMUTABLE  | Trade execution date           | `2026-02-28`           |
| `trade_timestamp`   | `datetime`         |       No | UPSTREAM              | IMMUTABLE  | Exact execution timestamp      | `2026-02-28T10:15:30Z` |
| `settlement_date`   | `date`             |      Yes | UPSTREAM              | IMMUTABLE  | Contractual settlement date    | `2026-03-03`           |
| `booking_date`      | `date \| None`     |       No | UPSTREAM / CONFIGURED | IMMUTABLE  | Accounting booking date        | `2026-02-28`           |
| `value_date`        | `date \| None`     |       No | UPSTREAM / CONFIGURED | IMMUTABLE  | Value date for ledger purposes | `2026-03-03`           |
| `trade_status`      | `TradeStatus`      |      Yes | UPSTREAM / CONFIGURED | RECOMPUTED | Processing state of the trade  | `BOOKED`               |
| `settlement_status` | `SettlementStatus` |      Yes | DERIVED / CONFIGURED  | RECOMPUTED | Settlement lifecycle status    | `PENDING`              |

#### 6.5.3 InstrumentReference

| Field                 | Type                | Required | Source               | Mutability | Description                                                 | Sample         |
| --------------------- | ------------------- | -------: | -------------------- | ---------- | ----------------------------------------------------------- | -------------- |
| `portfolio_id`        | `str`               |      Yes | UPSTREAM             | IMMUTABLE  | Portfolio receiving the purchased instrument                | `PORT-10001`   |
| `instrument_id`       | `str`               |      Yes | UPSTREAM             | IMMUTABLE  | Canonical instrument identifier                             | `AAPL`         |
| `security_id`         | `str`               |      Yes | UPSTREAM             | IMMUTABLE  | Security master identifier                                  | `US0378331005` |
| `instrument_type`     | `InstrumentType`    |      Yes | UPSTREAM / DERIVED   | IMMUTABLE  | Instrument type used for behavior and reporting             | `EQUITY`       |
| `income_bearing_type` | `IncomeBearingType` |      Yes | DERIVED / CONFIGURED | IMMUTABLE  | Whether the instrument accrues income between payment dates | `NON_ACCRUED`  |

#### 6.5.4 ExecutionDetails

| Field             | Type          | Required | Source   | Mutability | Description                              | Sample       |
| ----------------- | ------------- | -------: | -------- | ---------- | ---------------------------------------- | ------------ |
| `execution_venue` | `str \| None` |       No | UPSTREAM | IMMUTABLE  | Venue where the transaction was executed | `NASDAQ`     |
| `broker_id`       | `str \| None` |       No | UPSTREAM | IMMUTABLE  | Executing broker reference               | `BROKER-001` |
| `counterparty_id` | `str \| None` |       No | UPSTREAM | IMMUTABLE  | Counterparty identifier if relevant      | `CP-12345`   |
| `order_id`        | `str \| None` |       No | UPSTREAM | IMMUTABLE  | Upstream order reference                 | `ORD-778899` |
| `fill_id`         | `str \| None` |       No | UPSTREAM | IMMUTABLE  | Execution fill reference                 | `FILL-001`   |

#### 6.5.5 SettlementDetails

| Field                         | Type              | Required | Source                | Mutability | Description                                       | Sample            |
| ----------------------------- | ----------------- | -------: | --------------------- | ---------- | ------------------------------------------------- | ----------------- |
| `position_effective_timing`   | `EffectiveTiming` |      Yes | CONFIGURED            | IMMUTABLE  | When the position becomes economically effective  | `TRADE_DATE`      |
| `cash_effective_timing`       | `EffectiveTiming` |      Yes | CONFIGURED            | IMMUTABLE  | When cash is reduced for ledger purposes          | `SETTLEMENT_DATE` |
| `performance_cashflow_timing` | `EffectiveTiming` |      Yes | CONFIGURED            | IMMUTABLE  | When performance views recognize the BUY cashflow | `TRADE_DATE`      |
| `settlement_currency`         | `str`             |      Yes | UPSTREAM / CONFIGURED | IMMUTABLE  | Currency in which settlement occurs               | `USD`             |
| `cash_account_id`             | `str \| None`     |       No | UPSTREAM              | IMMUTABLE  | Cash account affected by the purchase             | `CASH-USD-01`     |

#### 6.5.6 QuantityDetails

| Field                | Type      | Required | Source     | Mutability | Description                                         | Sample |
| -------------------- | --------- | -------: | ---------- | ---------- | --------------------------------------------------- | ------ |
| `quantity`           | `Decimal` |      Yes | UPSTREAM   | IMMUTABLE  | Executed buy quantity                               | `100`  |
| `quantity_precision` | `int`     |      Yes | CONFIGURED | IMMUTABLE  | Allowed decimal precision for quantity              | `6`    |
| `settled_quantity`   | `Decimal` |      Yes | DERIVED    | RECOMPUTED | Quantity already settled at current lifecycle point | `0`    |
| `unsettled_quantity` | `Decimal` |      Yes | DERIVED    | RECOMPUTED | Quantity pending settlement                         | `100`  |

#### 6.5.7 PriceDetails

| Field             | Type              | Required | Source             | Mutability | Description                                         | Sample    |
| ----------------- | ----------------- | -------: | ------------------ | ---------- | --------------------------------------------------- | --------- |
| `execution_price` | `Decimal`         |      Yes | UPSTREAM           | IMMUTABLE  | Executed unit price                                 | `150.00`  |
| `clean_price`     | `Decimal \| None` |       No | UPSTREAM           | IMMUTABLE  | Clean price, primarily for fixed-income instruments | `98.0000` |
| `dirty_price`     | `Decimal \| None` |       No | UPSTREAM / DERIVED | RECOMPUTED | Dirty price including accrued interest component    | `99.2500` |
| `price_precision` | `int`             |      Yes | CONFIGURED         | IMMUTABLE  | Allowed decimal precision for price                 | `8`       |

#### 6.5.8 PrincipalAmountDetails

| Field                           | Type      | Required | Source             | Mutability   | Description                                             | Sample     |
| ------------------------------- | --------- | -------: | ------------------ | ------------ | ------------------------------------------------------- | ---------- |
| `gross_principal_local`         | `Decimal` |      Yes | UPSTREAM / DERIVED | DERIVED_ONCE | Principal trade amount before fees and accrued interest | `15000.00` |
| `gross_principal_base`          | `Decimal` |      Yes | DERIVED            | DERIVED_ONCE | Principal trade amount converted to base currency       | `15000.00` |
| `book_cost_local`               | `Decimal` |      Yes | DERIVED            | DERIVED_ONCE | Cost basis amount in trade currency                     | `15005.00` |
| `book_cost_base`                | `Decimal` |      Yes | DERIVED            | DERIVED_ONCE | Cost basis amount in base currency                      | `15005.00` |
| `dirty_settlement_amount_local` | `Decimal` |      Yes | DERIVED            | DERIVED_ONCE | Total settlement cash required in trade currency        | `15005.00` |
| `dirty_settlement_amount_base`  | `Decimal` |      Yes | DERIVED            | DERIVED_ONCE | Total settlement cash required in base currency         | `15005.00` |

#### 6.5.9 FeeDetails

| Field                    | Type      | Required | Source   | Mutability   | Description                                           | Sample |
| ------------------------ | --------- | -------: | -------- | ------------ | ----------------------------------------------------- | ------ |
| `brokerage_fee_local`    | `Decimal` |      Yes | UPSTREAM | IMMUTABLE    | Brokerage fee in trade currency                       | `5.00` |
| `exchange_fee_local`     | `Decimal` |      Yes | UPSTREAM | IMMUTABLE    | Exchange fee in trade currency                        | `0.50` |
| `stamp_duty_local`       | `Decimal` |      Yes | UPSTREAM | IMMUTABLE    | Stamp duty in trade currency                          | `0.00` |
| `tax_fee_local`          | `Decimal` |      Yes | UPSTREAM | IMMUTABLE    | Tax-related fee in trade currency                     | `0.00` |
| `other_fee_local`        | `Decimal` |      Yes | UPSTREAM | IMMUTABLE    | Other settlement-related fee in trade currency        | `0.00` |
| `capitalized_fees_local` | `Decimal` |      Yes | DERIVED  | DERIVED_ONCE | Sum of fee components capitalized into cost basis     | `5.50` |
| `capitalized_fees_base`  | `Decimal` |      Yes | DERIVED  | DERIVED_ONCE | Base-currency equivalent of capitalized fees          | `5.50` |
| `expensed_fees_local`    | `Decimal` |      Yes | DERIVED  | DERIVED_ONCE | Sum of fee components not capitalized into cost basis | `0.00` |
| `expensed_fees_base`     | `Decimal` |      Yes | DERIVED  | DERIVED_ONCE | Base-currency equivalent of expensed fees             | `0.00` |

#### 6.5.10 AccruedInterestDetails

| Field                                   | Type           | Required | Source             | Mutability       | Description                                                            | Sample       |
| --------------------------------------- | -------------- | -------: | ------------------ | ---------------- | ---------------------------------------------------------------------- | ------------ |
| `accrued_interest_paid_local`           | `Decimal`      |      Yes | UPSTREAM / DERIVED | DERIVED_ONCE     | Accrued interest paid to seller                                        | `1250.00`    |
| `accrued_interest_paid_base`            | `Decimal`      |      Yes | DERIVED            | DERIVED_ONCE     | Base-currency equivalent of accrued interest paid                      | `1250.00`    |
| `accrued_income_offset_remaining_local` | `Decimal`      |      Yes | DERIVED            | STATEFUL_BALANCE | Remaining accrued-interest offset to apply against future gross income | `1250.00`    |
| `accrued_income_offset_remaining_base`  | `Decimal`      |      Yes | DERIVED            | STATEFUL_BALANCE | Base-currency equivalent of remaining income offset                    | `1250.00`    |
| `accrual_start_date`                    | `date \| None` |       No | UPSTREAM           | IMMUTABLE        | Start date of accrual period                                           | `2026-01-15` |
| `accrual_end_date`                      | `date \| None` |       No | UPSTREAM           | IMMUTABLE        | End date used to compute accrued interest paid                         | `2026-02-28` |

#### 6.5.11 FxDetails

| Field                     | Type              | Required | Source                | Mutability | Description                                       | Sample     |
| ------------------------- | ----------------- | -------: | --------------------- | ---------- | ------------------------------------------------- | ---------- |
| `trade_currency`          | `str`             |      Yes | UPSTREAM              | IMMUTABLE  | Currency in which the trade is priced             | `USD`      |
| `portfolio_base_currency` | `str`             |      Yes | UPSTREAM / CONFIGURED | IMMUTABLE  | Portfolio reporting base currency                 | `USD`      |
| `trade_fx_rate`           | `Decimal`         |      Yes | UPSTREAM / CONFIGURED | IMMUTABLE  | FX rate from trade currency to base currency      | `1.000000` |
| `settlement_fx_rate`      | `Decimal \| None` |       No | UPSTREAM / CONFIGURED | IMMUTABLE  | FX rate used for settlement currency if different | `1.000000` |
| `fx_rate_source`          | `str \| None`     |       No | UPSTREAM / CONFIGURED | IMMUTABLE  | Source of FX rate used                            | `WMR_4PM`  |

#### 6.5.12 ClassificationDetails

| Field                        | Type                        | Required | Source               | Mutability | Description                                         | Sample               |
| ---------------------------- | --------------------------- | -------: | -------------------- | ---------- | --------------------------------------------------- | -------------------- |
| `transaction_classification` | `TransactionClassification` |      Yes | DERIVED / CONFIGURED | IMMUTABLE  | High-level classification of the transaction        | `INVESTMENT`         |
| `cashflow_classification`    | `CashflowClassification`    |      Yes | DERIVED / CONFIGURED | IMMUTABLE  | Classification of the cash movement                 | `INVESTMENT_OUTFLOW` |
| `income_classification`      | `IncomeClassification`      |      Yes | DERIVED / CONFIGURED | IMMUTABLE  | Income classification applicable to the transaction | `NONE`               |

#### 6.5.13 PositionEffect

| Field                     | Type      | Required | Source  | Mutability   | Description                                                       | Sample       |
| ------------------------- | --------- | -------: | ------- | ------------ | ----------------------------------------------------------------- | ------------ |
| `position_quantity_delta` | `Decimal` |      Yes | DERIVED | DERIVED_ONCE | Quantity change caused by the `BUY`                               | `100`        |
| `cost_basis_delta_local`  | `Decimal` |      Yes | DERIVED | DERIVED_ONCE | Cost basis change in trade currency                               | `15005.00`   |
| `cost_basis_delta_base`   | `Decimal` |      Yes | DERIVED | DERIVED_ONCE | Cost basis change in base currency                                | `15005.00`   |
| `held_since_date`         | `date`    |      Yes | DERIVED | RECOMPUTED   | Current holding-period start date after applying this transaction | `2026-02-28` |

#### 6.5.14 CostBasisEffect

| Field                 | Type              | Required | Source     | Mutability   | Description                                       | Sample         |
| --------------------- | ----------------- | -------: | ---------- | ------------ | ------------------------------------------------- | -------------- |
| `cost_basis_method`   | `CostBasisMethod` |      Yes | CONFIGURED | IMMUTABLE    | Cost-basis methodology applicable to the position | `FIFO`         |
| `lot_id`              | `str`             |      Yes | DERIVED    | DERIVED_ONCE | Identifier of created lot                         | `LOT-2026-001` |
| `lot_book_cost_local` | `Decimal`         |      Yes | DERIVED    | DERIVED_ONCE | Book cost assigned to the lot in trade currency   | `15005.00`     |
| `lot_book_cost_base`  | `Decimal`         |      Yes | DERIVED    | DERIVED_ONCE | Book cost assigned to the lot in base currency    | `15005.00`     |

#### 6.5.15 RealizedPnlDetails

| Field                        | Type      | Required | Source  | Mutability   | Description                            | Sample |
| ---------------------------- | --------- | -------: | ------- | ------------ | -------------------------------------- | ------ |
| `realized_capital_pnl_local` | `Decimal` |      Yes | DERIVED | DERIVED_ONCE | Realized capital P&L in trade currency | `0.00` |
| `realized_fx_pnl_local`      | `Decimal` |      Yes | DERIVED | DERIVED_ONCE | Realized FX P&L in trade currency      | `0.00` |
| `realized_total_pnl_local`   | `Decimal` |      Yes | DERIVED | DERIVED_ONCE | Total realized P&L in trade currency   | `0.00` |
| `realized_capital_pnl_base`  | `Decimal` |      Yes | DERIVED | DERIVED_ONCE | Realized capital P&L in base currency  | `0.00` |
| `realized_fx_pnl_base`       | `Decimal` |      Yes | DERIVED | DERIVED_ONCE | Realized FX P&L in base currency       | `0.00` |
| `realized_total_pnl_base`    | `Decimal` |      Yes | DERIVED | DERIVED_ONCE | Total realized P&L in base currency    | `0.00` |

#### 6.5.16 CashflowInstruction

| Field                           | Type            | Required | Source               | Mutability   | Description                                                      | Sample                 |
| ------------------------------- | --------------- | -------: | -------------------- | ------------ | ---------------------------------------------------------------- | ---------------------- |
| `cash_entry_mode`               | `CashEntryMode` |      Yes | CONFIGURED           | IMMUTABLE    | Whether cash entry is engine-generated or expected from upstream | `AUTO_GENERATE`        |
| `auto_generate_cash_entry`      | `bool`          |      Yes | DERIVED / CONFIGURED | IMMUTABLE    | Whether the engine must generate the linked cash entry           | `true`                 |
| `linked_cash_transaction_id`    | `str \| None`   |       No | LINKED / DERIVED     | RECOMPUTED   | Linked cash transaction identifier                               | `TXN-CASH-2026-000123` |
| `settlement_cash_outflow_local` | `Decimal`       |      Yes | DERIVED              | DERIVED_ONCE | Cash to be removed from cash balance in trade currency           | `15005.00`             |
| `settlement_cash_outflow_base`  | `Decimal`       |      Yes | DERIVED              | DERIVED_ONCE | Cash to be removed from cash balance in base currency            | `15005.00`             |

#### 6.5.17 LinkageDetails

| Field                        | Type          | Required | Source               | Mutability | Description                                               | Sample             |
| ---------------------------- | ------------- | -------: | -------------------- | ---------- | --------------------------------------------------------- | ------------------ |
| `originating_transaction_id` | `str \| None` |       No | LINKED               | IMMUTABLE  | Source transaction for linked entries                     | `TXN-2026-000123`  |
| `link_type`                  | `LinkType`    |      Yes | DERIVED / CONFIGURED | IMMUTABLE  | Semantic meaning of the transaction linkage               | `SECURITY_TO_CASH` |
| `reconciliation_key`         | `str \| None` |       No | UPSTREAM / DERIVED   | IMMUTABLE  | Key used to reconcile with upstream or accounting systems | `RECON-ABC-123`    |

#### 6.5.18 AuditMetadata

| Field                | Type               | Required | Source             | Mutability | Description                             | Sample                 |
| -------------------- | ------------------ | -------: | ------------------ | ---------- | --------------------------------------- | ---------------------- |
| `source_system`      | `str`              |      Yes | UPSTREAM           | IMMUTABLE  | Originating system name                 | `ADVISORY_PLATFORM`    |
| `external_reference` | `str \| None`      |       No | UPSTREAM           | IMMUTABLE  | Upstream external reference             | `EXT-998877`           |
| `booking_center`     | `str \| None`      |       No | UPSTREAM           | IMMUTABLE  | Booking center / legal booking location | `SGPB`                 |
| `created_at`         | `datetime`         |      Yes | UPSTREAM / DERIVED | IMMUTABLE  | Record creation timestamp               | `2026-02-28T10:16:00Z` |
| `processed_at`       | `datetime \| None` |       No | DERIVED            | RECOMPUTED | Processing completion timestamp         | `2026-02-28T10:16:02Z` |

#### 6.5.19 AdvisoryMetadata

| Field                   | Type          | Required | Source   | Mutability | Description                               | Sample           |
| ----------------------- | ------------- | -------: | -------- | ---------- | ----------------------------------------- | ---------------- |
| `advisor_id`            | `str \| None` |       No | UPSTREAM | IMMUTABLE  | Relationship manager / advisor reference  | `RM-1001`        |
| `client_instruction_id` | `str \| None` |       No | UPSTREAM | IMMUTABLE  | Client instruction reference              | `CI-2026-7788`   |
| `suitability_reference` | `str \| None` |       No | UPSTREAM | IMMUTABLE  | Suitability assessment reference          | `SUT-2026-4545`  |
| `mandate_reference`     | `str \| None` |       No | UPSTREAM | IMMUTABLE  | Discretionary or advisory mandate linkage | `DPM-MANDATE-01` |

#### 6.5.20 PolicyMetadata

| Field                               | Type  | Required | Source     | Mutability | Description                                         | Sample                                              |
| ----------------------------------- | ----- | -------: | ---------- | ---------- | --------------------------------------------------- | --------------------------------------------------- |
| `calculation_policy_id`             | `str` |      Yes | CONFIGURED | IMMUTABLE  | Policy identifier used for this calculation         | `POLICY-BUY-STD`                                    |
| `calculation_policy_version`        | `str` |      Yes | CONFIGURED | IMMUTABLE  | Version of the calculation policy applied           | `1.0.0`                                             |
| `fee_capitalization_policy`         | `str` |      Yes | CONFIGURED | IMMUTABLE  | Policy controlling capitalization of fee components | `DEFAULT_CAP_ALL_DIRECT_FEES`                       |
| `accrued_interest_treatment_policy` | `str` |      Yes | CONFIGURED | IMMUTABLE  | Policy controlling accrued-interest treatment       | `EXCLUDE_FROM_BOOK_COST_OFFSET_AGAINST_NEXT_INCOME` |
| `cash_generation_policy`            | `str` |      Yes | CONFIGURED | IMMUTABLE  | Policy controlling how cash entries are created     | `AUTO_GENERATE_LINKED_CASH`                         |

---

## 7. BUY Validation Rules

### 7.1 Mandatory required-field validation

A valid `BUY` must include, at minimum:

* transaction identity
* transaction type
* trade date
* settlement date
* portfolio identifier
* instrument identifier
* quantity
* execution price or reconcilable principal amount
* trade currency
* portfolio base currency
* applicable FX rate
* required policy identifiers if not resolved externally

### 7.2 Numeric validation

The engine must enforce:

* `quantity > 0`
* `execution_price >= 0`
* `gross_principal_local >= 0`
* all fee amounts `>= 0`
* `accrued_interest_paid_local >= 0`
* `trade_fx_rate > 0`
* `settlement_fx_rate > 0` when present
* all numeric fields must be decimal-safe
* all numeric fields must satisfy configured precision rules

### 7.3 Reconciliation validation

If both supplied and derived principal values are available:

* the engine must reconcile them
* tolerance must be policy-driven
* out-of-tolerance mismatches must fail or park according to policy

### 7.4 Enum validation

The engine must validate all enum-constrained fields, including:

* transaction type
* transaction classification
* cashflow classification
* income classification
* timing values
* trade status
* settlement status
* cash-entry mode
* link type

### 7.5 Referential validation

The engine must validate, where required:

* portfolio reference exists
* instrument reference exists
* cash account reference exists when explicit account linkage is required
* linked transaction identifiers are valid when separate cash-entry mode is used

### 7.6 Validation outcomes

Each validation failure must resolve to one of:

* `HARD_REJECT`
* `PARK_PENDING_REMEDIATION`
* `ACCEPT_WITH_WARNING`
* `RETRYABLE_FAILURE`
* `TERMINAL_FAILURE`

The applicable outcome must be deterministic and policy-driven.

### 7.7 BUY-specific hard-fail conditions

The following must hard-fail unless explicitly configured otherwise:

* zero quantity
* negative quantity
* missing settlement date
* missing instrument identifier
* missing portfolio identifier
* invalid transaction type
* cross-currency `BUY` with missing required FX rate
* negative accrued interest
* negative fee component
* policy conflict affecting a material calculation

---

## 8. BUY Calculation Rules and Formulas

### 8.1 Input values

The engine must support calculation from the following normalized inputs:

* quantity
* execution price
* clean price where relevant
* dirty price where relevant
* gross principal supplied value where present
* fee components
* accrued interest paid
* trade currency
* settlement currency where relevant
* portfolio base currency
* trade FX rate
* settlement FX rate where relevant

### 8.2 Derived values

The engine must derive, at minimum:

* `gross_principal_local`
* `gross_principal_base`
* `capitalized_fees_local`
* `capitalized_fees_base`
* `expensed_fees_local`
* `expensed_fees_base`
* `book_cost_local`
* `book_cost_base`
* `dirty_settlement_amount_local`
* `dirty_settlement_amount_base`
* `accrued_interest_paid_base`
* `accrued_income_offset_remaining_local`
* `accrued_income_offset_remaining_base`
* explicit realized P&L zero values
* position deltas
* lot cost values
* settlement cash instruction values

### 8.3 Canonical formula order

The engine must calculate in this exact order:

1. determine `gross_principal_local`
2. determine fee components and classify them as capitalized or expensed
3. determine `accrued_interest_paid_local`
4. determine `book_cost_local`
5. determine `dirty_settlement_amount_local`
6. convert required values into base currency
7. determine position and lot deltas
8. initialize accrued-income offset state
9. emit explicit zero realized P&L fields
10. determine linked cash behavior

### 8.4 Principal calculation

If `gross_principal_local` is not explicitly supplied, it must be derived as:

`gross_principal_local = quantity × execution_price`

If `gross_principal_local` is supplied, it must reconcile with the derived value within configured tolerance.

### 8.5 Fee bucket calculation

The engine must separate fees into:

* capitalized fees
* expensed fees

The classification of each fee component must be policy-driven.

### 8.6 Book cost calculation

By default:

`book_cost_local = gross_principal_local + capitalized_fees_local`

If policy includes accrued interest in cost basis, then:

`book_cost_local = gross_principal_local + capitalized_fees_local + accrued_interest_paid_local`

The chosen behavior must be explicitly governed by the active accrued-interest treatment policy.

### 8.7 Dirty settlement amount calculation

By default:

`dirty_settlement_amount_local = gross_principal_local + all settlement-related fees + accrued_interest_paid_local`

This amount represents the total settlement cash consumed by the economic event.

### 8.8 Base-currency conversion

The engine must convert all relevant local amounts to base currency using the active FX policy.

By default:

`amount_base = amount_local × applicable_fx_rate`

The FX source, precision, and rounding behavior must be policy-driven and traceable.

### 8.9 Accrued-income offset initialization

For eligible accrued-interest-bearing `BUY` transactions:

* `accrued_income_offset_remaining_local` must initialize to the amount of accrued interest paid that is recoverable under policy
* `accrued_income_offset_remaining_base` must initialize to its base-currency equivalent

If the instrument is not accrual-bearing, the offset must initialize to zero.

### 8.10 Realized P&L fields

For every `BUY`, the engine must explicitly produce:

* realized capital P&L local = `0`
* realized FX P&L local = `0`
* realized total P&L local = `0`
* realized capital P&L base = `0`
* realized FX P&L base = `0`
* realized total P&L base = `0`

These fields must be present and must not be omitted.

### 8.11 Rounding and precision

The engine must define:

* internal calculation precision
* rounding scale per amount type
* rounding mode
* presentation scale
* FX conversion rounding rules
* reconciliation tolerance rules

Rounding must be applied only at defined calculation boundaries and must not vary by implementation.

---

## 9. BUY Position Rules

### 9.1 Quantity effect

A `BUY` must increase position quantity by the executed quantity.

`new_quantity = old_quantity + quantity`

### 9.2 Position opening rule

If the pre-transaction position quantity is zero, the `BUY` must open a new long position.

### 9.3 Position increase rule

If the pre-transaction position quantity is already positive, the `BUY` must increase that long position.

### 9.4 Settled vs unsettled quantity

The engine must support both:

* `settled_quantity`
* `unsettled_quantity`

Behavior must depend on `position_effective_timing` and settlement lifecycle state.

### 9.5 Cost-basis effect

A `BUY` must increase position cost basis by:

* `book_cost_local`
* `book_cost_base`

### 9.6 Held-since behavior

* If pre-transaction quantity is zero, `held_since_date = trade_date`.
* If pre-transaction quantity is already positive, `held_since_date` must remain unchanged.
* If the position previously went to zero and is reopened by this `BUY`, the new `BUY` starts a new holding period.

### 9.7 Position rule invariants

* Position quantity must increase.
* Cost basis must increase by the defined cost-basis delta.
* A `BUY` must not create realized P&L on the position.

---

## 10. BUY Lot Rules

### 10.1 Lot creation

Every valid `BUY` must create one or more acquisition lots.

### 10.2 Required lot behavior

Each lot must contain:

* lot identifier
* source transaction reference
* acquisition date
* acquired quantity
* open quantity
* lot book cost local
* lot book cost base
* capitalized fee components
* accrued interest paid
* FX context
* policy context

### 10.3 Lot quantity initialization

By default:

* `lot_acquired_quantity = quantity`
* `lot_open_quantity = quantity`

### 10.4 Lot cost assignment

By default:

* `lot_book_cost_local = book_cost_local`
* `lot_book_cost_base = book_cost_base`

### 10.5 Accrued-interest storage on lot

By default:

* accrued interest paid must be stored separately on the lot
* accrued interest paid must not inflate principal cost unless policy explicitly says so

### 10.6 Methodology compatibility

The lot model must support:

* FIFO
* average-cost pooling
* specific-lot identification at the schema level

### 10.7 Lot traceability

Every lot must remain traceable to:

* source transaction id
* economic event id
* policy id and version

---

## 11. BUY Cash and Dual-Accounting Rules

### 11.1 Core cash rule

A `BUY` must reduce cash.

### 11.2 Required cash concepts

The engine must support:

* book investment amount
* settlement cash amount

These amounts may differ depending on accrued-interest and fee policy.

### 11.3 Settlement cash rule

By default:

`settlement_cash_outflow_local = dirty_settlement_amount_local`

`settlement_cash_outflow_base = dirty_settlement_amount_base`

### 11.4 Cash-entry modes

The system must support both:

* `AUTO_GENERATE`
* `UPSTREAM_PROVIDED`

### 11.5 Auto-generated cash mode

If `cash_entry_mode = AUTO_GENERATE`:

* the engine must create a linked cash entry
* the linked cash entry must reduce cash balance
* the entry must be linked to the originating `BUY`

### 11.6 Upstream-provided cash mode

If `cash_entry_mode = UPSTREAM_PROVIDED`:

* the engine must not generate a duplicate cash entry
* the engine must accept a separate upstream cash transaction
* the engine must link that cash transaction to the `BUY`

### 11.7 Required linkage fields

Security-side and cash-side entries must be linkable through:

* `economic_event_id`
* `linked_transaction_group_id`
* `originating_transaction_id`
* `linked_cash_transaction_id`
* `link_type`
* `reconciliation_key` where applicable

### 11.8 Cash balance views

The platform must distinguish, where relevant:

* available cash
* settled cash
* projected cash
* ledger cash

### 11.9 Cash invariants

* A `BUY` cash effect must always be linked or explicitly externally expected.
* Duplicate cash creation must be prevented.
* Cash-side and security-side effects must reconcile to the same economic event.

---

## 12. BUY Accrued-Interest Offset Rules

### 12.1 Core rule

Accrued interest paid on a `BUY` must not be treated as earned income.

### 12.2 Required storage

The engine must store:

* accrued interest paid local
* accrued interest paid base
* accrued-income offset remaining local
* accrued-income offset remaining base

### 12.3 Offset initialization

For eligible accrued-interest-bearing instruments:

* initialize the accrued-income offset on the `BUY`
* initialize the offset at the recoverable amount defined by policy

### 12.4 Offset persistence

The offset must remain available until:

* fully consumed by future eligible income events
* explicitly adjusted by a later lifecycle event under approved rules

### 12.5 Offset consumption requirement

Subsequent eligible income events must be able to use this offset to calculate:

* gross income
* offset applied
* net income

### 12.6 Partial consumption

The engine must support partial offset consumption.

### 12.7 Full consumption

The engine must support full offset consumption and a resulting zero remaining balance.

### 12.8 Scope rule

Default implementation must treat the offset as:

* lot-level for lifecycle accuracy
* instrument-level aggregatable for reporting

### 12.9 Offset invariants

* The offset must be auditable.
* The offset must be traceable to the originating `BUY`.
* The offset must never be confused with realized income.

---

## 13. BUY Timing Rules

### 13.1 Timing dimensions

The engine must support these timing dimensions independently:

* position timing
* cash timing
* performance timing
* reporting timing

### 13.2 Supported timing values

Supported values must include:

* `TRADE_DATE`
* `SETTLEMENT_DATE`

### 13.3 Trade-date economic effect

If position timing is `TRADE_DATE`:

* exposure becomes economically visible on trade date
* quantity may be reflected as unsettled until settlement

### 13.4 Settlement-date legal effect

If settlement timing is `SETTLEMENT_DATE`:

* legal settlement occurs on settlement date
* unsettled quantity transitions to settled quantity on settlement date
* cash is reduced for settlement-ledger purposes on settlement date unless configured otherwise

### 13.5 Cash timing

If cash timing is `TRADE_DATE`:

* cash may be reserved / committed on trade date

If cash timing is `SETTLEMENT_DATE`:

* actual ledger cash movement occurs on settlement date

### 13.6 Performance timing

The system must support performance recognition under the configured performance timing policy.

### 13.7 Timing invariants

* Timing behavior must be policy-driven, explicit, and auditable.
* Different timing modes must not produce silent inconsistencies between position, cash, and reporting views.

---

## 14. BUY Query / Output Contract

### 14.1 Required query surfaces

After successful processing, the platform must expose:

* enriched transaction view
* position view
* lot view
* cash linkage view
* accrued-income-offset view
* audit view

### 14.2 Required transaction output fields

At minimum, downstream consumers must be able to retrieve:

* canonical transaction identifiers
* core business fields
* derived cost fields
* classification fields
* timing fields
* policy metadata
* explicit realized P&L structure
* linkage fields

### 14.3 Required position output fields

At minimum:

* quantity
* settled quantity
* unsettled quantity
* cost basis local
* cost basis base
* held-since date

### 14.4 Required lot output fields

At minimum:

* lot id
* source transaction id
* acquisition date
* acquired quantity
* open quantity
* lot cost
* accrued-interest data
* policy and FX context

### 14.5 Required offset output fields

At minimum:

* accrued interest paid
* remaining accrued-income offset
* link to source `BUY`

### 14.6 Consistency expectation

The platform must define whether these surfaces are:

* synchronous
* eventually consistent

and must document the expected latency/SLA for visibility.

---

## 15. BUY Worked Examples

### 15.1 Example A: Same-currency equity BUY

#### Inputs

* instrument type: `EQUITY`
* quantity: `100`
* execution price: `150.00`
* gross principal supplied: not supplied
* brokerage fee: `5.00`
* exchange fee: `0.50`
* other fees: `0.00`
* accrued interest paid: `0.00`
* trade currency: `USD`
* portfolio base currency: `USD`
* trade FX rate: `1.000000`
* cash entry mode: `AUTO_GENERATE`
* accrued-interest policy: `EXCLUDE_FROM_BOOK_COST_OFFSET_AGAINST_NEXT_INCOME`

#### Derivations

* `gross_principal_local = 100 × 150.00 = 15000.00`
* `capitalized_fees_local = 5.00 + 0.50 = 5.50`
* `expensed_fees_local = 0.00`
* `book_cost_local = 15000.00 + 5.50 = 15005.50`
* `dirty_settlement_amount_local = 15000.00 + 5.50 + 0.00 = 15005.50`
* `gross_principal_base = 15000.00`
* `book_cost_base = 15005.50`
* `dirty_settlement_amount_base = 15005.50`
* realized P&L fields = `0.00`

#### Expected outputs

* position quantity increases by `100`
* cost basis increases by `15005.50`
* one acquisition lot is created
* linked cash entry is auto-generated for `15005.50`
* `held_since_date = trade_date` if opening from zero

#### Invariants checked

* positive quantity delta
* zero realized capital P&L
* zero realized FX P&L
* not classified as income

---

### 15.2 Example B: Cross-currency equity BUY

#### Inputs

* instrument type: `EQUITY`
* quantity: `100`
* execution price: `150.00`
* fees total local: `5.50`
* accrued interest paid: `0.00`
* trade currency: `USD`
* portfolio base currency: `SGD`
* trade FX rate: `1.350000`

#### Derivations

* `gross_principal_local = 15000.00`
* `book_cost_local = 15005.50`
* `dirty_settlement_amount_local = 15005.50`
* `gross_principal_base = 15000.00 × 1.35 = 20250.00`
* `book_cost_base = 15005.50 × 1.35 = 20257.425`
* `dirty_settlement_amount_base = 15005.50 × 1.35 = 20257.425`

#### Expected outputs

* position quantity increases by `100`
* local and base cost basis are both populated
* realized capital and FX P&L remain zero
* cash effect remains linked and traceable

---

### 15.3 Example C: Bond BUY with accrued interest

#### Inputs

* instrument type: `BOND`
* quantity: `100`
* clean-price-derived gross principal local: `98000.00`
* capitalized fees local: `40.00`
* accrued interest paid local: `1250.00`
* trade currency: `USD`
* base currency: `USD`
* trade FX rate: `1.000000`
* accrued-interest policy: `EXCLUDE_FROM_BOOK_COST_OFFSET_AGAINST_NEXT_INCOME`

#### Derivations

* `book_cost_local = 98000.00 + 40.00 = 98040.00`
* `dirty_settlement_amount_local = 98000.00 + 40.00 + 1250.00 = 99290.00`
* `accrued_income_offset_remaining_local = 1250.00`
* `book_cost_base = 98040.00`
* `dirty_settlement_amount_base = 99290.00`
* realized P&L fields = `0.00`

#### Expected outputs

* position cost basis increases by `98040.00`
* one lot is created with principal cost and separately stored accrued interest
* settlement cash outflow reflects `99290.00`
* accrued-income offset initializes at `1250.00`

#### Invariants checked

* accrued interest is not treated as income
* accrued interest is stored separately
* settlement cash may exceed book cost

---

### 15.4 Example D: Bond BUY with later income offset

#### Initial BUY state

From Example C:

* accrued-income offset remaining local = `1250.00`

#### Later income event assumption

* gross coupon income local = `1500.00`

#### Net-income effect under policy

* `offset_applied = 1250.00`
* `net_income = 1500.00 - 1250.00 = 250.00`
* `remaining_offset = 0.00`

#### Required outcome

* the future income event must be able to consume the offset
* the offset must reduce net income, not gross income classification
* the offset trail must remain auditable back to the `BUY`

---

### 15.5 Example E: Auto-generated cash entry

#### Inputs

* `cash_entry_mode = AUTO_GENERATE`

#### Required outcome

* the engine generates a linked cash entry
* the cash entry has the same `economic_event_id`
* `originating_transaction_id` links back to the `BUY`
* no duplicate cash entry may be produced on replay

---

### 15.6 Example F: Upstream-provided cash entry

#### Inputs

* `cash_entry_mode = UPSTREAM_PROVIDED`

#### Required outcome

* the engine does not auto-generate a duplicate cash entry
* the external cash transaction is accepted and linked
* security-side and cash-side effects remain reconcilable

---

## 16. BUY Decision Tables

### 16.1 Instrument-type decision table

| Condition                                                            | Required behavior                |
| -------------------------------------------------------------------- | -------------------------------- |
| Equity / non-accrual instrument                                      | No accrued-income offset created |
| Fixed-income / accrual-bearing instrument with accrued interest      | Create accrued-income offset     |
| Fixed-income / accrual-bearing instrument with zero accrued interest | Offset initializes to zero       |

### 16.2 Accrued-interest treatment decision table

| Condition                                            | Book cost                 | Settlement cash                                       | Offset                                     |
| ---------------------------------------------------- | ------------------------- | ----------------------------------------------------- | ------------------------------------------ |
| Policy excludes accrued interest from cost basis     | Excludes accrued interest | Includes accrued interest                             | Initialize offset                          |
| Policy includes accrued interest in cost basis       | Includes accrued interest | Includes accrued interest                             | Initialize offset if recoverable by policy |
| Policy uses separate accrued-interest cash component | Cost basis per policy     | Settlement cash may be split across linked components | Initialize offset per policy               |

### 16.3 Cash-entry mode decision table

| Condition                | Required behavior                                                              |
| ------------------------ | ------------------------------------------------------------------------------ |
| `AUTO_GENERATE`          | Engine generates linked cash entry                                             |
| `UPSTREAM_PROVIDED`      | Engine expects and links external cash entry                                   |
| Linked cash arrives late | Security-side record remains traceable and pending reconciliation until linked |

### 16.4 Timing decision table

| Condition                                     | Required behavior                                        |
| --------------------------------------------- | -------------------------------------------------------- |
| `position_effective_timing = TRADE_DATE`      | Position becomes economically visible on trade date      |
| `position_effective_timing = SETTLEMENT_DATE` | Position becomes effective on settlement date            |
| `cash_effective_timing = TRADE_DATE`          | Cash may be reserved/committed on trade date             |
| `cash_effective_timing = SETTLEMENT_DATE`     | Cash is reduced for ledger settlement on settlement date |

### 16.5 Fee-capitalization decision table

| Condition                        | Required behavior                                          |
| -------------------------------- | ---------------------------------------------------------- |
| Fee component marked capitalized | Included in `capitalized_fees_*` and cost basis            |
| Fee component marked expensed    | Excluded from cost basis and included in `expensed_fees_*` |
| No fee policy available          | Fail or park according to policy-resolution rules          |

---

## 17. BUY Test Matrix

The implementation is not complete unless the following test categories are covered.

### 17.1 Validation tests

* accept valid standard `BUY`
* reject zero quantity
* reject negative quantity
* reject negative fee component
* reject negative accrued interest
* reject missing settlement date
* reject missing required FX for cross-currency `BUY`
* reject invalid enum values
* reject principal mismatch beyond tolerance
* reject policy conflicts

### 17.2 Calculation tests

* same-currency equity `BUY`
* cross-currency equity `BUY`
* equity `BUY` with multiple fee components
* equity `BUY` with capitalized and expensed fee split
* bond `BUY` with accrued interest
* cross-currency bond `BUY` with accrued interest
* accrued interest excluded from book cost
* accrued interest included in book cost
* separate accrued-interest cash component policy

### 17.3 Position tests

* `BUY` into empty position
* `BUY` into existing long position
* trade-date-effective position
* settlement-date-effective position
* settled/unsettled quantity transition
* held-since first acquisition
* held-since top-up acquisition
* held-since reset after reopen

### 17.4 Lot tests

* lot creation for every `BUY`
* correct lot acquired quantity
* correct lot open quantity
* correct lot book cost
* separate accrued-interest storage on lot
* FIFO compatibility
* average-cost compatibility
* specific-lot schema readiness

### 17.5 Cash and dual-accounting tests

* auto-generated linked cash entry
* upstream-provided linked cash entry
* duplicate cash prevention
* linkage integrity
* same-currency settlement cash
* cross-currency settlement cash
* trade-date cash effect
* settlement-date cash effect

### 17.6 Accrued-interest offset tests

* offset initialized on fixed-income `BUY`
* no offset for non-accrual instrument
* partial offset consumption by later income
* full offset consumption by later income
* cross-currency offset handling
* offset traceability to source `BUY`

### 17.7 P&L schema tests

* explicit zero realized capital P&L local
* explicit zero realized FX P&L local
* explicit zero realized total P&L local
* explicit zero realized capital P&L base
* explicit zero realized FX P&L base
* explicit zero realized total P&L base

### 17.8 Query tests

* enriched transaction visibility
* position visibility after first `BUY`
* position visibility after multiple `BUY`s
* lot visibility
* cash linkage visibility
* accrued-offset visibility
* policy metadata visibility

### 17.9 Idempotency and replay tests

* same transaction replay does not duplicate business effects
* duplicate `BUY` detection
* duplicate linked cash prevention
* replay-safe regeneration of derived state
* late-arriving linked cash reconciles correctly

### 17.10 Failure-mode tests

* validation hard-fail
* park pending remediation
* retryable processing failure
* terminal processing failure
* partial processing with explicit state visibility

---

## 18. BUY Edge Cases and Failure Cases

### 18.1 Edge cases

The engine must explicitly handle:

* zero quantity
* negative quantity
* zero execution price
* missing settlement date
* cross-currency `BUY` without required FX
* supplied principal mismatching quantity × price
* zero accrued interest on accrual-bearing instrument
* multiple fee components with mixed treatment
* `BUY` opening a new position
* `BUY` topping up an existing position
* `BUY` with late linked cash entry
* `BUY` replay / duplicate arrival

### 18.2 Failure cases

The engine must explicitly define behavior for:

* validation failure
* referential integrity failure
* policy-resolution failure
* reconciliation failure
* duplicate detection conflict
* linked cash missing beyond expected SLA
* event publish failure after local persistence
* query-read-model lag or partial propagation

### 18.3 Failure semantics requirement

For each failure class, the system must define:

* status
* reason code
* whether retriable
* whether blocking
* whether user-visible
* what operational action is required

---

## 19. BUY Configurable Policies

All material `BUY` behavior must be configurable through versioned policy, not code forks.

### 19.1 Mandatory configurable dimensions

The following must be configurable:

* principal supplied vs derived
* quantity precision
* price precision
* FX precision
* reconciliation tolerance
* fee-capitalization rules by fee component
* accrued-interest treatment
* whether accrued interest is included in cost basis
* whether accrued interest is included in settlement cash
* whether accrued interest is emitted as a separate linked cash component
* cash-entry mode
* position timing
* cash timing
* performance timing
* held-since reset behavior
* linkage enforcement
* duplicate/replay handling
* tax handling as fee vs separate charge
* overdraft / negative-cash handling

### 19.2 Policy traceability

Every processed `BUY` must preserve:

* `calculation_policy_id`
* `calculation_policy_version`

### 19.3 Policy conflict rule

If two policies or policy fragments conflict in a way that changes a material outcome, the engine must not silently choose one. It must fail or park according to policy-resolution rules.

---

## 20. BUY Gap Assessment Checklist

This section defines the required template for assessing the current implementation against this RFC.

For each requirement, implementation review must record:

* requirement id or title
* current implementation status:

  * `COVERED`
  * `PARTIALLY_COVERED`
  * `NOT_COVERED`
* behavior match status:

  * `MATCHES`
  * `PARTIALLY_MATCHES`
  * `DOES_NOT_MATCH`
* current observed behavior
* target required behavior
* risk if unchanged
* proposed action
* blocking / non-blocking
* tests required
* schema impact
* behavior-change impact

### 20.1 Characterization rule

If the current implementation already matches a requirement in this RFC, that behavior must be locked with characterization tests before refactoring or enhancement.

### 20.2 Completion rule

`BUY` is complete only when:

* the full input contract is implemented
* all mandatory validations are enforced
* all mandatory calculations are implemented
* dual-accounting support is implemented
* accrued-interest offset behavior is implemented
* timing behavior is implemented
* all required metadata is preserved
* all required query outputs are available
* invariants are enforced
* the required test matrix is complete
* all remaining gaps are explicitly documented and approved

---

## 21. Appendices

### Appendix A: Error and Reason Codes

The platform must maintain a supporting catalog for:

* validation errors
* reconciliation mismatches
* policy-resolution failures
* linkage failures
* duplicate/replay conflicts
* processing failures

### Appendix B: Configuration Reference

The platform must maintain a supporting catalog for each configurable policy item, including:

* config name
* type
* allowed values
* default
* effect
* whether the setting has historical recalculation impact

### Appendix C: Field Catalog Extensions

Additional institution-specific fields may be added only if they:

* do not violate this RFC
* are documented in the field catalog
* preserve source classification and mutability metadata
* remain auditable and testable

### Appendix D: Future Transaction RFC Alignment

Subsequent transaction RFCs (such as `SELL`, `DIVIDEND`, `INTEREST`, `TRANSFER_IN`) must follow the same structural pattern as this `BUY` RFC to ensure consistency across:

* engineering implementation
* AI-assisted coding
* QA and regression
* BA analysis
* support and ops runbooks
* audit and reconciliation

---

## 22. Final Authoritative Statement

This RFC is the canonical specification for `BUY`.

If an implementation, test, support workflow, or downstream consumer behavior conflicts with this document, this document is the source of truth unless an approved exception or superseding RFC version explicitly states otherwise.
