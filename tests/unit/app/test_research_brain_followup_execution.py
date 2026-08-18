from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest

from trade_scout.app.entry_strategy_registry import EntryFamily
from trade_scout.app.research_brain_followup_execution import (
    ResearchBrainFollowUpExecutionError,
)
from trade_scout.app.research_brain_service import ResearchBrainWorkbenchService
from trade_scout.app.research_brain_surface import render_research_brains_html
from trade_scout.app.strategy_builder_entry_sweep import EntrySweepParameter
from trade_scout.app.strategy_builder_experiments import StrategyBuilderExperimentRecorder
from trade_scout.app.strategy_builder_service import StrategyBuilderRequest
from trade_scout.app.universe_research_service import UniverseOption
from trade_scout.data.contracts import DailyBar, DatasetVersion, InstrumentId, QualityStatus
from trade_scout.experiments.store import FileManifestStore
from trade_scout.features.parameterized_indicators import (
    IndicatorFamily,
    IndicatorMetric,
    ParameterizedIndicatorSpec,
)

_DATASET = "brain-execution-dataset-v1"


def _daily(instrument_id: str, index: int, *, offset: int) -> DailyBar:
    close = 50.0 + offset + index * 0.03
    volume = 8_000_000.0 if index % 60 == 0 else 1_000_000.0
    return DailyBar(
        instrument_id=InstrumentId(instrument_id),
        trade_date=date(2024, 1, 1) + timedelta(days=index),
        open_raw=close,
        high_raw=close + 0.4,
        low_raw=close - 0.4,
        close_raw=close,
        volume_raw=volume,
        split_factor=1.0,
        dividend_cash=0.0,
        open_split_adjusted=close,
        high_split_adjusted=close + 0.4,
        low_split_adjusted=close - 0.4,
        close_split_adjusted=close,
        provider_id="synthetic",
        dataset_version=DatasetVersion(_DATASET),
        quality_status=QualityStatus.PASS,
    )


@dataclass(frozen=True)
class _WindowedSource:
    daily: tuple[DailyBar, ...]

    def available_universes(self) -> tuple[UniverseOption, ...]:
        return (UniverseOption("reviewed_canonical", "Synthetic reviewed cohort", False),)

    def research_series(self, universe_id: str):
        raise AssertionError("windowed follow-up execution must not load full research_series")

    def canonical_daily_bars(self, universe_id: str):
        raise AssertionError("windowed follow-up execution must not load all canonical bars")

    def strategy_builder_latest_trade_date(self, universe_id: str) -> date:
        assert universe_id == "reviewed_canonical"
        return max(item.trade_date for item in self.daily)

    def strategy_builder_dataset_record_count(self, universe_id: str) -> int:
        assert universe_id == "reviewed_canonical"
        return len(self.daily)

    def strategy_builder_daily_bars(
        self,
        universe_id: str,
        *,
        signal_start: date,
        signal_end: date,
        warmup_observations: int,
    ) -> tuple[DailyBar, ...]:
        assert universe_id == "reviewed_canonical"
        selected: list[DailyBar] = []
        instruments = sorted({str(item.instrument_id) for item in self.daily})
        for instrument_id in instruments:
            rows = tuple(item for item in self.daily if str(item.instrument_id) == instrument_id)
            before = tuple(item for item in rows if item.trade_date < signal_start)
            warmup = before[-warmup_observations:]
            active = tuple(item for item in rows if signal_start <= item.trade_date <= signal_end)
            selected.extend((*warmup, *active))
        return tuple(sorted(selected, key=lambda item: (str(item.instrument_id), item.trade_date)))


def _source() -> _WindowedSource:
    rows = [
        *(_daily("brain_exec_a", index, offset=0) for index in range(800)),
        *(_daily("brain_exec_b", index, offset=20) for index in range(800)),
    ]
    return _WindowedSource(tuple(rows))


def _recorder(tmp_path: Path) -> StrategyBuilderExperimentRecorder:
    return StrategyBuilderExperimentRecorder(
        experiment_root=tmp_path / "research" / "experiments",
        dataset_version=_DATASET,
        code_version="test-code-v1",
    )


