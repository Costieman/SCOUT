"""Historical scanner replay over fixed point-in-time strategy definitions.

Replay deliberately truncates supplied histories at the requested as-of date before invoking the
shared research evaluator. Future rows can therefore be present in storage without becoming
observable to the replayed scanner state.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date
from typing import Protocol

from trade_scout.data.contracts import InstrumentId, QualityStatus, ResearchBar
from trade_scout.experiments.serialization import sha256_json
from trade_scout.scanner.contracts import (
    CandidateStateCount,
    HistoricalReplayResult,
    ReplayInstrumentRecord,
    ReplayInstrumentStatus,
    ReplayObservation,
    ReplayPublicationClass,
    ScanCandidate,
    ScanCandidateState,
    ScannerMode,
    ScanStrategyDefinition,
)


class ScannerEligibilityError(RuntimeError):
    """Raised when normal replay is requested for a non-production strategy."""


class ReplayEvaluator(Protocol):
    """Shared point-in-time analytical implementation used by historical replay."""

    @property
    def feature_set_version(self) -> str:
        """Return the exact feature-set version consumed by this evaluator."""

    def evaluate(
        self,
        bars: tuple[ResearchBar, ...],
        *,
        as_of_date: date,
    ) -> ReplayObservation | None:
        """Evaluate one instrument using only the supplied point-in-time history."""


def run_historical_replay(
    *,
    strategy: ScanStrategyDefinition,
    as_of_date: date,
    universe_version: str,
    eligible_instrument_ids: tuple[InstrumentId, ...],
    bars_by_instrument: Mapping[InstrumentId, tuple[ResearchBar, ...]],
    ticker_display_by_instrument: Mapping[InstrumentId, str],
    evaluator: ReplayEvaluator,
    research_preview: bool = False,
) -> HistoricalReplayResult:
    """Reconstruct what the scanner would have shown on one historical session.

    Normal replay requires explicit production eligibility because it is intended to exercise the
    production-compatible scanner pathway. Non-production strategies may be replayed only through
    the explicit research-preview switch, and every candidate is labelled accordingly.
    """

    if not universe_version.strip():
        raise ValueError("historical replay requires a non-empty universe version")
    if evaluator.feature_set_version != strategy.feature_set_version:
        raise ValueError("replay evaluator feature-set version does not match strategy")
    if len(set(eligible_instrument_ids)) != len(eligible_instrument_ids):
        raise ValueError("historical replay eligible instrument IDs must be unique")

    publication_class = _publication_class(strategy, research_preview=research_preview)
    ordered_instruments = tuple(sorted(eligible_instrument_ids, key=str))
    scan_run_id = _scan_run_id(
        strategy=strategy,
        as_of_date=as_of_date,
        universe_version=universe_version,
        eligible_instrument_ids=ordered_instruments,
        publication_class=publication_class,
    )

    records: list[ReplayInstrumentRecord] = []
    candidates: list[ScanCandidate] = []
    for instrument_id in ordered_instruments:
        series = bars_by_instrument.get(instrument_id, ())
        history = tuple(bar for bar in series if bar.trade_date <= as_of_date)
        record, candidate = _replay_instrument(
            scan_run_id=scan_run_id,
            strategy=strategy,
            publication_class=publication_class,
            as_of_date=as_of_date,
            instrument_id=instrument_id,
            history=history,
            ticker_display=ticker_display_by_instrument.get(instrument_id),
            evaluator=evaluator,
        )
        records.append(record)
        if candidate is not None:
            candidates.append(candidate)

    state_counts = tuple(
        CandidateStateCount(
            state=state,
            count=sum(candidate.candidate_state is state for candidate in candidates),
        )
        for state in ScanCandidateState
    )
    warnings = tuple(
        f"{record.instrument_id}:{record.status.value}:{record.detail}"
        for record in records
        if record.status is not ReplayInstrumentStatus.EVALUATED
    )
    output_checksum = sha256_json(
        {
            "scan_run_id": scan_run_id,
            "instrument_records": records,
            "candidates": candidates,
            "candidate_state_counts": state_counts,
            "warnings": warnings,
        }
    )
    return HistoricalReplayResult(
        scan_run_id=scan_run_id,
        mode=ScannerMode.REPLAY,
        replay_publication_class=publication_class,
        as_of_date=as_of_date,
        dataset_version=strategy.dataset_version,
        universe_version=universe_version,
        feature_set_version=strategy.feature_set_version,
        strategy_family_id=strategy.strategy_family_id,
        strategy_version=strategy.strategy_version,
        evidence_profile_id=strategy.evidence_profile_id,
        evidence_package_checksum=strategy.evidence_package_checksum,
        risk_policy_id=strategy.risk_policy_id,
        rank_model_version=strategy.rank_model_version,
        code_version=strategy.code_version,
        config_schema_version=strategy.config_schema_version,
        eligible_instrument_ids=ordered_instruments,
        instrument_records=tuple(records),
        candidates=tuple(candidates),
        candidate_state_counts=state_counts,
        output_checksum=output_checksum,
        warnings=warnings,
    )


def _publication_class(
    strategy: ScanStrategyDefinition,
    *,
    research_preview: bool,
) -> ReplayPublicationClass:
    if research_preview:
        return ReplayPublicationClass.RESEARCH_PREVIEW
    if not strategy.production_eligible:
        raise ScannerEligibilityError(
            "production-compatible replay requires an explicit PRODUCTION-ELIGIBLE strategy decision"
        )
    return ReplayPublicationClass.PRODUCTION_COMPATIBLE


def _scan_run_id(
    *,
    strategy: ScanStrategyDefinition,
    as_of_date: date,
    universe_version: str,
    eligible_instrument_ids: tuple[InstrumentId, ...],
    publication_class: ReplayPublicationClass,
) -> str:
    checksum = sha256_json(
        {
            "mode": ScannerMode.REPLAY,
            "publication_class": publication_class,
            "as_of_date": as_of_date.isoformat(),
            "dataset_version": strategy.dataset_version,
            "universe_version": universe_version,
            "feature_set_version": strategy.feature_set_version,
            "strategy_family_id": strategy.strategy_family_id,
            "strategy_version": strategy.strategy_version,
            "evidence_profile_id": strategy.evidence_profile_id,
            "evidence_package_checksum": strategy.evidence_package_checksum,
            "risk_policy_id": strategy.risk_policy_id,
            "rank_model_version": strategy.rank_model_version,
            "code_version": strategy.code_version,
            "config_schema_version": strategy.config_schema_version,
            "eligible_instrument_ids": [str(item) for item in eligible_instrument_ids],
        }
    )
    return f"scanner_replay_{checksum[:20]}"


def _replay_instrument(
    *,
    scan_run_id: str,
    strategy: ScanStrategyDefinition,
    publication_class: ReplayPublicationClass,
    as_of_date: date,
    instrument_id: InstrumentId,
    history: tuple[ResearchBar, ...],
    ticker_display: str | None,
    evaluator: ReplayEvaluator,
) -> tuple[ReplayInstrumentRecord, ScanCandidate | None]:
    if not history:
        return _blocked_record(
            instrument_id,
            ReplayInstrumentStatus.BLOCKED_MISSING_HISTORY,
            latest_available_date=None,
            detail="no point-in-time history is available through the replay session",
        )
    _validate_history_identity(history, instrument_id)
    latest = history[-1]
    if str(latest.dataset_version) != strategy.dataset_version:
        return _blocked_record(
            instrument_id,
            ReplayInstrumentStatus.BLOCKED_DATASET_MISMATCH,
            latest_available_date=latest.trade_date,
            detail=(
                f"latest dataset version {latest.dataset_version} does not match "
                f"strategy dataset {strategy.dataset_version}"
            ),
        )
    if latest.trade_date != as_of_date:
        return _blocked_record(
            instrument_id,
            ReplayInstrumentStatus.BLOCKED_MISSING_AS_OF_SESSION,
            latest_available_date=latest.trade_date,
            detail="latest point-in-time bar does not reach the requested replay session",
        )
    if not latest.eligibility or latest.quality_status is not QualityStatus.PASS:
        return _blocked_record(
            instrument_id,
            ReplayInstrumentStatus.BLOCKED_QUALITY,
            latest_available_date=latest.trade_date,
            detail=("requested replay session is not both universe-eligible and quality PASS"),
        )
    if ticker_display is None or not ticker_display.strip():
        return _blocked_record(
            instrument_id,
            ReplayInstrumentStatus.BLOCKED_MISSING_SYMBOL,
            latest_available_date=latest.trade_date,
            detail="point-in-time ticker display is unavailable for the replay session",
        )

    observation = evaluator.evaluate(history, as_of_date=as_of_date)
    if observation is None:
        return (
            ReplayInstrumentRecord(
                instrument_id=instrument_id,
                status=ReplayInstrumentStatus.EVALUATED,
                latest_available_date=latest.trade_date,
                candidate_id=None,
                detail="eligible instrument evaluated with no scanner candidate",
            ),
            None,
        )
    if observation.source_date != as_of_date:
        raise ValueError("replay evaluator returned an observation from a different session")
    if observation.quality_status is not QualityStatus.PASS:
        raise ValueError("replay evaluator candidate must retain quality PASS")

    candidate_id = _candidate_id(
        scan_run_id=scan_run_id,
        instrument_id=instrument_id,
        observation=observation,
    )
    candidate = ScanCandidate(
        candidate_id=candidate_id,
        scan_run_id=scan_run_id,
        as_of_date=as_of_date,
        instrument_id=instrument_id,
        ticker_display=ticker_display,
        strategy_family_id=strategy.strategy_family_id,
        strategy_version=strategy.strategy_version,
        pattern_instance_id=observation.pattern_instance_id,
        event_id=observation.event_id,
        candidate_state=observation.candidate_state,
        current_feature_snapshot=observation.feature_snapshot,
        structural_levels=observation.structural_levels,
        evidence_profile_id=strategy.evidence_profile_id,
        risk_policy_id=strategy.risk_policy_id,
        rank_model_version=strategy.rank_model_version,
        rank_score=None,
        rank_components=(),
        data_freshness="POINT_IN_TIME_COMPLETE",
        quality_status=observation.quality_status,
        dataset_version=strategy.dataset_version,
        replay_publication_class=publication_class,
        reasons=observation.reasons,
    )
    return (
        ReplayInstrumentRecord(
            instrument_id=instrument_id,
            status=ReplayInstrumentStatus.EVALUATED,
            latest_available_date=latest.trade_date,
            candidate_id=candidate_id,
            detail="eligible instrument evaluated and candidate emitted",
        ),
        candidate,
    )


def _blocked_record(
    instrument_id: InstrumentId,
    status: ReplayInstrumentStatus,
    *,
    latest_available_date: date | None,
    detail: str,
) -> tuple[ReplayInstrumentRecord, None]:
    return (
        ReplayInstrumentRecord(
            instrument_id=instrument_id,
            status=status,
            latest_available_date=latest_available_date,
            candidate_id=None,
            detail=detail,
        ),
        None,
    )


def _validate_history_identity(
    history: tuple[ResearchBar, ...],
    instrument_id: InstrumentId,
) -> None:
    if any(bar.instrument_id != instrument_id for bar in history):
        raise ValueError("replay history contains a different instrument identity")
    dates = tuple(bar.trade_date for bar in history)
    if dates != tuple(sorted(dates)) or len(dates) != len(set(dates)):
        raise ValueError("replay history must be unique and date-increasing through as-of")
    representations = {bar.price_representation for bar in history}
    if len(representations) != 1:
        raise ValueError("replay history cannot mix price representations")


def _candidate_id(
    *,
    scan_run_id: str,
    instrument_id: InstrumentId,
    observation: ReplayObservation,
) -> str:
    checksum = sha256_json(
        {
            "scan_run_id": scan_run_id,
            "instrument_id": str(instrument_id),
            "pattern_instance_id": observation.pattern_instance_id,
            "event_id": observation.event_id,
            "candidate_state": observation.candidate_state,
        }
    )
    return f"scan_candidate_{checksum[:20]}"
