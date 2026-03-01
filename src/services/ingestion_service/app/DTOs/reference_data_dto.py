from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, condecimal


class PortfolioBenchmarkAssignmentRecord(BaseModel):
    portfolio_id: str = Field(..., description="Canonical portfolio identifier.", examples=["DEMO_DPM_EUR_001"])
    benchmark_id: str = Field(
        ...,
        description="Canonical benchmark identifier.",
        examples=["BMK_GLOBAL_BALANCED_60_40"],
    )
    effective_from: date = Field(..., description="Assignment effective start date.", examples=["2025-01-01"])
    effective_to: date | None = Field(
        None,
        description="Assignment effective end date, null for open-ended assignment.",
        examples=["2026-12-31"],
    )
    assignment_source: str = Field(
        ...,
        description="Source channel that established this benchmark assignment.",
        examples=["benchmark_policy_engine"],
    )
    assignment_status: str = Field(..., description="Assignment status.", examples=["active"])
    policy_pack_id: str | None = Field(
        None,
        description="Optional policy pack identifier.",
        examples=["policy_pack_wm_v1"],
    )
    source_system: str | None = Field(None, description="Upstream source system.", examples=["lotus-manage"])
    assignment_recorded_at: datetime | None = Field(
        None,
        description="Optional assignment capture timestamp; defaults to ingestion time.",
    )
    assignment_version: int = Field(
        1,
        description="Assignment version used for tie-breaks at same effective_from.",
        examples=[1],
        ge=1,
    )

    model_config = ConfigDict()


class BenchmarkDefinitionRecord(BaseModel):
    benchmark_id: str = Field(..., description="Canonical benchmark identifier.", examples=["BMK_GLOBAL_BALANCED_60_40"])
    benchmark_name: str = Field(..., description="Benchmark display name.", examples=["Global Balanced 60/40 (TR)"])
    benchmark_type: Literal["single_index", "composite"] = Field(
        ...,
        description="Benchmark type.",
        examples=["composite"],
    )
    benchmark_currency: str = Field(..., description="Benchmark currency.", examples=["USD"])
    return_convention: Literal["price_return_index", "total_return_index"] = Field(
        ...,
        description="Benchmark return convention.",
        examples=["total_return_index"],
    )
    benchmark_status: str = Field("active", description="Benchmark status.", examples=["active"])
    benchmark_family: str | None = Field(
        None,
        description="Benchmark family grouping.",
        examples=["multi_asset_strategic"],
    )
    benchmark_provider: str | None = Field(
        None,
        description="Benchmark provider name.",
        examples=["MSCI"],
    )
    rebalance_frequency: str | None = Field(
        None,
        description="Rebalance frequency for composite benchmarks.",
        examples=["quarterly"],
    )
    classification_set_id: str | None = Field(
        None,
        description="Classification taxonomy set identifier.",
        examples=["wm_global_taxonomy_v1"],
    )
    classification_labels: dict[str, str] = Field(
        default_factory=dict,
        description="Canonical classification labels.",
        examples=[{"asset_class": "multi_asset", "region": "global"}],
    )
    effective_from: date = Field(..., description="Definition effective start date.", examples=["2025-01-01"])
    effective_to: date | None = Field(None, description="Definition effective end date.", examples=["2026-12-31"])
    source_timestamp: datetime | None = Field(None, description="Source publication timestamp.")
    source_vendor: str | None = Field(None, description="Source vendor.", examples=["MSCI"])
    source_record_id: str | None = Field(None, description="Source record identifier.", examples=["bmk_v20260131"])
    quality_status: str = Field("accepted", description="Quality status.", examples=["accepted"])

    model_config = ConfigDict()


class BenchmarkCompositionRecord(BaseModel):
    benchmark_id: str = Field(..., description="Benchmark identifier.", examples=["BMK_GLOBAL_BALANCED_60_40"])
    index_id: str = Field(..., description="Component index identifier.", examples=["IDX_MSCI_WORLD_TR"])
    composition_effective_from: date = Field(
        ...,
        description="Composition effective start date.",
        examples=["2026-01-01"],
    )
    composition_effective_to: date | None = Field(
        None,
        description="Composition effective end date.",
        examples=["2026-03-31"],
    )
    composition_weight: condecimal(ge=Decimal(0), le=Decimal(1)) = Field(
        ...,
        description="Component weight between 0 and 1.",
        examples=["0.6000000000"],
    )
    rebalance_event_id: str | None = Field(
        None,
        description="Rebalance event identifier.",
        examples=["rebalance_2026q1"],
    )
    source_timestamp: datetime | None = Field(None, description="Source publication timestamp.")
    source_vendor: str | None = Field(None, description="Source vendor.", examples=["MSCI"])
    source_record_id: str | None = Field(None, description="Source record identifier.", examples=["cmp_v20260131"])
    quality_status: str = Field("accepted", description="Quality status.", examples=["accepted"])

    model_config = ConfigDict()


