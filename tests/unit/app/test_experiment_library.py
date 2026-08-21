from __future__ import annotations

from pathlib import Path

import pytest

from trade_scout.app.experiment_library_service import (
    ExperimentLibraryFilters,
    ExperimentLibraryService,
)
from trade_scout.app.experiment_library_surface import render_experiment_library_html
from trade_scout.experiments.contracts import (
    ExperimentContext,
    ExperimentDefinition,
    ExperimentExecutionError,
    ExperimentStatus,
    ResearchMode,
    StageResult,
)
from trade_scout.experiments.runner import ExperimentRunner
from trade_scout.experiments.store import FileManifestStore


class _Stage:
    name = "strategy_builder"

    def __init__(self, expectancy: float) -> None:
        self._expectancy = expectancy

    def run(self, context: ExperimentContext) -> StageResult:
        return StageResult(
            stage_name=self.name,
            outputs={
                "entry_event_count": 120,
                "complete_event_count": 100,
                "policies": [
                    {
                        "family": "hold_to_horizon",
                        "expectancy_return": self._expectancy,
                    }
                ],
            },
        )


class _FailingStage:
    name = "strategy_builder"

    def run(self, context: ExperimentContext) -> StageResult:
        raise RuntimeError("synthetic analytical failure")


def _definition(
    name: str,
    *,
    family: str,
    parent: str | None = None,
    dataset: str = "dataset-v1",
    code: str = "code-v1",
) -> ExperimentDefinition:
    return ExperimentDefinition(
        name=name,
        hypothesis=f"Hypothesis for {name}",
        mode=ResearchMode.EXPLORATORY,
        dataset_version=dataset,
        universe_version="reviewed_canonical",
        code_version=code,
        config_schema_version="strategy-builder-experiment-v0.1",
        parent_experiment_id=parent,
        resolved_configuration={
            "surface": "visual_strategy_builder",
            "historical_lookback_years": 2,
            "universe": {
                "universe_id": "reviewed_canonical",
                "point_in_time_membership_claimed": False,
            },
            "outcome": {
                "maximum_holding_period_sessions": 20,
                "forced_exit_at_maximum_holding_period": True,
            },
            "entry": {
                "family": family,
                "expression": "return_20 > 0",
                "consolidation_duration_sessions": 20,
                "consolidation_max_range_percent": 12.0,
                "trend_filter": "above_sma_50_100_200",
                "minimum_breakout_volume_ratio": None,
            },
            "selection": {
                "rank_feature": "return_20",
                "rank_direction": "descending",
                "per_session_limit": 500,
            },
            "exit_candidates": {
                "hold_to_horizon_control": True,
                "fixed_stop_percentages": [],
                "trailing_stop_percentages": [],
                "atr_stop_multiples": [],
                "trailing_atr_multiples": [],
            },
            "execution_costs_bps": {
                "entry_slippage": 5.0,
                "normal_exit_slippage": 5.0,
                "additional_stop_slippage": 10.0,
                "commission_per_side": 0.0,
            },
        },
    )


def _seed_plain_manifest_store(root: Path) -> None:
    store = FileManifestStore(root)
    first = ExperimentRunner(store, id_factory=lambda: "exp_parent").run(
        _definition("Parent momentum test", family="feature_expression"),
        (_Stage(0.012),),
    )
    assert first.status is ExperimentStatus.SUCCEEDED
    child = ExperimentRunner(store, id_factory=lambda: "exp_child").run(
        _definition(
            "Child momentum test",
            family="feature_expression",
            parent=first.experiment_id,
            code="code-v2",
        ),
        (_Stage(0.009),),
    )
    assert child.status is ExperimentStatus.SUCCEEDED
    with pytest.raises(ExperimentExecutionError):
        ExperimentRunner(store, id_factory=lambda: "exp_failed").run(
            _definition("Failed breakout test", family="consolidation_breakout"),
            (_FailingStage(),),
        )


def test_library_indexes_existing_plain_manifests_and_keeps_failures(tmp_path: Path) -> None:
    _seed_plain_manifest_store(tmp_path)

    service = ExperimentLibraryService(tmp_path)
    snapshot = service.snapshot()

    assert snapshot.indexed_manifest_count == 3
    assert [item.record.experiment_id for item in snapshot.items] == [
        "exp_failed",
        "exp_child",
        "exp_parent",
    ]
    failed = next(item for item in snapshot.items if item.record.experiment_id == "exp_failed")
    assert failed.record.status is ExperimentStatus.FAILED
    assert failed.failure_type == "RuntimeError"
    assert failed.strategy_family == "consolidation_breakout"


