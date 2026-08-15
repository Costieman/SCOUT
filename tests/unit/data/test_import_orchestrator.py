from pathlib import Path

import pytest

from trade_scout.data.import_orchestrator import (
    ImportOrchestrationError,
    ImportProgressEvent,
    ImportStage,
    ImportStageStatus,
    run_import_pipeline,
)


def _stages() -> tuple[ImportStage, ...]:
    return (
        ImportStage("one", "Stage one", ("python", "one.py")),
        ImportStage("two", "Stage two", ("python", "two.py")),
        ImportStage("three", "Stage three", ("python", "three.py")),
    )


def test_pipeline_runs_all_stages_and_persists_state(tmp_path: Path) -> None:
    commands: list[tuple[str, ...]] = []
    events: list[ImportProgressEvent] = []

    def runner(command: tuple[str, ...], *, cwd: Path) -> int:
        assert cwd == tmp_path.resolve()
        commands.append(command)
        return 0

    state = run_import_pipeline(
        repository_root=tmp_path,
        workspace_root=tmp_path / "workspace",
        provider="tiingo",
        universe="sp500",
        stages=_stages(),
        runner=runner,
        progress_sink=events.append,
    )

    assert commands == [item.command for item in _stages()]
    assert all(item.status is ImportStageStatus.SUCCEEDED for item in state.stages)
    assert [event.status for event in events] == [
        ImportStageStatus.RUNNING,
        ImportStageStatus.SUCCEEDED,
        ImportStageStatus.RUNNING,
        ImportStageStatus.SUCCEEDED,
        ImportStageStatus.RUNNING,
        ImportStageStatus.SUCCEEDED,
    ]
    assert (
        tmp_path / "workspace" / "evidence" / "import-runs" / "tiingo-sp500" / "state.json"
    ).is_file()


def test_resume_skips_succeeded_stages(tmp_path: Path) -> None:
    attempts = 0

    def first_runner(command: tuple[str, ...], *, cwd: Path) -> int:
        nonlocal attempts
        del command, cwd
        attempts += 1
        return 9 if attempts == 2 else 0

    with pytest.raises(ImportOrchestrationError):
        run_import_pipeline(
            repository_root=tmp_path,
            workspace_root=tmp_path / "workspace",
            provider="tiingo",
            universe="sp500",
            stages=_stages(),
            runner=first_runner,
            progress_sink=lambda event: None,
        )

    resumed_commands: list[tuple[str, ...]] = []
    resumed_events: list[ImportProgressEvent] = []

    def resumed_runner(command: tuple[str, ...], *, cwd: Path) -> int:
        del cwd
        resumed_commands.append(command)
        return 0

    final = run_import_pipeline(
        repository_root=tmp_path,
        workspace_root=tmp_path / "workspace",
        provider="tiingo",
        universe="sp500",
        stages=_stages(),
        runner=resumed_runner,
        progress_sink=resumed_events.append,
    )

    assert resumed_commands == [_stages()[1].command, _stages()[2].command]
    assert resumed_events[0].stage_id == "one"
    assert resumed_events[0].status is ImportStageStatus.SKIPPED
    assert all(item.status is ImportStageStatus.SUCCEEDED for item in final.stages)


def test_restart_reexecutes_succeeded_stages(tmp_path: Path) -> None:
    def success(command: tuple[str, ...], *, cwd: Path) -> int:
        del command, cwd
        return 0

    run_import_pipeline(
        repository_root=tmp_path,
        workspace_root=tmp_path / "workspace",
        provider="tiingo",
        universe="sp500",
        stages=_stages(),
        runner=success,
        progress_sink=lambda event: None,
    )

    rerun: list[tuple[str, ...]] = []

    def capture(command: tuple[str, ...], *, cwd: Path) -> int:
        del cwd
        rerun.append(command)
        return 0

    run_import_pipeline(
        repository_root=tmp_path,
        workspace_root=tmp_path / "workspace",
        provider="tiingo",
        universe="sp500",
        stages=_stages(),
        runner=capture,
        progress_sink=lambda event: None,
        restart=True,
    )

    assert rerun == [item.command for item in _stages()]