class IndexDefinitionRecord(BaseModel):
    index_id: str = Field(..., description="Canonical index identifier.", examples=["IDX_MSCI_WORLD_TR"])
    index_name: str = Field(..., description="Index display name.", examples=["MSCI World Total Return"])
    index_currency: str = Field(..., description="Index currency.", examples=["USD"])
    index_type: str | None = Field(None, description="Index type descriptor.", examples=["equity_index"])
    index_status: str = Field("active", description="Index status.", examples=["active"])
    index_provider: str | None = Field(None, description="Index provider.", examples=["MSCI"])
    index_market: str | None = Field(
        None,
        description="Index market or universe scope.",
        examples=["global_developed"],
    )
    classification_set_id: str | None = Field(
        None,
        description="Classification taxonomy set identifier.",
        examples=["wm_global_taxonomy_v1"],
    )
    classification_labels: dict[str, str] = Field(
        default_factory=dict,
        description="Canonical classification labels for attribution.",
        examples=[{"asset_class": "equity", "sector": "technology", "region": "global"}],
    )
    effective_from: date = Field(..., description="Definition effective start date.", examples=["2025-01-01"])
    effective_to: date | None = Field(None, description="Definition effective end date.", examples=["2026-12-31"])
    source_timestamp: datetime | None = Field(None, description="Source publication timestamp.")
    source_vendor: str | None = Field(None, description="Source vendor.", examples=["MSCI"])
    source_record_id: str | None = Field(None, description="Source record identifier.", examples=["idx_v20260131"])
    quality_status: str = Field("accepted", description="Quality status.", examples=["accepted"])

    model_config = ConfigDict()


class IndexPriceSeriesRecord(BaseModel):
    series_id: str = Field(..., description="Series identifier.", examples=["series_idx_world_price"])
    index_id: str = Field(..., description="Index identifier.", examples=["IDX_MSCI_WORLD_TR"])
    series_date: date = Field(..., description="Series date.", examples=["2026-01-02"])
    index_price: condecimal(gt=Decimal(0)) = Field(..., description="Index price value.", examples=["4567.1234000000"])
    series_currency: str = Field(..., description="Series currency code.", examples=["USD"])
    value_convention: str = Field(..., description="Value convention label.", examples=["close_price"])
    source_timestamp: datetime | None = Field(None, description="Source publication timestamp.")
    source_vendor: str | None = Field(None, description="Source vendor.", examples=["MSCI"])
    source_record_id: str | None = Field(None, description="Source record identifier.", examples=["idxp_20260102"])
    quality_status: str = Field("accepted", description="Quality status.", examples=["accepted"])

    model_config = ConfigDict()


class IndexReturnSeriesRecord(BaseModel):
    series_id: str = Field(..., description="Series identifier.", examples=["series_idx_world_ret"])
    index_id: str = Field(..., description="Index identifier.", examples=["IDX_MSCI_WORLD_TR"])
    series_date: date = Field(..., description="Series date.", examples=["2026-01-02"])
    index_return: Decimal = Field(..., description="Index return value.", examples=["0.0023000000"])
    return_period: str = Field(..., description="Return period label.", examples=["1d"])
    return_convention: str = Field(..., description="Return convention label.", examples=["total_return_index"])
    series_currency: str = Field(..., description="Series currency code.", examples=["USD"])
    source_timestamp: datetime | None = Field(None, description="Source publication timestamp.")
    source_vendor: str | None = Field(None, description="Source vendor.", examples=["MSCI"])
    source_record_id: str | None = Field(None, description="Source record identifier.", examples=["idxr_20260102"])
    quality_status: str = Field("accepted", description="Quality status.", examples=["accepted"])

    model_config = ConfigDict()


class BenchmarkReturnSeriesRecord(BaseModel):
    series_id: str = Field(..., description="Series identifier.", examples=["series_bmk_60_40_ret"])
    benchmark_id: str = Field(..., description="Benchmark identifier.", examples=["BMK_GLOBAL_BALANCED_60_40"])
    series_date: date = Field(..., description="Series date.", examples=["2026-01-02"])
    benchmark_return: Decimal = Field(..., description="Benchmark return value.", examples=["0.0019000000"])
    return_period: str = Field(..., description="Return period label.", examples=["1d"])
    return_convention: str = Field(..., description="Return convention label.", examples=["total_return_index"])
    series_currency: str = Field(..., description="Series currency code.", examples=["USD"])
    source_timestamp: datetime | None = Field(None, description="Source publication timestamp.")
    source_vendor: str | None = Field(None, description="Source vendor.", examples=["MSCI"])
    source_record_id: str | None = Field(None, description="Source record identifier.", examples=["bmkr_20260102"])
    quality_status: str = Field("accepted", description="Quality status.", examples=["accepted"])

    model_config = ConfigDict()