def test_registry_sync_skips_unchanged_manifests_and_reindexes_only_changed_one(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _seed_plain_manifest_store(tmp_path)
    service = ExperimentLibraryService(tmp_path)
    original_register = service._registry.register
    registered: list[str] = []

    def counting_register(manifest) -> None:
        registered.append(manifest.experiment_id)
        original_register(manifest)

    monkeypatch.setattr(service._registry, "register", counting_register)

    first_count, first_warnings = service._synchronize_registry()
    assert first_count == 3
    assert first_warnings == ()
    assert sorted(registered) == ["exp_child", "exp_failed", "exp_parent"]

    second_count, second_warnings = service._synchronize_registry()
    assert second_count == 3
    assert second_warnings == ()
    assert len(registered) == 3

    manifest_path = tmp_path / "exp_parent" / "manifest.json"
    manifest_path.write_text(manifest_path.read_text(encoding="utf-8") + "\n", encoding="utf-8")

    third_count, third_warnings = service._synchronize_registry()
    assert third_count == 3
    assert third_warnings == ()
    assert registered.count("exp_parent") == 2
    assert registered.count("exp_child") == 1
    assert registered.count("exp_failed") == 1


def test_library_filters_text_family_status_dataset_and_code(tmp_path: Path) -> None:
    _seed_plain_manifest_store(tmp_path)
    service = ExperimentLibraryService(tmp_path)

    family = service.snapshot(ExperimentLibraryFilters(strategy_family="feature_expression"))
    assert {item.record.experiment_id for item in family.items} == {"exp_parent", "exp_child"}

    failed = service.snapshot(ExperimentLibraryFilters(status=ExperimentStatus.FAILED))
    assert [item.record.experiment_id for item in failed.items] == ["exp_failed"]

    text = service.snapshot(ExperimentLibraryFilters(text="child momentum"))
    assert [item.record.experiment_id for item in text.items] == ["exp_child"]

    code = service.snapshot(ExperimentLibraryFilters(code_version="code-v2"))
    assert [item.record.experiment_id for item in code.items] == ["exp_child"]

    dataset = service.snapshot(ExperimentLibraryFilters(dataset_version="dataset-v1"))
    assert len(dataset.items) == 3


def test_library_detail_preserves_artifacts_lineage_and_result_summary(tmp_path: Path) -> None:
    _seed_plain_manifest_store(tmp_path)
    service = ExperimentLibraryService(tmp_path)

    detail = service.detail("exp_child")

    assert detail.manifest.experiment_id == "exp_child"
    assert [item.experiment_id for item in detail.lineage] == ["exp_parent", "exp_child"]
    assert detail.stage_outputs[0][0] == "strategy_builder"
    assert detail.result is not None
    assert detail.result.complete_event_count == 100
    assert detail.result.hold_expectancy == pytest.approx(0.009)
    parent = service.detail("exp_parent")
    assert [item.experiment_id for item in parent.children] == ["exp_child"]


def test_library_comparison_is_explicit_and_bounded(tmp_path: Path) -> None:
    _seed_plain_manifest_store(tmp_path)
    service = ExperimentLibraryService(tmp_path)

    compared = service.comparison(("exp_parent", "exp_child"))
    assert [item.manifest.experiment_id for item in compared] == ["exp_parent", "exp_child"]

    with pytest.raises(ValueError, match="between 2 and 4"):
        service.comparison(("exp_parent",))


def test_library_surface_shows_failed_rows_detail_and_non_composite_comparison(
    tmp_path: Path,
) -> None:
    _seed_plain_manifest_store(tmp_path)
    service = ExperimentLibraryService(tmp_path)
    snapshot = service.snapshot()
    detail = service.detail("exp_failed")
    comparison = service.comparison(("exp_parent", "exp_child"))

    html = render_experiment_library_html(
        snapshot=snapshot,
        strategy_families=service.strategy_families(),
        detail=detail,
        comparison=comparison,
        current_dataset_version="dataset-v1",
    )

    assert "Experiment Library" in html
    assert "exp_failed" in html
    assert "synthetic analytical failure" in html
    assert "configuration/result comparison" in html
    assert "does not rank these experiments" in html
    assert "Re-run saved settings" in html
    assert "not presented as an exact historical-code reproduction" in html
