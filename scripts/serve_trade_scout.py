"""Serve the evidence-backed Trade Scout console on a local HTTP port."""

from __future__ import annotations

import argparse
import webbrowser
from datetime import date
from pathlib import Path

from trade_scout.app.data_health_service import DataHealthSourcePaths
from trade_scout.app.local_console import LocalConsoleConfig, serve_local_console


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Serve the read-only Trade Scout Phase 1 research console locally."
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--allow-remote", action="store_true")
    parser.add_argument("--open-browser", action="store_true")
    parser.add_argument("--refresh-seconds", type=int, default=15)
    parser.add_argument(
        "--tiingo-acceptance",
        type=Path,
        default=Path("configs/provider_acceptance_tiingo_v0.1.json"),
    )
    parser.add_argument(
        "--free-stack-acceptance",
        type=Path,
        default=Path("configs/provider_acceptance_free_stack_v0.1.json"),
    )
    parser.add_argument("--tiingo-safe-state", type=Path, default=None)
    parser.add_argument("--composite-evidence", type=Path, action="append", default=[])
    parser.add_argument("--canonical-root", type=Path, default=None)
    parser.add_argument("--canonical-dataset-version", default=None)
    parser.add_argument("--scanner-required-session", type=date.fromisoformat, default=None)
    parser.add_argument("--failed-ingestion-marker", type=Path, action="append", default=[])
    parser.add_argument(
        "--corporate-action-anomaly-report",
        type=Path,
        action="append",
        default=[],
    )
    return parser


def main() -> int:
    args = _parser().parse_args()
    sources = DataHealthSourcePaths(
        tiingo_acceptance_path=args.tiingo_acceptance,
        free_stack_acceptance_path=args.free_stack_acceptance,
        tiingo_safe_state_path=args.tiingo_safe_state,
        composite_evidence_paths=tuple(args.composite_evidence),
        canonical_root=args.canonical_root,
        canonical_dataset_version=args.canonical_dataset_version,
        scanner_required_session=args.scanner_required_session,
        failed_ingestion_markers=tuple(args.failed_ingestion_marker),
        corporate_action_anomaly_reports=tuple(args.corporate_action_anomaly_report),
    )
    config = LocalConsoleConfig(
        sources=sources,
        build_label="local-console-v0.1",
        refresh_seconds=args.refresh_seconds,
    )
    url = f"http://{args.host}:{args.port}/"
    print(f"Trade Scout local console: {url}")
    print(f"Data Health JSON: {url}api/data-health.json")
    print(f"Application snapshot JSON: {url}api/snapshot.json")
    print("Press Ctrl+C to stop.")
    if args.open_browser:
        webbrowser.open(url)
    try:
        serve_local_console(
            config,
            host=args.host,
            port=args.port,
            allow_remote=args.allow_remote,
        )
    except KeyboardInterrupt:
        print("\nTrade Scout local console stopped.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
