"""Serve Trade Scout with single-stock and market-wide research workbenches enabled."""

from __future__ import annotations

import argparse
import socket
import subprocess
import time
import webbrowser
from pathlib import Path
from threading import Thread

from trade_scout.app.cached_windowed_canonical_source import (
    CachedWindowedCanonicalUniverseResearchSource,
)
from trade_scout.app.edge_explorer_service import CanonicalEdgeExplorerSource
from trade_scout.app.local_console import LocalConsoleConfig
from trade_scout.app.operator_workspace import load_operator_workspace, validate_workspace_location
from trade_scout.app.research_station_runtime_identity import configure_runtime_identity
from trade_scout.app.research_station_workflow_v12 import (
    configure_research_station_runtime,
    serve_research_workbench_console,
)
from trade_scout.app.strategy_builder_experiments import StrategyBuilderExperimentRecorder


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

    commit_sha = _git_head(repository_root)
    branch = _git_branch(repository_root)
    edge_source = CanonicalEdgeExplorerSource(
        canonical_root=workspace.canonical_root,
        dataset_version=dataset_version,
        identity_candidate_path=identity_candidate,
    )
    universe_source = CachedWindowedCanonicalUniverseResearchSource(
        canonical_root=workspace.canonical_root,
        dataset_version=dataset_version,
        identity_candidate_path=identity_candidate,
    )
    config = LocalConsoleConfig(
        sources=workspace.data_health_sources(repository_root=repository_root),
        build_label=f"research-workbench:{workspace.manifest.workspace_id}@{commit_sha[:8]}",
        refresh_seconds=15,
        edge_explorer_source=edge_source,
        universe_research_source=universe_source,
        strategy_builder_source=universe_source,
    )
    experiment_root = workspace.root / "research" / "experiments"
    brain_root = workspace.root / "research" / "brains"
    experiment_recorder = StrategyBuilderExperimentRecorder(
        experiment_root=experiment_root,
        dataset_version=dataset_version,
        code_version=commit_sha,
    )
    base_url = f"http://{args.host}:{args.port}/"
    strategy_url = f"{base_url}research/strategy"
    print(f"Trade Scout research console: {base_url}")
    print(f"Visual Strategy Builder: {strategy_url}")
    print(f"Experiment records: {experiment_root}")
    print(f"Experiment registry: {experiment_recorder.registry_path}")
    print(f"Research brain records: {brain_root}")
    print(f"SCOUT runtime: {branch} @ {commit_sha[:8]}")
    print("Research Station run path: brain-aware-research-sequence-v12")
    print("Canonical research read cache: enabled for iterative runs")
    print("Uses selected immutable canonical data only; no provider calls are made by the app.")
    print("Press Ctrl+C to stop.")
    configure_research_station_runtime(experiment_root=experiment_root, brain_root=brain_root)
    configure_runtime_identity(commit_sha=commit_sha, branch=branch)
    if args.open_browser:
        Thread(
            target=_open_browser_when_ready,
            args=(args.host, args.port, strategy_url),
            daemon=True,
        ).start()
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


def _open_browser_when_ready(host: str, port: int, url: str) -> None:
    """Open the browser only after the HTTP listener accepts connections."""

    connect_host = "127.0.0.1" if host in {"0.0.0.0", "::"} else host
    for _ in range(100):
        try:
            with socket.create_connection((connect_host, port), timeout=0.1):
                webbrowser.open(url)
                return
        except OSError:
            time.sleep(0.05)
    print(f"Browser was not opened because the research server never became ready: {url}")


def _git_head(repository_root: Path) -> str:
    return _git_value(
        repository_root, "rev-parse", "HEAD", failure="cannot resolve repository HEAD"
    )


def _git_branch(repository_root: Path) -> str:
    return _git_value(
        repository_root,
        "rev-parse",
        "--abbrev-ref",
        "HEAD",
        failure="cannot resolve repository branch",
    )


def _git_value(repository_root: Path, *args: str, failure: str) -> str:
    completed = subprocess.run(
        ["git", *args], cwd=repository_root, capture_output=True, check=False, text=True
    )
    value = completed.stdout.strip()
    if completed.returncode != 0 or not value:
        raise SystemExit(failure)
    return value


if __name__ == "__main__":
    raise SystemExit(main())
