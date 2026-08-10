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
    ProvenanceSummary,
    ProviderHealthSummary,
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

    missing_count, discrepancy_count, review_count = _composite_counts(
        sources.composite_evidence_paths
    )
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

    phase_blockers = _phase_blockers(
        tiingo_assessment=tiingo_assessment,
        tiingo_state=tiingo_state,
        canonical=canonical,
        review_count=review_count,
        corporate_action_count=corporate_action_count,
        failed_job_count=failed_job_count,
        scanner_gate=scanner_gate,
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
        review_work_item_count=review_count,
        phase_blockers=phase_blockers,
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
        operational_status = "STATE_NOT_SUPPLIED"
        last_observed_at = None
        quota_pause_count = None
        failure_count = None
        last_rate_limited_symbol = None
        last_failed_symbol = None
        last_failure_type = None
    else:
        current = state.durable_completed_symbol_count
        total = state.total_symbol_count
        operational_status = state.last_status
        last_observed_at = state.last_run_at
        quota_pause_count = state.quota_pause_count
        failure_count = state.failure_count
        last_rate_limited_symbol = state.last_rate_limited_symbol
        last_failed_symbol = state.last_failed_symbol
        last_failure_type = state.last_failure_type
        message = (
            f"{decision}; durable campaign {current}/{total}; last status {state.last_status}."
        )
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
        operational_status=operational_status,
        last_observed_at=last_observed_at,
        quota_pause_count=quota_pause_count,
        failure_count=failure_count,
        last_rate_limited_symbol=last_rate_limited_symbol,
        last_failed_symbol=last_failed_symbol,
        last_failure_type=last_failure_type,
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
        operational_status=_criterion_status(
            free_stack,
            "alpha_vantage_point_in_time_listing_status",
        ),
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
        operational_status=_criterion_status(free_stack, "stooq_historical_ohlcv_retrieval"),
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


def _phase_blockers(
    *,
    tiingo_assessment: dict[str, object],
    tiingo_state: TiingoSafeCampaignState | None,
    canonical: CanonicalDatasetManifest | None,
    review_count: int | None,
    corporate_action_count: int | None,
    failed_job_count: int | None,
    scanner_gate: HealthState,
) -> tuple[str, ...]:
    blockers: list[str] = []
    decision = _required_text(tiingo_assessment.get("decision"), "Tiingo decision")
    if decision != "ACCEPTED":
        blockers.append(f"Tiingo baseline provider decision remains {decision}.")
    if tiingo_state is None:
        blockers.append("Durable Tiingo S&P 500 acquisition state is not available to the console.")
    elif tiingo_state.durable_pending_symbol_count:
        blockers.append(
            "Durable Tiingo acquisition is incomplete: "
            f"{tiingo_state.durable_completed_symbol_count}/{tiingo_state.total_symbol_count} "
            "symbols secured."
        )
    if review_count is None:
        blockers.append("Cross-provider reconciliation evidence has not been supplied.")
    elif review_count:
        blockers.append(f"Cross-provider reconciliation has {review_count} review items outstanding.")
    if corporate_action_count is None:
        blockers.append("Corporate-action anomaly evidence has not been supplied to Data Health.")
    elif corporate_action_count:
        blockers.append(f"Corporate-action review has {corporate_action_count} open anomalies.")
    if failed_job_count:
        blockers.append(f"There are {failed_job_count} failed ingestion job markers.")
    if canonical is None:
        blockers.append("No canonical Phase 1 dataset has been explicitly selected and promoted.")
    elif scanner_gate is not HealthState.PASS:
        blockers.append(f"Scanner freshness gate is {scanner_gate.value}, not PASS.")
    return tuple(blockers)


def _composite_counts(paths: tuple[Path, ...]) -> tuple[int | None, int | None, int | None]:
    if not paths:
        return None, None, None
    missing = 0
    discrepancies = 0
    reviews = 0
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
            a_only = _required_nonnegative_int(summary.get("a_only_count"), "a_only_count")
            b_only = _required_nonnegative_int(summary.get("b_only_count"), "b_only_count")
            disagree = _required_nonnegative_int(
                summary.get("both_disagree_count"),
                "both_disagree_count",
            )
            missing += a_only + b_only
            discrepancies += disagree
            reviews += a_only + b_only + disagree
    return missing, discrepancies, reviews


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
    item = _criterion(payload, criterion_name)
    return _required_text(item.get("note"), f"criterion note {criterion_name}")


def _criterion_status(payload: dict[str, object], criterion_name: str) -> str | None:
    item = _criterion(payload, criterion_name)
    status = item.get("status")
    if status is None:
        return None
    return _required_text(status, f"criterion status {criterion_name}")


def _criterion(payload: dict[str, object], criterion_name: str) -> dict[str, object]:
    criteria = payload.get("criteria")
    if not isinstance(criteria, list):
        raise DataHealthServiceError("provider assessment lacks criteria array")
    for item in criteria:
        if isinstance(item, dict) and item.get("criterion") == criterion_name:
            return item
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
