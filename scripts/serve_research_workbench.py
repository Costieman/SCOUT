"""Serve Trade Scout with single-stock and market-wide research workbenches enabled."""

from __future__ import annotations

import argparse
import webbrowser
from pathlib import Path

from trade_scout.app.edge_explorer_service import CanonicalEdgeExplorerSource
from trade_scout.app.local_console import LocalConsoleConfig, serve_local_console
from trade_scout.app.market_analysis_service import CanonicalMarketAnalysisSource
from trade_scout.app.operator_workspace import load_operator_workspace, validate_workspace_location
from trade_scout.app.universe_research_service import CanonicalUniverseResearchSource


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
    universe_source = CanonicalUniverseResearchSource(
        canonical_root=workspace.canonical_root,
        dataset_version=dataset_version,
        identity_candidate_path=identity_candidate,
    )
    market_source = CanonicalMarketAnalysisSource(
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
        market_analysis_source=market_source,
    )
    base_url = f"http://{args.host}:{args.port}/"
    market_url = f"{base_url}research/market"
    universe_url = f"{base_url}research/universe"
    edge_url = f"{base_url}research/edge"
    print(f"Trade Scout research console: {base_url}")
    print(f"Market Analysis: {market_url}")
    print(f"Universe Research Analyzer: {universe_url}")
    print(f"Single-stock Edge Explorer: {edge_url}")
    print("Uses selected immutable canonical data only; no provider calls are made by the app.")
    print("Press Ctrl+C to stop.")
    if args.open_browser:
        webbrowser.open(market_url)
    try:
        serve_local_console(
            config,
            host=args.host,
            port=args.port,
            allow_remote=args.allow_remote,
        )
    except KeyboardInterrupt:
        print("\nTrade Scout research workbench stopped.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
