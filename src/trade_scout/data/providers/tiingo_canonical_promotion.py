"""Fail-closed promotion of reviewed Tiingo split-only histories into canonical storage."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from trade_scout.data.canonical_storage import (
    CanonicalDailyBarStore,
    CanonicalDatasetManifest,
    DatasetPromotionRequest,
)
from trade_scout.data.contracts import DailyBar, DatasetVersion, QualityStatus
from trade_scout.data.durable_raw_receipt import (
    DurableRawReceipt,
    load_durable_raw_receipt,
    verify_durable_raw_receipt,
)
from trade_scout.data.instrument_storage import InstrumentMasterStore
from trade_scout.data.normalization import normalize_provider_daily_bars_identity_aware
from trade_scout.data.providers.tiingo_split_preview import (
    TiingoSplitPreviewError,
    build_tiingo_split_only_provider_bars,
)
from trade_scout.data.reviewed_identity_snapshot import (
    ProviderSeriesLink,
    ReviewedIdentitySnapshotCandidate,
    load_reviewed_identity_snapshot_candidate,
)
from trade_scout.data.session_completeness import (
    DatasetSessionCompletenessAudit,
    SessionCompletenessError,
    audit_daily_bar_session_completeness,
    default_us_equity_session_calendar,
)

_DATASET_ID = "equities_daily_reviewed_tiingo_slice"
_TRANSFORMATION_VERSION = "tiingo-reviewed-split-only-normalization-v0.1"
_ADJUSTMENT_POLICY_VERSION = "raw-plus-split-only-v0.1"
_QUALITY_CHECK_VERSION = "canonical-daily-bar-quality-v0.1"
_PROMOTION_SCOPE = "reviewed_seed_set_only"
_DATASET_VERSION_BY_IDENTITY_SNAPSHOT = {
    "tiingo-reviewed-identity-candidate-v0.2": DatasetVersion("tiingo-reviewed-split-only-v0.1"),
    "tiingo-reviewed-identity-candidate-v0.3": DatasetVersion("tiingo-reviewed-split-only-v0.2"),
}


class TiingoCanonicalPromotionError(RuntimeError):
    """Raised when reviewed Tiingo price evidence is not safe for canonical promotion."""


@dataclass(frozen=True, slots=True)
class TiingoCanonicalPromotionResult:
    """Verified result for one bounded immutable canonical price promotion."""

    manifest: CanonicalDatasetManifest
    already_registered: bool
    identity_snapshot_version: str
    promotion_scope: str
    symbol_count: int
    row_count: int
    split_event_count: int
    dividend_event_count: int
    cross_check_eligible_symbol_count: int
    cross_check_mismatch_field_count: int
    session_calendar_definition_version: str
    session_coverage_start_date: date | None
    session_coverage_end_date: date
    missing_expected_session_count: int
    unexpected_observed_date_count: int
    duplicate_observed_date_count: int
    source_receipt_ids: tuple[str, ...]
    source_batch_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class _BuiltCanonicalSlice:
    bars: tuple[DailyBar, ...]
    identity_snapshot_version: str
    symbol_count: int
    split_event_count: int
    dividend_event_count: int
    cross_check_eligible_symbol_count: int
    cross_check_mismatch_field_count: int
    session_audit: DatasetSessionCompletenessAudit
    source_receipt_ids: tuple[str, ...]
    source_batch_ids: tuple[str, ...]


def promote_reviewed_tiingo_prices(
    *,
    receipt_root: Path,
    raw_root: Path,
    storage_namespace: str,
    candidate_path: Path,
    canonical_root: Path,
    dataset_version: DatasetVersion | None = None,
    dataset_start_date: date | None = None,
    dataset_end_date: date | None = None,
    promoted_at: datetime | None = None,
) -> TiingoCanonicalPromotionResult:
    """Rebuild and promote the reviewed Tiingo price slice with no silent repair.

    The gate re-verifies every targeted durable receipt, rebuilds split-only provider bars from raw
    Tiingo OHLC plus event-date ``splitFactor``, resolves permanent identity plus dated symbol
    history, requires strictly PASS quality and complete expected exchange sessions, and only then
    writes an immutable canonical Parquet dataset. Tiingo's dividend-adjusted ``adj*`` values are
    never used as canonical prices.

    ``dataset_start_date`` and ``dataset_end_date`` may pin the explicit historical coverage
    contract of the acquisition campaign. This prevents a security that listed before the campaign
    window from creating false pre-window gaps while still detecting missing initial or terminal
    sessions inside the requested window.

    Known reviewed identity snapshots map to explicit immutable canonical dataset versions. Callers
    may provide ``dataset_version`` for synthetic/test candidates, but production expansion remains
    fail-closed when an identity snapshot has no reviewed dataset-version mapping.
    """

    candidate = load_reviewed_identity_snapshot_candidate(candidate_path)
    target_dataset_version = (
        dataset_version
        if dataset_version is not None
        else _dataset_version_for_identity_snapshot(candidate.snapshot_version)
    )
    built = _build_reviewed_slice(
        receipt_root=receipt_root,
        raw_root=raw_root,
        storage_namespace=storage_namespace,
        candidate=candidate,
        canonical_root=canonical_root,
        dataset_version=target_dataset_version,
        dataset_start_date=dataset_start_date,
        dataset_end_date=dataset_end_date,
    )
    store = CanonicalDailyBarStore(canonical_root)
    existing = store.get_manifest(target_dataset_version)
    created_at = existing.created_at if existing is not None else (promoted_at or datetime.now(UTC))
    if created_at.tzinfo is None or created_at.utcoffset() is None:
        raise TiingoCanonicalPromotionError("promoted_at must be timezone-aware")

    request = DatasetPromotionRequest(
        dataset_id=_DATASET_ID,
        dataset_version=target_dataset_version,
        primary_provider_id="tiingo",
        created_at=created_at,
        source_batch_ids=built.source_batch_ids,
        transformation_version=_TRANSFORMATION_VERSION,
        adjustment_policy_version=_ADJUSTMENT_POLICY_VERSION,
        universe_construction_version=built.identity_snapshot_version,
        quality_check_version=_QUALITY_CHECK_VERSION,
    )
    manifest = store.promote(built.bars, request)
    loaded = store.load(target_dataset_version)
    if loaded != built.bars:
        raise TiingoCanonicalPromotionError(
            "post-promotion canonical reload does not exactly match rebuilt reviewed Tiingo bars"
        )

    return TiingoCanonicalPromotionResult(
        manifest=manifest,
        already_registered=existing is not None,
        identity_snapshot_version=built.identity_snapshot_version,
        promotion_scope=_PROMOTION_SCOPE,
        symbol_count=built.symbol_count,
        row_count=len(built.bars),
        split_event_count=built.split_event_count,
        dividend_event_count=built.dividend_event_count,
        cross_check_eligible_symbol_count=built.cross_check_eligible_symbol_count,
        cross_check_mismatch_field_count=built.cross_check_mismatch_field_count,
        session_calendar_definition_version=built.session_audit.calendar_definition_version,
        session_coverage_start_date=built.session_audit.dataset_start_date,
        session_coverage_end_date=built.session_audit.dataset_end_date,
        missing_expected_session_count=built.session_audit.missing_expected_session_count,
        unexpected_observed_date_count=built.session_audit.unexpected_observed_date_count,
        duplicate_observed_date_count=built.session_audit.duplicate_observed_date_count,
        source_receipt_ids=built.source_receipt_ids,
        source_batch_ids=built.source_batch_ids,
    )


def persist_tiingo_canonical_promotion_report(
    path: Path,
    result: TiingoCanonicalPromotionResult,
) -> None:
    """Persist metadata/checksums for the bounded promotion without exposing price values."""

    manifest = result.manifest
    payload = {
        "schema_version": "tiingo-reviewed-canonical-promotion-v0.1",
        "dataset_id": manifest.dataset_id,
        "dataset_version": str(manifest.dataset_version),
        "identity_snapshot_version": result.identity_snapshot_version,
        "promotion_scope": result.promotion_scope,
        "provider_acceptance_changed": False,
        "serving_selected": False,
        "already_registered": result.already_registered,
        "symbol_count": result.symbol_count,
        "record_count": result.row_count,
        "first_trade_date": manifest.first_trade_date.isoformat(),
        "last_trade_date": manifest.last_trade_date.isoformat(),
        "split_event_count": result.split_event_count,
        "dividend_event_count": result.dividend_event_count,
        "cross_check_eligible_symbol_count": result.cross_check_eligible_symbol_count,
        "cross_check_mismatch_field_count": result.cross_check_mismatch_field_count,
        "session_completeness": {
            "calendar_definition_version": result.session_calendar_definition_version,
            "coverage_start_date": (
                result.session_coverage_start_date.isoformat()
                if result.session_coverage_start_date is not None
                else None
            ),
            "coverage_end_date": result.session_coverage_end_date.isoformat(),
            "missing_expected_session_count": result.missing_expected_session_count,
            "unexpected_observed_date_count": result.unexpected_observed_date_count,
            "duplicate_observed_date_count": result.duplicate_observed_date_count,
            "complete": not (
                result.missing_expected_session_count
                or result.unexpected_observed_date_count
                or result.duplicate_observed_date_count
            ),
        },
        "source_receipt_ids": list(result.source_receipt_ids),
        "source_batch_ids": list(result.source_batch_ids),
        "transformation_version": manifest.transformation_version,
        "adjustment_policy_version": manifest.adjustment_policy_version,
        "quality_check_version": manifest.quality_check_version,
        "quality_summary": {
            "pass_count": manifest.quality_summary.pass_count,
            "warn_count": manifest.quality_summary.warn_count,
            "quarantine_count": manifest.quality_summary.quarantine_count,
            "reject_count": manifest.quality_summary.reject_count,
        },
        "content_checksum_sha256": manifest.content_checksum_sha256,
        "parquet_checksum_sha256": manifest.parquet_checksum_sha256,
        "parquet_relative_path": manifest.parquet_relative_path,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def _dataset_version_for_identity_snapshot(snapshot_version: str) -> DatasetVersion:
    try:
        return _DATASET_VERSION_BY_IDENTITY_SNAPSHOT[snapshot_version]
    except KeyError as exc:
        raise TiingoCanonicalPromotionError(
            f"reviewed identity snapshot {snapshot_version} has no approved canonical "
            "dataset version"
        ) from exc


def _build_reviewed_slice(
    *,
    receipt_root: Path,
    raw_root: Path,
    storage_namespace: str,
    candidate: ReviewedIdentitySnapshotCandidate,
    canonical_root: Path,
    dataset_version: DatasetVersion,
    dataset_start_date: date | None,
    dataset_end_date: date | None,
) -> _BuiltCanonicalSlice:
    if not candidate.promotion_ready:
        raise TiingoCanonicalPromotionError("reviewed identity candidate still has coverage gaps")

    snapshot = InstrumentMasterStore(canonical_root).load(candidate.snapshot_version)
    if (
        snapshot.instruments != candidate.instruments
        or snapshot.symbol_history != candidate.symbol_history
    ):
        raise TiingoCanonicalPromotionError(
            "promoted instrument master does not exactly match the reviewed identity candidate"
        )

    links = tuple(item for item in candidate.provider_series_links if item.provider_id == "tiingo")
    if not links:
        raise TiingoCanonicalPromotionError(
            "reviewed candidate contains no Tiingo provider-series links"
        )
    link_by_symbol = _links_by_query_symbol(links)
    receipts = _receipts_by_subject(receipt_root, frozenset(link_by_symbol))

    bars: list[DailyBar] = []
    receipt_ids: list[str] = []
    batch_ids: list[str] = []
    split_events = 0
    dividend_events = 0
    cross_check_eligible = 0
    cross_check_mismatches = 0

    for query_symbol, link in sorted(link_by_symbol.items()):
        receipt = receipts.get(query_symbol)
        if receipt is None:
            raise TiingoCanonicalPromotionError(
                f"no durable Tiingo receipt found for reviewed query symbol {query_symbol}"
            )
        record = verify_durable_raw_receipt(
            receipt,
            durable_root=raw_root,
            storage_namespace=storage_namespace,
        )
        rows = _read_raw_rows(record.payload_path, query_symbol)
        try:
            transform = build_tiingo_split_only_provider_bars(
                rows,
                query_symbol=query_symbol,
                provider_instrument_id=link.provider_series_id,
            )
        except TiingoSplitPreviewError as exc:
            raise TiingoCanonicalPromotionError(str(exc)) from exc

        normalized = normalize_provider_daily_bars_identity_aware(
            transform.bars,
            instruments=snapshot.instruments,
            symbol_history=snapshot.symbol_history,
            dataset_version=dataset_version,
        )
        if normalized.status is not QualityStatus.PASS:
            raise TiingoCanonicalPromotionError(
                f"{query_symbol} normalization status {normalized.status} "
                "blocks canonical promotion"
            )
        if normalized.normalization_issues or normalized.quality_issues:
            raise TiingoCanonicalPromotionError(
                f"{query_symbol} has normalization or quality issues and cannot be promoted"
            )
        if len(normalized.bars) != len(transform.bars):
            raise TiingoCanonicalPromotionError(
                f"{query_symbol} normalized row count does not match verified raw row count"
            )
        if (
            transform.tiingo_adjusted_cross_check_eligible
            and transform.tiingo_adjusted_cross_check_mismatch_count
        ):
            raise TiingoCanonicalPromotionError(
                f"{query_symbol} split-only transform disagrees with eligible Tiingo "
                "adjusted cross-check"
            )

        bars.extend(normalized.bars)
        receipt_ids.append(receipt.receipt_id)
        batch_ids.append(receipt.batch_id)
        split_events += len(transform.split_events)
        dividend_events += transform.dividend_event_count
        cross_check_eligible += int(transform.tiingo_adjusted_cross_check_eligible)
        cross_check_mismatches += transform.tiingo_adjusted_cross_check_mismatch_count

    frozen_bars = tuple(
        sorted(bars, key=lambda item: (str(item.instrument_id), item.trade_date, item.provider_id))
    )
    if not frozen_bars:
        raise TiingoCanonicalPromotionError("reviewed Tiingo canonical slice is empty")

    observed_end = max(bar.trade_date for bar in frozen_bars)
    audit_end = dataset_end_date or observed_end
    try:
        session_audit = audit_daily_bar_session_completeness(
            frozen_bars,
            instruments=snapshot.instruments,
            dataset_start_date=dataset_start_date,
            dataset_end_date=audit_end,
            calendar=default_us_equity_session_calendar(),
        )
    except SessionCompletenessError as exc:
        raise TiingoCanonicalPromotionError(f"expected-session audit failed: {exc}") from exc
    if not session_audit.complete:
        raise TiingoCanonicalPromotionError(
            "expected-session completeness blocks canonical promotion: "
            f"missing={session_audit.missing_expected_session_count}, "
            f"unexpected={session_audit.unexpected_observed_date_count}, "
            f"duplicates={session_audit.duplicate_observed_date_count}, "
            f"missing_histories={session_audit.missing_history_instrument_count}"
        )

    return _BuiltCanonicalSlice(
        bars=frozen_bars,
        identity_snapshot_version=candidate.snapshot_version,
        symbol_count=len(link_by_symbol),
        split_event_count=split_events,
        dividend_event_count=dividend_events,
        cross_check_eligible_symbol_count=cross_check_eligible,
        cross_check_mismatch_field_count=cross_check_mismatches,
        session_audit=session_audit,
        source_receipt_ids=tuple(sorted(receipt_ids)),
        source_batch_ids=tuple(sorted(batch_ids)),
    )


def _links_by_query_symbol(links: tuple[ProviderSeriesLink, ...]) -> dict[str, ProviderSeriesLink]:
    result: dict[str, ProviderSeriesLink] = {}
    for link in links:
        symbol = link.query_symbol.upper()
        if symbol in result:
            raise TiingoCanonicalPromotionError(f"duplicate reviewed Tiingo query link: {symbol}")
        result[symbol] = link
    return result


def _receipts_by_subject(
    receipt_root: Path,
    targets: frozenset[str],
) -> dict[str, DurableRawReceipt]:
    result: dict[str, DurableRawReceipt] = {}
    paths = tuple(sorted(receipt_root.rglob("*.json"))) if receipt_root.exists() else ()
    for path in paths:
        receipt = load_durable_raw_receipt(path)
        if receipt.provider_id != "tiingo" or receipt.subject_key not in targets:
            continue
        if receipt.subject_key in result:
            raise TiingoCanonicalPromotionError(
                f"multiple durable receipts found for reviewed Tiingo symbol {receipt.subject_key}"
            )
        result[receipt.subject_key] = receipt
    return result


def _read_raw_rows(path: Path, symbol: str) -> list[dict[str, Any]]:
    try:
        raw: object = json.loads(path.read_bytes())
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise TiingoCanonicalPromotionError(
            f"verified Tiingo payload is unreadable for {symbol}"
        ) from exc
    if not isinstance(raw, list) or not all(isinstance(item, dict) for item in raw):
        raise TiingoCanonicalPromotionError(
            f"verified Tiingo payload shape is invalid for {symbol}"
        )
    return raw


__all__ = [
    "TiingoCanonicalPromotionError",
    "TiingoCanonicalPromotionResult",
    "persist_tiingo_canonical_promotion_report",
    "promote_reviewed_tiingo_prices",
]
