"""Resumable orchestration for provider/universe import workflows.

The orchestrator owns stage sequencing, durable run state, progress events, and restart behavior.
It deliberately contains no provider parsing, identity adjudication, normalization, or promotion logic.
Those responsibilities remain in the existing domain modules and narrow operational entry points.
"""

from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Callable, Protocol


class ImportOrchestrationError(RuntimeError):
    """Raised when an import stage fails or the persisted run state is invalid."""


class ImportStageStatus(StrEnum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"


@dataclass(frozen=True, slots=True)
class ImportStage:
    stage_id: str
    label: str
    command: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ImportStageRecord:
    stage_id: str
    label: str
    status: ImportStageStatus
    started_at: str | None = None
    finished_at: str | None = None
    returncode: int | None = None


@dataclass(frozen=True, slots=True)
class ImportProgressEvent:
    run_id: str
    provider: str
    universe: str
    stage_index: int
    stage_count: int
    stage_id: str
    stage_label: str
    status: ImportStageStatus
    message: str


@dataclass(frozen=True, slots=True)
class ImportRunState:
    schema_version: str
    run_id: str
    provider: str
    universe: str
    root: str
    created_at: str
    updated_at: str
    stages: tuple[ImportStageRecord, ...]


class CommandRunner(Protocol):
    def __call__(self, command: tuple[str, ...], *, cwd: Path) -> int: ...


ProgressSink = Callable[[ImportProgressEvent], None]


def tiingo_sp500_stage_plan(
    *, repository_root: Path, workspace_root: Path, sec_sleep: float = 0.6
) -> tuple[ImportStage, ...]:
    """Return the current Tiingo/S&P 500 import pipeline as explicit resumable stages."""

    python = sys.executable
    root = str(workspace_root)
    scripts = repository_root / "scripts"
    return (
        ImportStage(
            "profile",
            "Profile durable provider history",
            (python, str(scripts / "trade_scout_workspace.py"), "profile-tiingo", "--root", root),
        ),
        ImportStage(
            "review_queue",
            "Build unresolved identity queue",
            (
                python,
                str(scripts / "prepare_tiingo_identity_review_queue.py"),
                "--root",
                root,
                "--limit",
                "5000",
            ),
        ),
        ImportStage(
            "primary_identity",
            "Resolve primary identity evidence",
            (
                python,
                str(scripts / "run_tiingo_overnight_import.py"),
                "--root",
                root,
                "--sleep",
                str(sec_sleep),
            ),
        ),
        ImportStage(
            "deferred_identity",
            "Resolve deferred identity boundaries",
            (
                python,
                str(scripts / "resolve_tiingo_deferred_identities.py"),
                "--root",
                root,
                "--sleep",
                str(sec_sleep),
                "--restart",
            ),
        ),
        ImportStage(
            "historical_identity",
            "Resolve historical campaign-boundary evidence",
            (
                python,
                str(scripts / "resolve_tiingo_historical_index.py"),
                "--root",
                root,
                "--sleep",
                str(sec_sleep),
            ),
        ),
        ImportStage(
            "extended_identity",
            "Resolve remaining identities with broader SEC filing evidence",
            (
                python,
                str(scripts / "resolve_tiingo_extended_identities.py"),
                "--root",
                root,
                "--sleep",
                str(sec_sleep),
            ),
        ),
        ImportStage(
            "resolved_batch_preflight_v2",
            "Preflight all newly proven identity evidence",
            (python, str(scripts / "promote_tiingo_resolved_batch.py"), "--root", root),
        ),
        ImportStage(
            "resolved_batch_promote_v2",
            "Promote all newly proven identities and prices",
            (
                python,
                str(scripts / "promote_tiingo_resolved_batch.py"),
                "--root",
                root,
                "--apply",
            ),
        ),
        ImportStage(
            "remaining_only_queue_v1",
            "Build queue from unresolved symbols only; exclude locked reviewed symbols",
            (
                python,
                str(scripts / "build_tiingo_remaining_identity_queue.py"),
                "--root",
                root,
            ),
        ),
    )


def run_import_pipeline(
    *,
    repository_root: Path,
    workspace_root: Path,
    provider: str,
    universe: str,
    stages: tuple[ImportStage, ...],
    runner: CommandRunner | None = None,
    progress_sink: ProgressSink | None = None,
    restart: bool = False,
) -> ImportRunState:
    """Run or resume an import pipeline using durable per-stage checkpoints."""

    repository_root = repository_root.resolve()
    workspace_root = workspace_root.resolve()
    state_path = _state_path(workspace_root, provider, universe)
    existing = None if restart else _load_state(state_path)
    run_id = existing.run_id if existing is not None else _new_run_id(provider, universe)
    created_at = existing.created_at if existing is not None else _now()
    records = _reconcile_records(existing, stages)
    execute = runner or _subprocess_runner
    sink = progress_sink or _print_progress

    for index, stage in enumerate(stages, start=1):
        previous = records[stage.stage_id]
        if previous.status is ImportStageStatus.SUCCEEDED and not restart:
            sink(
                _event(
                    run_id,
                    provider,
                    universe,
                    index,
                    len(stages),
                    stage,
                    ImportStageStatus.SKIPPED,
                    "checkpoint already succeeded",
                )
            )
            continue

        started = _now()
        records[stage.stage_id] = ImportStageRecord(
            stage_id=stage.stage_id,
            label=stage.label,
            status=ImportStageStatus.RUNNING,
            started_at=started,
        )
        _persist_state(
            state_path,
            _state(run_id, provider, universe, workspace_root, created_at, stages, records),
        )
        sink(
            _event(
                run_id,
                provider,
                universe,
                index,
                len(stages),
                stage,
                ImportStageStatus.RUNNING,
                "started",
            )
        )

        returncode = execute(stage.command, cwd=repository_root)
        finished = _now()
        status = ImportStageStatus.SUCCEEDED if returncode == 0 else ImportStageStatus.FAILED
        records[stage.stage_id] = ImportStageRecord(
            stage_id=stage.stage_id,
            label=stage.label,
            status=status,
            started_at=started,
            finished_at=finished,
            returncode=returncode,
        )
        current = _state(
            run_id,
            provider,
            universe,
            workspace_root,
            created_at,
            stages,
            records,
        )
        _persist_state(state_path, current)
        sink(
            _event(
                run_id,
                provider,
                universe,
                index,
                len(stages),
                stage,
                status,
                "completed" if returncode == 0 else f"failed with return code {returncode}",
            )
        )
        if returncode != 0:
            raise ImportOrchestrationError(
                f"import stage {stage.stage_id!r} failed with return code {returncode}; "
                f"resume will restart from this stage"
            )

    final = _state(run_id, provider, universe, workspace_root, created_at, stages, records)
    _persist_state(state_path, final)
    return final


def _subprocess_runner(command: tuple[str, ...], *, cwd: Path) -> int:
    completed = subprocess.run(command, cwd=cwd, check=False)
    return completed.returncode


def _reconcile_records(
    existing: ImportRunState | None, stages: tuple[ImportStage, ...]
) -> dict[str, ImportStageRecord]:
    prior = {item.stage_id: item for item in existing.stages} if existing is not None else {}
    result: dict[str, ImportStageRecord] = {}
    for stage in stages:
        item = prior.get(stage.stage_id)
        if item is not None and item.label == stage.label:
            result[stage.stage_id] = item
        else:
            result[stage.stage_id] = ImportStageRecord(
                stage_id=stage.stage_id,
                label=stage.label,
                status=ImportStageStatus.PENDING,
            )
    return result


def _state(
    run_id: str,
    provider: str,
    universe: str,
    root: Path,
    created_at: str,
    stages: tuple[ImportStage, ...],
    records: dict[str, ImportStageRecord],
) -> ImportRunState:
    return ImportRunState(
        schema_version="trade-scout-import-run-v0.1",
        run_id=run_id,
        provider=provider,
        universe=universe,
        root=str(root),
        created_at=created_at,
        updated_at=_now(),
        stages=tuple(records[item.stage_id] for item in stages),
    )


def _event(
    run_id: str,
    provider: str,
    universe: str,
    index: int,
    count: int,
    stage: ImportStage,
    status: ImportStageStatus,
    message: str,
) -> ImportProgressEvent:
    return ImportProgressEvent(
        run_id=run_id,
        provider=provider,
        universe=universe,
        stage_index=index,
        stage_count=count,
        stage_id=stage.stage_id,
        stage_label=stage.label,
        status=status,
        message=message,
    )


def _print_progress(event: ImportProgressEvent) -> None:
    print(
        f"[{event.stage_index}/{event.stage_count}] {event.stage_label}: "
        f"{event.status} - {event.message}",
        flush=True,
    )


def _state_path(root: Path, provider: str, universe: str) -> Path:
    slug = f"{provider.strip().lower()}-{universe.strip().lower()}"
    return root / "evidence" / "import-runs" / slug / "state.json"


def _persist_state(path: Path, state: ImportRunState) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".json.tmp")
    payload = asdict(state)
    payload["stages"] = [{**item, "status": str(item["status"])} for item in payload["stages"]]
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def _load_state(path: Path) -> ImportRunState | None:
    if not path.is_file():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.get("schema_version") != "trade-scout-import-run-v0.1":
        raise ImportOrchestrationError("unsupported import run state")
    stage_rows = payload.get("stages")
    if not isinstance(stage_rows, list):
        raise ImportOrchestrationError("import run stages must be an array")
    stages: list[ImportStageRecord] = []
    for row in stage_rows:
        if not isinstance(row, dict):
            raise ImportOrchestrationError("malformed import stage record")
        stages.append(
            ImportStageRecord(
                stage_id=_required_text(row.get("stage_id"), "stage_id"),
                label=_required_text(row.get("label"), "label"),
                status=ImportStageStatus(_required_text(row.get("status"), "status")),
                started_at=_optional_text(row.get("started_at")),
                finished_at=_optional_text(row.get("finished_at")),
                returncode=_optional_int(row.get("returncode")),
            )
        )
    return ImportRunState(
        schema_version="trade-scout-import-run-v0.1",
        run_id=_required_text(payload.get("run_id"), "run_id"),
        provider=_required_text(payload.get("provider"), "provider"),
        universe=_required_text(payload.get("universe"), "universe"),
        root=_required_text(payload.get("root"), "root"),
        created_at=_required_text(payload.get("created_at"), "created_at"),
        updated_at=_required_text(payload.get("updated_at"), "updated_at"),
        stages=tuple(stages),
    )


def _new_run_id(provider: str, universe: str) -> str:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    return f"import-{provider.lower()}-{universe.lower()}-{stamp}"


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _required_text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ImportOrchestrationError(f"{field} must be non-empty text")
    return value.strip()


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    return _required_text(value, "optional text")


def _optional_int(value: object) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise ImportOrchestrationError("returncode must be an integer")
    return value