def _service(tmp_path: Path) -> ResearchBrainWorkbenchService:
    return ResearchBrainWorkbenchService(
        experiment_root=tmp_path / "research" / "experiments",
        brain_root=tmp_path / "research" / "brains",
    )


def _plain_request() -> StrategyBuilderRequest:
    return StrategyBuilderRequest(
        entry_family=EntryFamily.FEATURE_EXPRESSION,
        expression="relative_volume_20 > 2",
        rank_feature="return_20",
        per_session_limit=500,
        horizon=5,
        lookback_years=1,
        fixed_percentages=(),
        atr_multiples=(),
        trailing_percentages=(),
        trailing_atr_multiples=(),
        entry_slippage_bps=5.0,
        exit_slippage_bps=5.0,
    )


def _prepare_approved_plain(
    tmp_path: Path,
) -> tuple[
    _WindowedSource,
    StrategyBuilderExperimentRecorder,
    ResearchBrainWorkbenchService,
    str,
    str,
]:
    source = _source()
    recorder = _recorder(tmp_path)
    run = recorder.run_strategy(source, _plain_request())
    service = _service(tmp_path)
    brain = service.create_brain(
        brain_id="brain_execution",
        name="Execution brain",
        research_question="Does this entry timing add information beyond random eligible timing?",
        created_by="local-user",
        created_at=datetime(2026, 8, 18, 10, 0, tzinfo=UTC),
    )
    service.add_experiment(
        brain_id=brain.brain_id,
        experiment_id=run.manifest.experiment_id,
        added_by="local-user",
        added_at=datetime(2026, 8, 18, 10, 1, tzinfo=UTC),
    )
    proposal = service.draft_follow_up_proposal(
        brain_id=brain.brain_id,
        created_by="local-user",
        created_at=datetime(2026, 8, 18, 10, 2, tzinfo=UTC),
    )
    service.approve_follow_up_proposal(
        brain_id=brain.brain_id,
        proposal_id=proposal.proposal_id,
        approved_by="local-user",
        approved_at=datetime(2026, 8, 18, 10, 3, tzinfo=UTC),
    )
    return source, recorder, service, brain.brain_id, proposal.proposal_id


def test_executor_requires_explicit_approval(tmp_path: Path) -> None:
    source = _source()
    recorder = _recorder(tmp_path)
    run = recorder.run_strategy(source, _plain_request())
    service = _service(tmp_path)
    brain = service.create_brain(
        brain_id="brain_unapproved",
        name="Unapproved brain",
        research_question="Should this be compared with randomized timing?",
        created_by="local-user",
        created_at=datetime(2026, 8, 18, 9, 0, tzinfo=UTC),
    )
    service.add_experiment(
        brain_id=brain.brain_id,
        experiment_id=run.manifest.experiment_id,
        added_by="local-user",
    )
    proposal = service.draft_follow_up_proposal(
        brain_id=brain.brain_id,
        created_by="local-user",
    )

    with pytest.raises(ResearchBrainFollowUpExecutionError, match="explicitly approved"):
        service.execute_follow_up_comparator(
            brain_id=brain.brain_id,
            proposal_id=proposal.proposal_id,
            executed_by="local-user",
            recorder=recorder,
            source=source,
        )


def test_approved_comparator_runs_as_child_and_returns_result_to_same_brain(
    tmp_path: Path,
) -> None:
    source, recorder, service, brain_id, proposal_id = _prepare_approved_plain(tmp_path)

    receipt = service.execute_follow_up_comparator(
        brain_id=brain_id,
        proposal_id=proposal_id,
        executed_by="local-user",
        recorder=recorder,
        source=source,
        executed_at=datetime(2026, 8, 18, 10, 4, tzinfo=UTC),
    )

    manifest_store = FileManifestStore(recorder.experiment_root)
    child = manifest_store.read_manifest(receipt.result_experiment_id)
    output = manifest_store.read_stage_output(
        child.experiment_id,
        "research_brain_random_timing_comparator",
    )
    detail = service.detail(brain_id)
    membership_ids = {item.experiment_id for item in detail.snapshot.memberships}

    assert child.status.value == "SUCCEEDED"
    assert child.definition.parent_experiment_id is not None
    assert output["comparator_kind"] == "same_instrument_random_eligible_timing"
    assert isinstance(output["p_value"], float)
    assert output["provider_calls_made"] is False
    assert child.experiment_id in membership_ids
    assert receipt.auto_attached_to_brain is True
    assert detail.follow_up_executions[0].result_experiment_id == child.experiment_id
    assert detail.follow_up_proposals[0].stale is True

    repeated = service.execute_follow_up_comparator(
        brain_id=brain_id,
        proposal_id=proposal_id,
        executed_by="another-user",
        recorder=recorder,
        source=source,
    )
    assert repeated == receipt
    assert (
        sum(item.experiment_id == child.experiment_id for item in detail.snapshot.memberships) == 1
    )


