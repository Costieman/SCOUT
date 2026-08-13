"""Canonicalize one explicitly identified Tiingo benchmark series for research use.

This boundary is separate from the reviewed-equity universe workflow. A benchmark must be named,
identified, bounded, quality checked, and promoted into its own immutable canonical dataset.
The standalone result can then be composed with an Experiment A research cohort.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from trade_scout.data.canonical_storage import (
    CanonicalDailyBarStore,
    CanonicalDatasetManifest,
    DatasetPromotionRequest,
)
from trade_scout.data.contracts import (
    DatasetVersion,
    InstrumentId,
    InstrumentRecord,
    QualityStatus,
    SecurityType,
)
from trade_scout.data.normalization import normalize_provider_daily_bars
from trade_scout.data.providers.tiingo_split_preview import (
    TiingoSplitPreviewError,
    build_tiingo_split_only_provider_bars,
)
from trade_scout.data.session_completeness import (
    DatasetSessionCompletenessAudit,
    SessionCompletenessError,
    audit_daily_bar_session_completeness,
)

BENCHMARK_TRANSFORMATION_VERSION = "tiingo-benchmark-split-only-v0.1"
BENCHMARK_ADJUSTMENT_POLICY_VERSION = "raw-plus-split-only-v0.1"
BENCHMARK_QUALITY_VERSION = "canonical-daily-bar-plus-session-completeness-v0.1"
BENCHMARK_UNIVERSE_VERSION = "explicit-research-benchmark-v0.1"


class TiingoBenchmarkPromotionError(RuntimeError):
    """Raised when benchmark evidence cannot be safely promoted."""


@dataclass(frozen=True, slots=True)
class TiingoBenchmarkDefinition:
    """Explicit permanent identity and declared historical coverage for one benchmark."""

    query_symbol: str
    provider_instrument_id: str
    instrument_id: InstrumentId
    name: str
    exchange: str
    currency: str
    first_trade_date: date
    dataset_start_date: date
    dataset_end_date: date
    dataset_version: DatasetVersion
    dataset_id: str = "research_benchmark_daily"

    def __post_init__(self) -> None:
        for value, field in (
            (self.query_symbol, "query_symbol"),
            (self.provider_instrument_id, "provider_instrument_id"),
            (str(self.instrument_id), "instrument_id"),
            (self.name, "name"),
            (self.exchange, "exchange"),
            (self.currency, "currency"),
            (str(self.dataset_version), "dataset_version"),
            (self.dataset_id, "dataset_id"),
        ):
            if not value.strip():
                raise ValueError(f"{field} must be non-empty")
        if self.dataset_end_date < self.dataset_start_date:
            raise ValueError("benchmark dataset_end_date precedes dataset_start_date")
        if self.dataset_start_date < self.first_trade_date:
            raise ValueError("benchmark coverage cannot begin before first_trade_date")


@dataclass(frozen=True, slots=True)
class TiingoBenchmarkPromotionResult:
    """Immutable benchmark promotion and quality diagnostics."""

    manifest: CanonicalDatasetManifest
    session_audit: DatasetSessionCompletenessAudit
    split_event_count: int
    dividend_event_count: int
    source_batch_ids: tuple[str, ...]
    already_registered: bool


def promote_tiingo_benchmark_rows(
    rows: list[dict[str, Any]],
    *,
    definition: TiingoBenchmarkDefinition,
    canonical_root: Path,
    source_batch_ids: tuple[str, ...],
    promoted_at: datetime | None = None,
) -> TiingoBenchmarkPromotionResult:
    """Transform one raw Tiingo EOD payload and promote it only after fail-closed checks."""

    if not source_batch_ids or any(not value.strip() for value in source_batch_ids):
        raise TiingoBenchmarkPromotionError("benchmark promotion requires raw source batch IDs")
    if len(set(source_batch_ids)) != len(source_batch_ids):
        raise TiingoBenchmarkPromotionError("benchmark source batch IDs must be unique")

    try:
        transformed = build_tiingo_split_only_provider_bars(
            rows,
            query_symbol=definition.query_symbol,
            provider_instrument_id=definition.provider_instrument_id,
        )
    except TiingoSplitPreviewError as exc:
        raise TiingoBenchmarkPromotionError(str(exc)) from exc

    if (
        transformed.tiingo_adjusted_cross_check_eligible
        and transformed.tiingo_adjusted_cross_check_mismatch_count
    ):
        raise TiingoBenchmarkPromotionError(
            "benchmark split-only transform disagrees with eligible Tiingo adjusted cross-check"
        )

    instrument = _instrument(definition)
    normalized = normalize_provider_daily_bars(
        transformed.bars,
        instruments=(instrument,),
        dataset_version=definition.dataset_version,
    )
    if normalized.status is not QualityStatus.PASS:
        raise TiingoBenchmarkPromotionError(
            "benchmark normalization is not PASS: "
            f"normalization_issues={len(normalized.normalization_issues)}, "
            f"quality_issues={len(normalized.quality_issues)}"
        )
    if normalized.normalization_issues or normalized.quality_issues:
        raise TiingoBenchmarkPromotionError(
            "benchmark has normalization or quality issues and cannot be promoted"
        )
    if len(normalized.bars) != len(transformed.bars):
        raise TiingoBenchmarkPromotionError(
            "benchmark normalized row count does not match verified raw row count"
        )
    if not normalized.bars:
        raise TiingoBenchmarkPromotionError("benchmark normalization produced no canonical bars")

    try:
        session_audit = audit_daily_bar_session_completeness(
            normalized.bars,
            instruments=(instrument,),
            dataset_start_date=definition.dataset_start_date,
            dataset_end_date=definition.dataset_end_date,
        )
    except SessionCompletenessError as exc:
        raise TiingoBenchmarkPromotionError(str(exc)) from exc
    if not session_audit.complete:
        raise TiingoBenchmarkPromotionError(
            "benchmark session completeness failed: "
            f"missing={session_audit.missing_expected_session_count}, "
            f"unexpected={session_audit.unexpected_observed_date_count}, "
            f"duplicates={session_audit.duplicate_observed_date_count}"
        )

    store = CanonicalDailyBarStore(canonical_root)
    existing = store.get_manifest(definition.dataset_version)
    created_at = existing.created_at if existing is not None else (promoted_at or datetime.now(UTC))
    if created_at.tzinfo is None or created_at.utcoffset() is None:
        raise TiingoBenchmarkPromotionError("promoted_at must be timezone-aware")

    manifest = store.promote(
        normalized.bars,
        DatasetPromotionRequest(
            dataset_id=definition.dataset_id,
            dataset_version=definition.dataset_version,
            primary_provider_id="tiingo",
            created_at=created_at,
            source_batch_ids=source_batch_ids,
            transformation_version=BENCHMARK_TRANSFORMATION_VERSION,
            adjustment_policy_version=BENCHMARK_ADJUSTMENT_POLICY_VERSION,
            universe_construction_version=BENCHMARK_UNIVERSE_VERSION,
            quality_check_version=BENCHMARK_QUALITY_VERSION,
        ),
    )
    if store.load(definition.dataset_version) != normalized.bars:
        raise TiingoBenchmarkPromotionError(
            "post-promotion reload does not match deterministic benchmark normalization"
        )

    return TiingoBenchmarkPromotionResult(
        manifest=manifest,
        session_audit=session_audit,
        split_event_count=len(transformed.split_events),
        dividend_event_count=transformed.dividend_event_count,
        source_batch_ids=source_batch_ids,
        already_registered=existing is not None,
    )


def _instrument(definition: TiingoBenchmarkDefinition) -> InstrumentRecord:
    return InstrumentRecord(
        instrument_id=definition.instrument_id,
        primary_symbol=definition.query_symbol.strip().upper(),
        name=definition.name.strip(),
        exchange=definition.exchange.strip().upper(),
        security_type=SecurityType.ETF,
        currency=definition.currency.strip().upper(),
        first_trade_date=definition.first_trade_date,
        delisting_date=None,
        provider_ids={"tiingo": definition.provider_instrument_id.strip()},
    )
