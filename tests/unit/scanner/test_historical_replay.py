from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

import pytest

from trade_scout.data.contracts import (
    DatasetVersion,
    InstrumentId,
    PriceRepresentation,
    QualityStatus,
    ResearchBar,
)
from trade_scout.experiments.decisions import (
    ProductionEligibilityAttestation,
    ResearchDecision,
    ResearchDecisionState,
)
from trade_scout.scanner import (
    ReplayInstrumentStatus,
    ReplayObservation,
    ReplayPublicationClass,
    ScanCandidateState,
    ScannerEligibilityError,
    ScanStrategyDefinition,
    SnapshotField,
    StructuralLevel,
    run_historical_replay,
)


@dataclass(frozen=True, slots=True)
class LastBarEvaluator:
    feature_set_version: str = "feature-set-test-v1"

    def evaluate(
        self,
        bars: tuple[ResearchBar, ...],
        *,
        as_of_date: date,
    ) -> ReplayObservation | None:
        bar = bars[-1]
        if bar.close < 100:
            return None
        return ReplayObservation(
            source_date=as_of_date,
            pattern_instance_id=f"pattern:{bar.instrument_id}",
            candidate_state=ScanCandidateState.QUALIFIED,
            feature_snapshot=(SnapshotField("close", bar.close),),
            structural_levels=(StructuralLevel("resistance", 99.0),),
            quality_status=QualityStatus.PASS,
            reasons=("test qualified state",),
        )


def _decision(state: ResearchDecisionState) -> ResearchDecision:
    attestation = None
    if state is ResearchDecisionState.PRODUCTION_ELIGIBLE:
        attestation = ProductionEligibilityAttestation(
            implementation_compatible=True,
            cost_assumptions_acceptable=True,
            liquidity_assumptions_acceptable=True,
            risk_policy_validated=True,
            operational_dependencies_available=True,
        )
    return ResearchDecision(
        decision_id=f"decision-{state.value}",
        subject_id="strategy-v1",
        state=state,
        experiment_ids=("experiment-1",),
        evidence_references=("research-evidence-1",),
        rationale="test decision",
        decided_by="test-suite",
        decided_at="2026-08-15T00:00:00Z",
        production_attestation=attestation,
    )


def _strategy(state: ResearchDecisionState) -> ScanStrategyDefinition:
    return ScanStrategyDefinition(
        strategy_family_id="consolidation-breakout",
        strategy_version="strategy-v1",
        dataset_version="dataset-v1",
        feature_set_version="feature-set-test-v1",
        evidence_profile_id="evidence-profile-v1",
        evidence_package_checksum="abc123",
        code_version="code-v1",
        config_schema_version="config-v1",
        eligibility_decision=_decision(state),
    )


def _bar(
    index: int,
    *,
    close: float = 101.0,
    quality: QualityStatus = QualityStatus.PASS,
    eligibility: bool = True,
) -> ResearchBar:
    return ResearchBar(
        instrument_id=InstrumentId("instrument-1"),
        trade_date=date(2024, 1, 2) + timedelta(days=index),
        open=close,
        high=close + 1,
        low=close - 1,
        close=close,
        volume=1_000_000.0,
        eligibility=eligibility,
        quality_status=quality,
        dataset_version=DatasetVersion("dataset-v1"),
        price_representation=PriceRepresentation.SPLIT_ADJUSTED,
    )


def _run(
    bars: tuple[ResearchBar, ...],
    *,
    strategy: ScanStrategyDefinition | None = None,
    research_preview: bool = False,
    as_of_date: date | None = None,
):
    instrument = InstrumentId("instrument-1")
    return run_historical_replay(
        strategy=strategy or _strategy(ResearchDecisionState.PRODUCTION_ELIGIBLE),
        as_of_date=as_of_date or bars[-1].trade_date,
        universe_version="universe-v1",
        eligible_instrument_ids=(instrument,),
        bars_by_instrument={instrument: bars},
        ticker_display_by_instrument={instrument: "TEST"},
        evaluator=LastBarEvaluator(),
        research_preview=research_preview,
    )


def test_normal_replay_requires_production_eligible_strategy() -> None:
    bars = tuple(_bar(index) for index in range(3))

    with pytest.raises(ScannerEligibilityError, match="PRODUCTION-ELIGIBLE"):
        _run(bars, strategy=_strategy(ResearchDecisionState.CANDIDATE))


def test_explicit_research_preview_allows_nonproduction_strategy_and_labels_output() -> None:
    bars = tuple(_bar(index) for index in range(3))
    result = _run(
        bars,
        strategy=_strategy(ResearchDecisionState.CANDIDATE),
        research_preview=True,
    )

    assert result.replay_publication_class is ReplayPublicationClass.RESEARCH_PREVIEW
    assert len(result.candidates) == 1
    assert result.candidates[0].replay_publication_class is ReplayPublicationClass.RESEARCH_PREVIEW


def test_future_rows_are_not_visible_to_historical_replay() -> None:
    prefix = tuple(_bar(index) for index in range(3))
    future = (*prefix, _bar(3, close=50.0), _bar(4, close=40.0))
    as_of_date = prefix[-1].trade_date

    first = _run(prefix, as_of_date=as_of_date)
    second = _run(future, as_of_date=as_of_date)

    assert first.scan_run_id == second.scan_run_id
    assert first.output_checksum == second.output_checksum
    assert first.candidates == second.candidates


def test_missing_as_of_session_is_blocked_not_treated_as_no_candidate() -> None:
    bars = tuple(_bar(index) for index in range(2))
    result = _run(bars, as_of_date=bars[-1].trade_date + timedelta(days=1))

    assert result.candidates == ()
    assert (
        result.instrument_records[0].status is ReplayInstrumentStatus.BLOCKED_MISSING_AS_OF_SESSION
    )
    assert result.warnings


def test_current_quality_failure_is_blocked_explicitly() -> None:
    bars = (_bar(0), _bar(1, quality=QualityStatus.QUARANTINE))
    result = _run(bars)

    assert result.candidates == ()
    assert result.instrument_records[0].status is ReplayInstrumentStatus.BLOCKED_QUALITY


def test_no_candidate_remains_distinct_from_blocked_evaluation() -> None:
    bars = (_bar(0), _bar(1, close=95.0))
    result = _run(bars)

    assert result.candidates == ()
    assert result.instrument_records[0].status is ReplayInstrumentStatus.EVALUATED
    assert not result.warnings