class RiskFreeSeriesRecord(BaseModel):
    series_id: str = Field(..., description="Series identifier.", examples=["rf_usd_3m"])
    risk_free_curve_id: str = Field(..., description="Risk-free curve identifier.", examples=["USD_SOFR_3M"])
    series_date: date = Field(..., description="Series date.", examples=["2026-01-02"])
    value: Decimal = Field(..., description="Risk-free value.", examples=["0.0350000000"])
    value_convention: Literal["annualized_rate", "period_return"] = Field(
        ...,
        description="Risk-free value convention.",
        examples=["annualized_rate"],
    )
    day_count_convention: str | None = Field(
        None,
        description="Day-count convention for annualized rates.",
        examples=["act_360"],
    )
    compounding_convention: str | None = Field(
        None,
        description="Compounding convention.",
        examples=["simple"],
    )
    series_currency: str = Field(..., description="Series currency.", examples=["USD"])
    source_timestamp: datetime | None = Field(None, description="Source publication timestamp.")
    source_vendor: str | None = Field(None, description="Source vendor.", examples=["BLOOMBERG"])
    source_record_id: str | None = Field(None, description="Source record identifier.", examples=["rf_20260102"])
    quality_status: str = Field("accepted", description="Quality status.", examples=["accepted"])

    model_config = ConfigDict()


class ClassificationTaxonomyRecord(BaseModel):
    classification_set_id: str = Field(..., description="Classification set identifier.", examples=["wm_global_taxonomy_v1"])
    taxonomy_scope: str = Field(..., description="Taxonomy scope.", examples=["index"])
    dimension_name: str = Field(..., description="Dimension name.", examples=["sector"])
    dimension_value: str = Field(..., description="Dimension value.", examples=["technology"])
    dimension_description: str | None = Field(
        None,
        description="Dimension description.",
        examples=["Technology sector classification"],
    )
    effective_from: date = Field(..., description="Effective start date.", examples=["2025-01-01"])
    effective_to: date | None = Field(None, description="Effective end date.", examples=["2026-12-31"])
    source_timestamp: datetime | None = Field(None, description="Source publication timestamp.")
    source_vendor: str | None = Field(None, description="Source vendor.", examples=["LOTUS_TAXONOMY"])
    source_record_id: str | None = Field(None, description="Source record identifier.", examples=["tax_20260131"])
    quality_status: str = Field("accepted", description="Quality status.", examples=["accepted"])

    model_config = ConfigDict()


class PortfolioBenchmarkAssignmentIngestionRequest(BaseModel):
    benchmark_assignments: list[PortfolioBenchmarkAssignmentRecord] = Field(
        ...,
        description="Portfolio benchmark assignment records.",
        min_length=1,
    )

    model_config = ConfigDict()


class BenchmarkDefinitionIngestionRequest(BaseModel):
    benchmark_definitions: list[BenchmarkDefinitionRecord] = Field(
        ...,
        description="Benchmark definition records.",
        min_length=1,
    )

    model_config = ConfigDict()


class BenchmarkCompositionIngestionRequest(BaseModel):
    benchmark_compositions: list[BenchmarkCompositionRecord] = Field(
        ...,
        description="Benchmark composition records.",
        min_length=1,
    )

    model_config = ConfigDict()


class IndexDefinitionIngestionRequest(BaseModel):
    indices: list[IndexDefinitionRecord] = Field(..., description="Index definition records.", min_length=1)

    model_config = ConfigDict()


class IndexPriceSeriesIngestionRequest(BaseModel):
    index_price_series: list[IndexPriceSeriesRecord] = Field(
        ...,
        description="Index price series records.",
        min_length=1,
    )

    model_config = ConfigDict()


class IndexReturnSeriesIngestionRequest(BaseModel):
    index_return_series: list[IndexReturnSeriesRecord] = Field(
        ...,
        description="Index return series records.",
        min_length=1,
    )

    model_config = ConfigDict()


class BenchmarkReturnSeriesIngestionRequest(BaseModel):
    benchmark_return_series: list[BenchmarkReturnSeriesRecord] = Field(
        ...,
        description="Benchmark return series records.",
        min_length=1,
    )

    model_config = ConfigDict()


class RiskFreeSeriesIngestionRequest(BaseModel):
    risk_free_series: list[RiskFreeSeriesRecord] = Field(
        ...,
        description="Risk-free series records.",
        min_length=1,
    )

    model_config = ConfigDict()


class ClassificationTaxonomyIngestionRequest(BaseModel):
    classification_taxonomy: list[ClassificationTaxonomyRecord] = Field(
        ...,
        description="Classification taxonomy records.",
        min_length=1,
    )

    model_config = ConfigDict()
