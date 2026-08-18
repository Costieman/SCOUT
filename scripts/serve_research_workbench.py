"""Serve Trade Scout with single-stock and market-wide research workbenches enabled."""

from __future__ import annotations

import argparse
import subprocess
import webbrowser
from pathlib import Path

from trade_scout.app.edge_explorer_service import CanonicalEdgeExplorerSource
from trade_scout.app.local_console import LocalConsoleConfig
from trade_scout.app.operator_workspace import load_operator_workspace, validate_workspace_location
from trade_scout.app.research_workbench_console import serve_research_workbench_console
from trade_scout.app.strategy_builder_experiments import StrategyBuilderExperimentRecorder
from trade_scout.app.windowed_canonical_source import WindowedCanonicalUniverseResearchSource


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Serve the Trade Scout research console with canonical research tools enabled."
    )
    parser.add_argument("--root", type=Path, required=True, help="Private operator workspace root")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--allow-remote", action="store_true")
    parser.add_argument("--open-browser", action="store_true")
    return parser


def main() -> int:
    args = _parser().parse_args()
    repository_root = Path(__file__).resolve().parents[1]
    validate_workspace_location(args.root, repository_root=repository_root)
    workspace = load_operator_workspace(args.root)
    dataset_version = workspace.manifest.canonical_dataset_version
    if dataset_version is None:
        raise SystemExit(
            "operator workspace has no selected canonical dataset; configure it before research"
        )

    identity_candidate = (
        workspace.root / "evidence" / "instrument-identity" / "tiingo-reviewed-candidate.json"
    )
    if not identity_candidate.is_file():
        raise SystemExit(
            "reviewed identity candidate is missing; build the Tiingo identity candidate first"
        )

    edge_source = CanonicalEdgeExplorerSource(
        canonical_root=workspace.canonical_root,
        dataset_version=dataset_version,
        identity_candidate_path=identity_candidate,
    )
    universe_source = WindowedCanonicalUniverseResearchSource(
        canonical_root=workspace.canonical_root,
        dataset_version=dataset_version,
        identity_candidate_path=identity_candidate,
    )
    config = LocalConsoleConfig(
        sources=workspace.data_health_sources(repository_root=repository_root),
        build_label=f"research-workbench:{workspace.manifest.workspace_id}",
        refresh_seconds=15,
        edge_explorer_source=edge_source,
        universe_research_source=universe_source,
        strategy_builder_source=universe_source,
    )
    experiment_root = workspace.root / "research" / "experiments"
    experiment_recorder = StrategyBuilderExperimentRecorder(
        experiment_root=experiment_root,
        dataset_version=dataset_version,
        code_version=_git_head(repository_root),
    )
    base_url = f"http://{args.host}:{args.port}/"
    universe_url = f"{base_url}research/universe"
    edge_url = f"{base_url}research/edge"
    risk_url = f"{base_url}research/risk"
    exit_url = f"{base_url}research/exits"
    strategy_url = f"{base_url}research/strategy"
    experiment_library_url = f"{base_url}research/experiments"
    print(f"Trade Scout research console: {base_url}")
    print(f"Visual Strategy Builder: {strategy_url}")
    print(f"Experiment Library: {experiment_library_url}")
    print(f"Universe Research Analyzer: {universe_url}")
    print(f"Single-stock Edge Explorer: {edge_url}")
    print(f"Risk & Stop Research: {risk_url}")
    print(f"Configurable Exit Policy Lab: {exit_url}")
    print(f"Experiment records: {experiment_root}")
    print(f"Experiment registry: {experiment_recorder.registry_path}")
    print("Uses selected immutable canonical data only; no provider calls are made by the app.")
    print("Press Ctrl+C to stop.")
    if args.open_browser:
        webbrowser.open(strategy_url)
    try:
        serve_research_workbench_console(
            config,
            host=args.host,
            port=args.port,
            allow_remote=args.allow_remote,
            experiment_recorder=experiment_recorder,
        )
    except KeyboardInterrupt:
        print("\nTrade Scout research workbench stopped.")
    return 0


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
        raise SystemExit("cannot resolve repository HEAD for experiment provenance")
    return value


if __name__ == "__main__":
    raise SystemExit(main())
