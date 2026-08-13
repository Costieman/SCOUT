"""Prepare the explicit SPY benchmark, compose canonical inputs, and run Experiment A."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

from trade_scout.app.operator_workspace import (
    OperatorWorkspaceError,
    load_operator_workspace,
    validate_workspace_location,
    verify_operator_workspace,
)
from trade_scout.data.canonical_storage import CanonicalDailyBarStore
from trade_scout.data.contracts import DatasetVersion
from trade_scout.experiments.benchmark_config import (
    BenchmarkConfigError,
    ExperimentABenchmarkConfig,
    load_experiment_a_benchmark_config,
)

_DEFAULT_BENCHMARK_CONFIG = Path("configs/experiment_a_spy_benchmark_v0.1.json")


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Prepare the checked-in Experiment A benchmark, compose it with the selected immutable "
            "research dataset, and execute the governed T0-T6 batch."
        )
    )
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--research-dataset-version", default=None)
    parser.add_argument("--benchmark-config", type=Path, default=_DEFAULT_BENCHMARK_CONFIG)
    parser.add_argument("--target-dataset-version", default=None)
    parser.add_argument("--sampling-stride", type=int, default=5)
    parser.add_argument("--sma-slope-lookback", type=int, default=20)
    parser.add_argument("--trailing-return-intervals", type=int, default=60)
    parser.add_argument("--relative-strength-intervals", type=int, default=60)
    args = parser.parse_args()

    repository_root = Path(__file__).resolve().parents[1]
    root = args.root.expanduser().resolve()
    benchmark_config_path = _resolve_config(repository_root, args.benchmark_config)
    try:
        validate_workspace_location(root, repository_root=repository_root)
        workspace = load_operator_workspace(root)
        verification = verify_operator_workspace(workspace)
        if not verification.is_consistent:
            raise OperatorWorkspaceError(
                "durable workspace evidence is inconsistent; Experiment A pipeline is blocked"
            )
        benchmark = load_experiment_a_benchmark_config(benchmark_config_path)
        research_text = (
            args.research_dataset_version or workspace.manifest.canonical_dataset_version
        )
        if research_text is None:
            raise OperatorWorkspaceError(
                "no research canonical dataset is selected; pass --research-dataset-version "
                "or select one in workspace.json"
            )
        research_version = DatasetVersion(research_text)
        target_version = DatasetVersion(
            args.target_dataset_version
            or _default_target_version(research_version, benchmark.definition.dataset_version)
        )

        store = CanonicalDailyBarStore(workspace.canonical_root)
        _require_research_dataset(store, research_version)
        if store.get_manifest(benchmark.definition.dataset_version) is None:
            _run(
                _benchmark_promotion_command(
                    repository_root,
                    root,
                    benchmark_config_path,
                ),
                repository_root,
                "benchmark promotion",
            )
        else:
            store.load(benchmark.definition.dataset_version)
            print(
                "Experiment A pipeline: benchmark canonical dataset already exists; "
                "verified and reused without a provider call."
            )

        if store.get_manifest(target_version) is None:
            _run(
                _composition_command(
                    repository_root,
                    root,
                    research_version,
                    benchmark,
                    target_version,
                ),
                repository_root,
                "canonical composition",
            )
        else:
            store.load(target_version)
            print(
                "Experiment A pipeline: composed canonical dataset already exists; "
                "verified and reused."
            )

        _run(
            _experiment_command(
                repository_root,
                root,
                target_version,
                benchmark,
                sampling_stride=args.sampling_stride,
                sma_slope_lookback=args.sma_slope_lookback,
                trailing_return_intervals=args.trailing_return_intervals,
                relative_strength_intervals=args.relative_strength_intervals,
            ),
            repository_root,
            "Experiment A execution",
        )
    except (OperatorWorkspaceError, BenchmarkConfigError, ValueError) as exc:
        print(f"Experiment A pipeline error: {exc}", file=sys.stderr)
        return 2

    return 0


def _resolve_config(repository_root: Path, value: Path) -> Path:
    return (value if value.is_absolute() else repository_root / value).resolve()


def _default_target_version(
    research_version: DatasetVersion,
    benchmark_version: DatasetVersion,
) -> str:
    value = f"{research_version}__with__{benchmark_version}"
    if len(value) > 128:
        raise ValueError(
            "derived Experiment A target dataset version exceeds the canonical "
            "128-character limit; pass --target-dataset-version explicitly"
        )
    return value


def _require_research_dataset(store: CanonicalDailyBarStore, version: DatasetVersion) -> None:
    manifest = store.get_manifest(version)
    if manifest is None:
        raise OperatorWorkspaceError(f"research canonical dataset is not registered: {version}")
    store.load(version)


def _benchmark_promotion_command(
    repository_root: Path,
    root: Path,
    config_path: Path,
) -> list[str]:
    return [
        sys.executable,
        str(repository_root / "scripts" / "promote_experiment_a_benchmark.py"),
        "--root",
        str(root),
        "--config",
        str(config_path),
    ]


def _composition_command(
    repository_root: Path,
    root: Path,
    research_version: DatasetVersion,
    benchmark: ExperimentABenchmarkConfig,
    target_version: DatasetVersion,
) -> list[str]:
    return [
        sys.executable,
        str(repository_root / "scripts" / "compose_experiment_a_dataset.py"),
        "--root",
        str(root),
        "--research-dataset-version",
        str(research_version),
        "--benchmark-dataset-version",
        str(benchmark.definition.dataset_version),
        "--target-dataset-version",
        str(target_version),
        "--universe-version",
        "reviewed-canonical-fixed-cohort-plus-spy-v0.1",
    ]


def _experiment_command(
    repository_root: Path,
    root: Path,
    target_version: DatasetVersion,
    benchmark: ExperimentABenchmarkConfig,
    *,
    sampling_stride: int,
    sma_slope_lookback: int,
    trailing_return_intervals: int,
    relative_strength_intervals: int,
) -> list[str]:
    return [
        sys.executable,
        str(repository_root / "scripts" / "run_experiment_a.py"),
        "--root",
        str(root),
        "--dataset-version",
        str(target_version),
        "--benchmark-instrument-id",
        str(benchmark.definition.instrument_id),
        "--sampling-stride",
        str(sampling_stride),
        "--sma-slope-lookback",
        str(sma_slope_lookback),
        "--trailing-return-intervals",
        str(trailing_return_intervals),
        "--relative-strength-intervals",
        str(relative_strength_intervals),
    ]


def _run(command: list[str], cwd: Path, label: str) -> None:
    completed = subprocess.run(command, cwd=cwd, check=False)
    if completed.returncode != 0:
        raise OperatorWorkspaceError(f"{label} failed with exit code {completed.returncode}")


if __name__ == "__main__":
    raise SystemExit(main())