def test_brain_change_after_approval_blocks_execution(tmp_path: Path) -> None:
    source, recorder, service, brain_id, proposal_id = _prepare_approved_plain(tmp_path)
    another = recorder.run_strategy(
        source,
        replace(_plain_request(), expression="relative_volume_20 > 3"),
    )
    service.add_experiment(
        brain_id=brain_id,
        experiment_id=another.manifest.experiment_id,
        added_by="local-user",
    )

    with pytest.raises(ResearchBrainFollowUpExecutionError, match="stale"):
        service.execute_follow_up_comparator(
            brain_id=brain_id,
            proposal_id=proposal_id,
            executed_by="local-user",
            recorder=recorder,
            source=source,
        )


def test_sweep_source_requires_operator_to_freeze_one_declared_candidate(
    tmp_path: Path,
) -> None:
    source = _source()
    recorder = _recorder(tmp_path)
    ma = ParameterizedIndicatorSpec(
        family=IndicatorFamily.MOVING_AVERAGE,
        metric=IndicatorMetric.MA_DISTANCE_PCT,
        period=20,
    )
    request = StrategyBuilderRequest(
        entry_family=EntryFamily.FEATURE_EXPRESSION,
        expression=f"{ma.feature_name} > 0",
        rank_feature="return_20",
        per_session_limit=500,
        horizon=5,
        lookback_years=1,
        fixed_percentages=(),
        atr_multiples=(),
        trailing_percentages=(),
        trailing_atr_multiples=(),
    )
    run = recorder.run_entry_sweep(
        source,
        request,
        target_feature_name=ma.feature_name,
        parameter=EntrySweepParameter.PERIOD,
        values=(10.0, 20.0, 30.0),
    )
    service = _service(tmp_path)
    brain = service.create_brain(
        brain_id="brain_sweep_execution",
        name="Sweep execution brain",
        research_question="Which saved sweep candidate should receive a timing comparator?",
        created_by="local-user",
    )
    service.add_experiment(
        brain_id=brain.brain_id,
        experiment_id=run.manifest.experiment_id,
        added_by="local-user",
    )
    proposal = service.draft_follow_up_proposal(
        brain_id=brain.brain_id,
        created_by="local-user",
    )
    service.approve_follow_up_proposal(
        brain_id=brain.brain_id,
        proposal_id=proposal.proposal_id,
        approved_by="local-user",
    )

    with pytest.raises(ResearchBrainFollowUpExecutionError, match="choose one"):
        service.execute_follow_up_comparator(
            brain_id=brain.brain_id,
            proposal_id=proposal.proposal_id,
            executed_by="local-user",
            recorder=recorder,
            source=source,
        )
    with pytest.raises(ValueError, match="was not part of the source declared sweep"):
        service.execute_follow_up_comparator(
            brain_id=brain.brain_id,
            proposal_id=proposal.proposal_id,
            executed_by="local-user",
            recorder=recorder,
            source=source,
            candidate_value=25.0,
        )

    html = render_research_brains_html(
        brains=service.list_brains(),
        detail=service.detail(brain.brain_id),
    )
    assert "Run approved comparator" in html
    assert 'value="10"' in html
    assert 'value="20"' in html
    assert 'value="30"' in html
    assert "does not select the historical maximum" in html
