"""Operate the private Phase 1 Trade Scout workspace from one command surface."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import webbrowser
from datetime import date
from pathlib import Path

from trade_scout.app.local_console import LocalConsoleConfig, serve_local_console
from trade_scout.app.operator_workspace import (
    OperatorWorkspaceError,
    configure_operator_workspace,
    initialize_operator_workspace,
    load_operator_workspace,
    verify_operator_workspace,
    workspace_status_payload,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Initialize, acquire, verify, inspect, and serve one private Trade Scout workspace."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    init = subparsers.add_parser("init", help="Create the private workspace directory layout.")
    init.add_argument("--root", type=Path, required=True)
    init.add_argument("--storage-namespace", required=True)
    init.add_argument("--workspace-id", default="trade-scout-phase1-local")

    status = subparsers.add_parser("status", help="Show safe workspace and campaign status.")
    status.add_argument("--root", type=Path, required=True)

    verify = subparsers.add_parser("verify", help="Checksum-verify durable Tiingo receipts.")
    verify.add_argument("--root", type=Path, required=True)

    configure = subparsers.add_parser(
        "configure",
        help="Set explicit canonical-dataset and scanner-freshness selections.",
    )
    configure.add_argument("--root", type=Path, required=True)
    configure.add_argument("--canonical-dataset-version", default=None)
    configure.add_argument("--scanner-required-session", type=date.fromisoformat, default=None)

    acquire = subparsers.add_parser(
        "acquire-tiingo",
        help="Run a checksum-verified durable Tiingo acquisition slice.",
    )
    acquire.add_argument("--root", type=Path, required=True)
    acquire.add_argument("--max-symbols", type=int, default=1)
    acquire.add_argument(
        "--plan",
        type=Path,
        default=Path("configs/tiingo_sp500_campaign_v0.1.json"),
    )

    serve = subparsers.add_parser("serve", help="Open the read-only console for this workspace.")
    serve.add_argument("--root", type=Path, required=True)
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8765)
    serve.add_argument("--allow-remote", action="store_true")
    serve.add_argument("--open-browser", action="store_true")
    serve.add_argument("--refresh-seconds", type=int, default=15)
    return parser


def main() -> int:
    args = _parser().parse_args()
    try:
        if args.command == "init":
            return _init(args)
        if args.command == "status":
            return _status(args)
        if args.command == "verify":
            return _verify(args)
        if args.command == "configure":
            return _configure(args)
        if args.command == "acquire-tiingo":
            return _acquire_tiingo(args)
        if args.command == "serve":
            return _serve(args)
    except OperatorWorkspaceError as exc:
        print(f"operator workspace error: {exc}", file=sys.stderr)
        return 2
    raise AssertionError("unreachable workspace command")


def _init(args: argparse.Namespace) -> int:
    workspace = initialize_operator_workspace(
        args.root,
        storage_namespace=args.storage_namespace,
        workspace_id=args.workspace_id,
    )
    print(workspace.manifest_path)
    print(json.dumps(workspace_status_payload(workspace), indent=2, sort_keys=True))
    return 0


def _status(args: argparse.Namespace) -> int:
    workspace = load_operator_workspace(args.root)
    print(json.dumps(workspace_status_payload(workspace), indent=2, sort_keys=True))
    return 0


def _verify(args: argparse.Namespace) -> int:
    workspace = load_operator_workspace(args.root)
    report = verify_operator_workspace(workspace)
    payload = {
        "workspace_id": report.workspace_id,
        "consistent": report.is_consistent,
        "state_present": report.state_present,
        "durable_completed_symbol_count": report.durable_completed_symbol_count,
        "receipt_file_count": report.receipt_file_count,
        "verified_receipt_count": report.verified_receipt_count,
        "missing_receipt_symbols": list(report.missing_receipt_symbols),
        "receipt_subjects_not_in_state": list(report.receipt_subjects_not_in_state),
        "invalid_receipt_paths": list(report.invalid_receipt_paths),
    }
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if report.is_consistent else 1


def _configure(args: argparse.Namespace) -> int:
    workspace = load_operator_workspace(args.root)
    canonical = (
        args.canonical_dataset_version
        if args.canonical_dataset_version is not None
        else workspace.manifest.canonical_dataset_version
    )
    scanner_session = (
        args.scanner_required_session
        if args.scanner_required_session is not None
        else workspace.manifest.scanner_required_session
    )
    updated = configure_operator_workspace(
        workspace,
        canonical_dataset_version=canonical,
        scanner_required_session=scanner_session,
    )
    print(updated.manifest_path)
    return 0


def _acquire_tiingo(args: argparse.Namespace) -> int:
    workspace = load_operator_workspace(args.root)
    if args.max_symbols < 1:
        raise OperatorWorkspaceError("--max-symbols must be positive")
    before = verify_operator_workspace(workspace)
    if not before.is_consistent:
        raise OperatorWorkspaceError(
            "durable evidence is inconsistent; run the verify command before further acquisition"
        )

    repository_root = Path(__file__).resolve().parents[1]
    runner = repository_root / "scripts" / "run_tiingo_sp500_durable_slice.py"
    plan = args.plan if args.plan.is_absolute() else repository_root / args.plan
    command = [
        sys.executable,
        str(runner),
        "--plan",
        str(plan),
        "--durable-root",
        str(workspace.tiingo_root),
        "--storage-namespace",
        workspace.manifest.storage_namespace,
        "--max-symbols",
        str(args.max_symbols),
    ]
    completed = subprocess.run(command, cwd=repository_root, check=False)
    after = verify_operator_workspace(workspace)
    print(json.dumps(workspace_status_payload(workspace), indent=2, sort_keys=True))
    if not after.is_consistent:
        print(
            "durable evidence became inconsistent; acquisition is stopped fail-closed",
            file=sys.stderr,
        )
        return 2
    return completed.returncode


def _serve(args: argparse.Namespace) -> int:
    workspace = load_operator_workspace(args.root)
    repository_root = Path(__file__).resolve().parents[1]
    sources = workspace.data_health_sources(repository_root=repository_root)
    config = LocalConsoleConfig(
        sources=sources,
        build_label=f"operator:{workspace.manifest.workspace_id}",
        refresh_seconds=args.refresh_seconds,
    )
    url = f"http://{args.host}:{args.port}/"
    print(f"Trade Scout workspace: {workspace.root}")
    print(f"Trade Scout local console: {url}")
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
