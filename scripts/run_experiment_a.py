"""Run the complete governed Experiment A T0-T6 baseline in a private operator workspace."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import asdict
from pathlib import Path

from trade_scout.app.operator_workspace import (
    OperatorWorkspaceError,
    load_operator_workspace,
    validate_workspace_location,
    verify_operator_workspace,
)
from trade_scout.data.canonical_storage import CanonicalDailyBarStore, CanonicalDatasetNotFoundError
from trade_scout.data.contracts import DatasetVersion, InstrumentId
from trade_scout.experiments.store import FileManifestStore
from trade_scout.experiments.trend_baseline_operator import (
    ExperimentAOperatorError,
    execute_experiment_a_fixed_cohort,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Run first-program Experiment A across T0-T6 using one immutable canonical dataset. "
            "This command uses a fixed reviewed cohort and does not claim historical index membership."
        )
    )
    parser.add_argument("--root", type=Path, required=True, help="Private operator workspace root.")
    parser.add_argument(
        "--dataset-version",
        default=None,
        help="Canonical dataset version; defaults to workspace.json canonical_dataset_version.",
    )
    parser.add_argument(
        "--benchmark-instrument-id",
        required=True,
        help=(
            "Permanent canonical instrument ID for the broad-market benchmark used by T6. "
            "It must already be present in the same canonical dataset."
        ),
    )
    parser.add_argument("--sampling-stride", type=int, default=5)
    parser.add_argument("--sma-slope-lookback", type=int, default=20)
    parser.add_argument("--trailing-return-intervals", type=int, default=60)
    parser.add_argument("--relative-strength-intervals", type=int, default=60)
    args = parser.parse_args()

    repository_root = Path(__file__).resolve().parents[1]
    root = args.root.expanduser().resolve()
    try:
        validate_workspace_location(root, repository_root=repository_root)
        workspace = load_operator_workspace(root)
        verification = verify_operator_workspace(workspace)
        if not verification.is_consistent:
            raise OperatorWorkspaceError(
                "durable workspace evidence is inconsistent; Experiment A is blocked fail-closed"
            )
        dataset_text = args.dataset_version or workspace.manifest.canonical_dataset_version
        if dataset_text is None:
            raise OperatorWorkspaceError(
                "no canonical dataset is selected; pass --dataset-version or select one in workspace.json"
            )

        dataset_version = DatasetVersion(dataset_text)
        canonical_store = CanonicalDailyBarStore(workspace.canonical_root)
        experiment_root = workspace.root / "research" / "experiments"
        manifest_store = FileManifestStore(experiment_root)
        result = execute_experiment_a_fixed_cohort(
            canonical_store,
            manifest_store,
            dataset_version=dataset_version,
            benchmark_instrument_id=InstrumentId(args.benchmark_instrument_id),
            code_version=_git_head(repository_root),
            config_schema_version="experiment-a-operator-v0.1",
            sampling_stride=args.sampling_stride,
            sma_slope_lookback=args.sma_slope_lookback,
            trailing_return_intervals=args.trailing_return_intervals,
            relative_strength_intervals=args.relative_strength_intervals,
        )
        report_path = (
            workspace.root
            / "evidence"
            / "research-program"
            / "experiment-a"
            / f"{dataset_version}__{result.batch.plan_id}.json"
        )
        _persist_report(report_path, result)
    except (
        OperatorWorkspaceError,
        CanonicalDatasetNotFoundError,
        ExperimentAOperatorError,
        ValueError,
    ) as exc:
        print(f"Experiment A error: {exc}", file=sys.stderr)
        return 2

    payload = _result_payload(result)
    payload["report_path"] = str(report_path)
    payload["experiment_root"] = str(experiment_root)
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


def _result_payload(result) -> dict[str, object]:
    return {
        "schema_version": "experiment-a-operator-report-v0.1",
        "program_experiment": "A",
        "research_mode": "EXPLORATORY",
        "dataset_version": result.preflight.dataset_version,
        "canonical_content_sha256": result.preflight.canonical_content_sha256,
        "universe_version": result.preflight.universe_version,
        "universe_scope_warning": result.preflight.scope_warning,
        "benchmark_instrument_id": str(result.preflight.benchmark_instrument_id),
        "research_instrument_count": len(result.preflight.research_instrument_ids),
        "canonical_record_count": result.preflight.record_count,
        "first_trade_date": result.preflight.first_trade_date.isoformat(),
        "last_trade_date": result.preflight.last_trade_date.isoformat(),
        "plan_id": result.batch.plan_id,
        "planned_count": result.batch.planned_count,
        "attempted_count": result.batch.attempted_count,
        "succeeded_count": result.batch.succeeded_count,
        "failed_count": result.batch.failed_count,
        "experiment_ids": [record.experiment_id for record in result.batch.records],
        "comparison": [
            {
                **asdict(row),
                "trend_context": row.trend_context.value,
            }
            for row in result.comparison
        ],
        "provider_calls_made": False,
        "historical_index_membership_claimed": False,
        "survivorship_bias_free_claimed": False,
        "validation_claimed": False,
    }


def _persist_report(path: Path, result) -> None:
    payload = _result_payload(result)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def _git_head(repository_root: Path) -> str:
    completed = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repository_root,
        capture_output=True,
        check=False,
        text=True,
    )
    value = completed.stdout.strip()
    if completed.returncode != 0 or not value:
        raise OperatorWorkspaceError("cannot resolve repository HEAD for experiment provenance")
    return value


if __name__ == "__main__":
    raise SystemExit(main())
