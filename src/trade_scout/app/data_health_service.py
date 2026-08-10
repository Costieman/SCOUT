"""Build the Data Health workspace from persisted Trade Scout evidence.

The service is deliberately read-only. It translates checked-in provider assessments,
persisted campaign state, optional A+B evidence reports, and an explicitly selected canonical
dataset into presentation contracts. It does not call market-data providers and does not infer
missing observations from absent files.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from trade_scout.api.dashboard_contracts import (
    DataHealthSummary,
    HealthState,
    ProviderHealthSummary,
    ProvenanceSummary,
    QualityCounts,
)
from trade_scout.data.canonical_storage import CanonicalDailyBarStore, CanonicalDatasetManifest
from trade_scout.data.contracts import DatasetVersion
from trade_scout.data.providers.tiingo_campaign_state import (
    TiingoSafeCampaignState,
    load_tiingo_safe_campaign_state,
)


class DataHealthServiceError(RuntimeError):
    """Raised when a supplied data-health evidence artifact is malformed."""


@dataclass(frozen=True, slots=True)
class DataHealthSourcePaths:
    """Explicit evidence locations used to build one Data Health snapshot."""

    tiingo_acceptance_path: Path
    free_stack_acceptance_path: Path
    tiingo_safe_state_path: Path | None = None
    composite_evidence_paths: tuple[Path, ...] = ()
    canonical_root: Path | None = None
    canonical_dataset_version: str | None = None
    scanner_required_session: date | None = None
    failed_ingestion_markers: tuple[Path, ...] = ()
    corporate_action_anomaly_reports: tuple[Path, ...] = ()


def build_data_health_summary(sources: DataHealthSourcePaths) -> DataHealthSummary:
    """Translate persisted evidence into a provider-independent Data Health contract."""

    tiingo_assessment = _load_object(sources.tiingo_acceptance_path)
    free_stack = _load_object(sources.free_stack_acceptance_path)
    tiingo_state = _load_tiingo_state(sources.tiingo_safe_state_path)
    providers = (
        _tiingo_provider_summary(tiingo_assessment, tiingo_state),
        _alpha_provider_summary(free_stack),
        _stooq_provider_summary(free_stack),
    )

    missing_count, discrepancy_count = _composite_counts(sources.composite_evidence_paths)
    corporate_action_count = _count_report_items(sources.corporate_action_anomaly_reports)
    failed_job_count = _existing_marker_count(sources.failed_ingestion_markers)
    canonical = _canonical_summary(sources)

    if canonical is None:
        overall_state = HealthState.BLOCKED
        quality_counts = QualityCounts(passed=0, warned=0, quarantined=0)
        dataset_version = None
        latest_session = None
        scanner_gate = HealthState.BLOCKED
        message = "No explicitly selected canonical Phase 1 dataset is available."
        provenance = ProvenanceSummary(
            dataset_version=None,
            strategy_version=None,
            feature_set_version=None,
            risk_policy_version=None,
            ranking_model_version=None,
            run_id=None,
            as_of_date=None,
        )
    else:
        manifest = canonical
        quality_counts = QualityCounts(
            passed=manifest.quality_summary.pass_count,
            warned=manifest.quality_summary.warn_count,
            quarantined=(
                manifest.quality_summary.quarantine_count + manifest.quality_summary.reject_count
            ),
        )
        dataset_version = str(manifest.dataset_version)
        latest_session = manifest.last_trade_date
        scanner_gate = _scanner_gate(
            latest_session,
            required_session=sources.scanner_required_session,
        )
        overall_state = _overall_state(
            scanner_gate=scanner_gate,
            quality_counts=quality_counts,
            discrepancy_count=discrepancy_count,
        )
        message = (
            "Canonical dataset is registered; downstream use remains subject to visible gates."
        )
        provenance = ProvenanceSummary(
            dataset_version=dataset_version,
            strategy_version=None,
            feature_set_version=None,
            risk_policy_version=None,
            ranking_model_version=None,
            run_id=None,
            as_of_date=latest_session,
        )

    return DataHealthSummary(
        state=overall_state,
        dataset_version=dataset_version,
        latest_canonical_session=latest_session,
        quality_counts=quality_counts,
        missing_data_anomaly_count=missing_count,
        cross_provider_discrepancy_count=discrepancy_count,
        corporate_action_anomaly_count=corporate_action_count,
        failed_ingestion_job_count=failed_job_count,
        scanner_freshness_gate=scanner_gate,
        providers=providers,
        message=message,
        provenance=provenance,
    )


def _tiingo_provider_summary(
    assessment: dict[str, object],
    state: TiingoSafeCampaignState | None,
) -> ProviderHealthSummary:
    decision = _required_text(assessment.get("decision"), "Tiingo decision")
    acceptance_state = HealthState.PASS if decision == "ACCEPTED" else HealthState.WARN
    if state is None:
        message = f"{decision}; no durable S&P 500 campaign state has been supplied."
        current = None
        total = None
    else:
        current = state.durable_completed_symbol_count
        total = state.total_symbol_count
        message = f"{decision}; durable campaign {current}/{total}; last status {state.last_status}."
        if state.last_status == "FAILED":
            acceptance_state = HealthState.WARN
    return ProviderHealthSummary(
        provider_id="tiingo",
        display_name="Tiingo",
        role="Long-history baseline candidate",
        state=acceptance_state,
        latest_successful_session=None,
        message=message,
        progress_current=current,
        progress_total=total,
        progress_label="durably secured symbols" if state is not None else None,
    )


def _alpha_provider_summary(free_stack: dict[str, object]) -> ProviderHealthSummary:
    note = _criterion_note(free_stack, "alpha_vantage_point_in_time_listing_status")
    return ProviderHealthSummary(
        provider_id="alpha_vantage",
        display_name="Alpha Vantage",
        role="Independent validation / listings evidence",
        state=HealthState.WARN,
        latest_successful_session=None,
        message=note,
    )


def _stooq_provider_summary(free_stack: dict[str, object]) -> ProviderHealthSummary:
    note = _criterion_note(free_stack, "stooq_historical_ohlcv_retrieval")
    return ProviderHealthSummary(
        provider_id="stooq",
        display_name="Stooq",
        role="Opportunistic/manual third observation",
        state=HealthState.BLOCKED,
        latest_successful_session=None,
        message=note,
    )


def _load_tiingo_state(path: Path | None) -> TiingoSafeCampaignState | None:
    if path is None or not path.exists():
        return None
    return load_tiingo_safe_campaign_state(path)


def _canonical_summary(sources: DataHealthSourcePaths) -> CanonicalDatasetManifest | None:
    if sources.canonical_root is None or sources.canonical_dataset_version is None:
        return None
    store = CanonicalDailyBarStore(sources.canonical_root)
    return store.get_manifest(DatasetVersion(sources.canonical_dataset_version))


def _scanner_gate(latest: date, *, required_session: date | None) -> HealthState:
    if required_session is None:
        return HealthState.BLOCKED
    if latest < required_session:
        return HealthState.BLOCKED
    if latest > required_session:
        return HealthState.WARN
    return HealthState.PASS


def _overall_state(
    *,
    scanner_gate: HealthState,
    quality_counts: QualityCounts,
    discrepancy_count: int | None,
) -> HealthState:
    if scanner_gate is HealthState.BLOCKED or quality_counts.quarantined:
        return HealthState.BLOCKED
    if scanner_gate is HealthState.WARN or quality_counts.warned:
        return HealthState.WARN
    if discrepancy_count is None or discrepancy_count:
        return HealthState.WARN
    return HealthState.PASS


def _composite_counts(paths: tuple[Path, ...]) -> tuple[int | None, int | None]:
    if not paths:
        return None, None
    missing = 0
    discrepancies = 0
    for path in paths:
        payload = _load_object(path)
        cases = payload.get("cases")
        if not isinstance(cases, list):
            raise DataHealthServiceError(f"composite evidence lacks cases array: {path}")
        for case in cases:
            if not isinstance(case, dict):
                raise DataHealthServiceError(f"composite evidence case is not an object: {path}")
            summary = case.get("summary")
            if not isinstance(summary, dict):
                raise DataHealthServiceError(f"composite evidence case lacks summary: {path}")
            missing += _required_nonnegative_int(summary.get("a_only_count"), "a_only_count")
            missing += _required_nonnegative_int(summary.get("b_only_count"), "b_only_count")
            discrepancies += _required_nonnegative_int(
                summary.get("both_disagree_count"),
                "both_disagree_count",
            )
    return missing, discrepancies


def _count_report_items(paths: tuple[Path, ...]) -> int | None:
    if not paths:
        return None
    count = 0
    for path in paths:
        payload = _load_object(path)
        items = payload.get("items")
        if not isinstance(items, list):
            raise DataHealthServiceError(f"anomaly report lacks items array: {path}")
        count += len(items)
    return count


def _existing_marker_count(paths: tuple[Path, ...]) -> int | None:
    if not paths:
        return None
    return sum(path.exists() for path in paths)


def _criterion_note(payload: dict[str, object], criterion_name: str) -> str:
    criteria = payload.get("criteria")
    if not isinstance(criteria, list):
        raise DataHealthServiceError("provider assessment lacks criteria array")
    for item in criteria:
        if isinstance(item, dict) and item.get("criterion") == criterion_name:
            note = item.get("note")
            return _required_text(note, f"criterion note {criterion_name}")
    raise DataHealthServiceError(f"provider assessment lacks criterion {criterion_name}")


def _load_object(path: Path) -> dict[str, object]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise DataHealthServiceError(f"cannot read data-health evidence: {path}") from exc
    except json.JSONDecodeError as exc:
        raise DataHealthServiceError(f"invalid JSON data-health evidence: {path}") from exc
    if not isinstance(payload, dict):
        raise DataHealthServiceError(f"data-health evidence root must be an object: {path}")
    return payload


def _required_text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise DataHealthServiceError(f"{field} must be non-empty text")
    return value.strip()


def _required_nonnegative_int(value: object, field: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise DataHealthServiceError(f"{field} must be a non-negative integer")
    return value
