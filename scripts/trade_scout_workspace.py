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
    OperatorWorkspace,
    OperatorWorkspaceError,
    configure_operator_workspace,
    initialize_operator_workspace,
    load_operator_workspace,
    validate_workspace_location,
    verify_operator_workspace,
    workspace_status_payload,
)
from trade_scout.data.providers.tiingo_profile import (
    TiingoProfileError,
    persist_tiingo_durable_profile,
    profile_durable_tiingo,
)
from trade_scout.data.reviewed_identity_snapshot import (
    ReviewedIdentitySnapshotError,
    build_reviewed_identity_snapshot_candidate,
    load_reviewed_identity_seed_set,
    persist_reviewed_identity_snapshot_candidate,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Operate one private Trade Scout workspace.")
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

    plan_tiingo = subparsers.add_parser(
        "plan-tiingo",
        help="Validate S&P source symbols against audited Tiingo query symbology.",
    )
    plan_tiingo.add_argument("--root", type=Path, required=True)
    plan_tiingo.add_argument(
        "--plan",
        type=Path,
        default=Path("configs/tiingo_sp500_campaign_v0.1.json"),
    )

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

    profile = subparsers.add_parser(
        "profile-tiingo",
        help="Profile verified private Tiingo history without provider calls or raw-price output.",
    )
    profile.add_argument("--root", type=Path, required=True)

    identity = subparsers.add_parser(
        "build-tiingo-identity",
        help="Build a reviewed identity candidate from the local Tiingo lineage audit.",
    )
    identity.add_argument("--root", type=Path, required=True)
    identity.add_argument(
        "--config",
        type=Path,
        default=Path("configs/tiingo_reviewed_identity_seeds_v0.1.json"),
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
        if args.command == "plan-tiingo":
            return _plan_tiingo(args)
        if args.command == "acquire-tiingo":
            return _acquire_tiingo(args)
        if args.command == "profile-tiingo":
            return _profile_tiingo(args)
        if args.command == "build-tiingo-identity":
            return _build_tiingo_identity(args)
        if args.command == "serve":
            return _serve(args)
    except (OperatorWorkspaceError, TiingoProfileError, ReviewedIdentitySnapshotError) as exc:
        print(f"operator workspace error: {exc}", file=sys.stderr)
        return 2
    raise AssertionError("unreachable workspace command")


def _repository_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _load_checked_workspace(root: Path) -> OperatorWorkspace:
    repository_root = _repository_root()
    validate_workspace_location(root, repository_root=repository_root)
    return load_operator_workspace(root)


def _resolved_plan(path: Path) -> Path:
    repository_root = _repository_root()
    return path if path.is_absolute() else repository_root / path


def _resolved_repository_path(path: Path) -> Path:
    repository_root = _repository_root()
    return path if path.is_absolute() else repository_root / path


def _init(args: argparse.Namespace) -> int:
    validate_workspace_location(args.root, repository_root=_repository_root())
    workspace = initialize_operator_workspace(
        args.root,
        storage_namespace=args.storage_namespace,
        workspace_id=args.workspace_id,
    )
    print(workspace.manifest_path)
    print(json.dumps(workspace_status_payload(workspace), indent=2, sort_keys=True))
    return 0


def _status(args: argparse.Namespace) -> int:
    workspace = _load_checked_workspace(args.root)
    print(json.dumps(workspace_status_payload(workspace), indent=2, sort_keys=True))
    return 0


def _verify(args: argparse.Namespace) -> int:
    workspace = _load_checked_workspace(args.root)
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
    workspace = _load_checked_workspace(args.root)
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


def _plan_tiingo(args: argparse.Namespace) -> int:
    workspace = _load_checked_workspace(args.root)
    repository_root = _repository_root()
    runner = repository_root / "scripts" / "plan_tiingo_sp500_symbology.py"
    output = workspace.tiingo_root / "symbology-plan.json"
    command = [
        sys.executable,
        str(runner),
        "--plan",
        str(_resolved_plan(args.plan)),
        "--output",
        str(output),
    ]
    completed = subprocess.run(command, cwd=repository_root, check=False)
    if completed.returncode == 0:
        print(output)
    return completed.returncode


def _acquire_tiingo(args: argparse.Namespace) -> int:
    workspace = _load_checked_workspace(args.root)
    if args.max_symbols < 1:
        raise OperatorWorkspaceError("--max-symbols must be positive")
    before = verify_operator_workspace(workspace)
    if not before.is_consistent:
        raise OperatorWorkspaceError(
            "durable evidence is inconsistent; run the verify command before further acquisition"
        )

    repository_root = _repository_root()
    runner = repository_root / "scripts" / "run_tiingo_sp500_durable_slice.py"
    command = [
        sys.executable,
        str(runner),
        "--plan",
        str(_resolved_plan(args.plan)),
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


def _profile_tiingo(args: argparse.Namespace) -> int:
    workspace = _load_checked_workspace(args.root)
    verification = verify_operator_workspace(workspace)
    if not verification.is_consistent:
        raise OperatorWorkspaceError(
            "durable evidence is inconsistent; profile generation is blocked fail-closed"
        )

    profile = profile_durable_tiingo(
        receipt_root=workspace.tiingo_receipts_root,
        raw_root=workspace.tiingo_raw_root,
        storage_namespace=workspace.manifest.storage_namespace,
    )
    output = workspace.root / "evidence" / "tiingo-profile" / "profile.json"
    persist_tiingo_durable_profile(output, profile)
    anomaly_symbol_count = sum(
        1
        for item in profile.symbols
        if (
            item.duplicate_date_count
            or item.non_monotonic_date_count
            or item.missing_required_field_row_count
            or item.invalid_numeric_row_count
            or item.ohlc_invariant_violation_count
            or item.negative_volume_count
            or item.long_calendar_gap_count
        )
    )
    summary = {
        "profile_path": str(output),
        "symbol_count": profile.symbol_count,
        "total_row_count": profile.total_row_count,
        "symbols_with_structural_anomalies": anomaly_symbol_count,
        "duplicate_date_count": profile.duplicate_date_count,
        "non_monotonic_date_count": profile.non_monotonic_date_count,
        "missing_required_field_row_count": profile.missing_required_field_row_count,
        "invalid_numeric_row_count": profile.invalid_numeric_row_count,
        "ohlc_invariant_violation_count": profile.ohlc_invariant_violation_count,
        "negative_volume_count": profile.negative_volume_count,
        "split_event_count": profile.split_event_count,
        "dividend_event_count": profile.dividend_event_count,
        "long_calendar_gap_count": profile.long_calendar_gap_count,
    }
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


def _build_tiingo_identity(args: argparse.Namespace) -> int:
    workspace = _load_checked_workspace(args.root)
    verification = verify_operator_workspace(workspace)
    if not verification.is_consistent:
        raise OperatorWorkspaceError(
            "durable evidence is inconsistent; identity candidate generation is blocked fail-closed"
        )

    audit_path = workspace.root / "evidence" / "tiingo-lineage" / "audit.json"
    profile_path = workspace.root / "evidence" / "tiingo-profile" / "profile.json"
    if not profile_path.is_file():
        raise OperatorWorkspaceError("Tiingo profile is missing; run profile-tiingo first")
    if not audit_path.is_file():
        raise OperatorWorkspaceError(
            "Tiingo lineage audit is missing; run audit_tiingo_symbol_lineage.py first"
        )

    seed_set = load_reviewed_identity_seed_set(_resolved_repository_path(args.config))
    candidate = build_reviewed_identity_snapshot_candidate(
        seed_set=seed_set,
        lineage_audit_path=audit_path,
    )
    output = workspace.root / "evidence" / "instrument-identity" / "tiingo-reviewed-candidate.json"
    persist_reviewed_identity_snapshot_candidate(output, candidate)
    summary = {
        "candidate_path": str(output),
        "snapshot_version": candidate.snapshot_version,
        "instrument_count": len(candidate.instruments),
        "symbol_history_count": len(candidate.symbol_history),
        "provider_series_link_count": len(candidate.provider_series_links),
        "coverage_gap_count": len(candidate.coverage_gaps),
        "fully_covered_instrument_count": candidate.fully_covered_instrument_count,
        "promotion_ready": candidate.promotion_ready,
        "coverage_gaps": [
            {
                "query_symbol": item.query_symbol,
                "gap_start": item.gap_start.isoformat(),
                "gap_end": item.gap_end.isoformat(),
                "reason": item.reason,
                "known_predecessor_symbol": item.known_predecessor_symbol,
            }
            for item in candidate.coverage_gaps
        ],
    }
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


def _serve(args: argparse.Namespace) -> int:
    workspace = _load_checked_workspace(args.root)
    repository_root = _repository_root()
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
