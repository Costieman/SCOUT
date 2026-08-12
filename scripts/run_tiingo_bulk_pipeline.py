"""Run a large, resumable Tiingo operator batch with minimal interaction.

The pipeline deliberately separates acquisition from reviewed identity clearance. It can acquire a
large durable slice, re-profile every verified receipt, rebuild the current reviewed identity
candidate, promote the reviewed instrument master and prices, select the resulting canonical
dataset for the workspace, and leave all not-yet-reviewed symbols outside canonical research use.

A provider rate-limit pause is not treated as corruption: the underlying acquisition command
persists safe state, after which this runner continues with the durable symbols already available.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

from trade_scout.app.operator_workspace import (
    OperatorWorkspaceError,
    configure_operator_workspace,
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
from trade_scout.data.reviewed_identity_snapshot import load_reviewed_identity_snapshot_candidate


class BulkTiingoPipelineError(RuntimeError):
    """Raised when a bulk operator stage cannot continue safely."""


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Acquire, verify, profile, review-promote, and select a Tiingo batch."
    )
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument(
        "--acquire-max-symbols",
        type=int,
        default=100,
        help="Maximum additional S&P symbols to attempt in this run; use 0 to skip acquisition.",
    )
    parser.add_argument(
        "--no-select",
        action="store_true",
        help="Do not update workspace.json to select the newly promoted canonical dataset.",
    )
    return parser


def _run_stage(
    *,
    name: str,
    command: list[str],
    cwd: Path,
    log_root: Path,
) -> tuple[int, str, str]:
    completed = subprocess.run(
        command,
        cwd=cwd,
        check=False,
        text=True,
        capture_output=True,
    )
    stdout = completed.stdout.strip()
    stderr = completed.stderr.strip()
    (log_root / f"{name}.stdout.txt").write_text(
        stdout + ("\n" if stdout else ""),
        encoding="utf-8",
    )
    (log_root / f"{name}.stderr.txt").write_text(
        stderr + ("\n" if stderr else ""),
        encoding="utf-8",
    )
    if stdout:
        print(stdout)
    if stderr:
        print(stderr, file=sys.stderr)
    return completed.returncode, stdout, stderr


def _parse_single_json(text: str, stage: str) -> dict[str, object]:
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise BulkTiingoPipelineError(f"{stage} did not emit a single JSON object") from exc
    if not isinstance(payload, dict):
        raise BulkTiingoPipelineError(f"{stage} JSON output must be an object")
    return payload


def _verify_or_raise(workspace_root: Path) -> tuple[object, object]:
    workspace = load_operator_workspace(workspace_root)
    verification = verify_operator_workspace(workspace)
    if not verification.is_consistent:
        raise BulkTiingoPipelineError(
            "durable Tiingo evidence is inconsistent; bulk processing is blocked fail-closed"
        )
    return workspace, verification


def main() -> int:
    args = _parser().parse_args()
    if args.acquire_max_symbols < 0:
        raise SystemExit("--acquire-max-symbols must be zero or positive")

    repository_root = Path(__file__).resolve().parents[1]
    root = args.root.expanduser().resolve()
    validate_workspace_location(root, repository_root=repository_root)
    workspace, before = _verify_or_raise(root)

    run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    log_root = root / "evidence" / "bulk-tiingo" / run_id
    log_root.mkdir(parents=True, exist_ok=False)

    summary: dict[str, object] = {
        "schema_version": "tiingo-bulk-operator-run-v0.1",
        "run_id": run_id,
        "started_at": datetime.now(UTC).isoformat(),
        "requested_acquire_max_symbols": args.acquire_max_symbols,
        "durable_symbols_before": before.durable_completed_symbol_count,
        "stages": {},
    }

    try:
        if args.acquire_max_symbols:
            acquire_command = [
                sys.executable,
                str(repository_root / "scripts" / "trade_scout_workspace.py"),
                "acquire-tiingo",
                "--root",
                str(root),
                "--max-symbols",
                str(args.acquire_max_symbols),
            ]
            code, stdout, stderr = _run_stage(
                name="01-acquire",
                command=acquire_command,
                cwd=repository_root,
                log_root=log_root,
            )
            summary["stages"]["acquire"] = {
                "returncode": code,
                "stdout_log": str(log_root / "01-acquire.stdout.txt"),
                "stderr_log": str(log_root / "01-acquire.stderr.txt"),
            }
            if code not in (0,):
                raise BulkTiingoPipelineError(
                    "Tiingo acquisition returned a hard failure; inspect the saved stage logs"
                )

        workspace, after_acquire = _verify_or_raise(root)
        summary["durable_symbols_after_acquire"] = after_acquire.durable_completed_symbol_count

        profile = profile_durable_tiingo(
            receipt_root=workspace.tiingo_receipts_root,
            raw_root=workspace.tiingo_raw_root,
            storage_namespace=workspace.manifest.storage_namespace,
        )
        profile_path = root / "evidence" / "tiingo-profile" / "profile.json"
        persist_tiingo_durable_profile(profile_path, profile)
        summary["stages"]["profile"] = {
            "symbol_count": profile.symbol_count,
            "row_count": profile.total_row_count,
            "profile_path": str(profile_path),
        }

        expand_command = [
            sys.executable,
            str(repository_root / "scripts" / "expand_tiingo_reviewed_identity.py"),
            "--root",
            str(root),
        ]
        code, stdout, stderr = _run_stage(
            name="02-expand-identity",
            command=expand_command,
            cwd=repository_root,
            log_root=log_root,
        )
        summary["stages"]["expand_identity"] = {
            "returncode": code,
            "stdout_log": str(log_root / "02-expand-identity.stdout.txt"),
            "stderr_log": str(log_root / "02-expand-identity.stderr.txt"),
        }
        if code != 0:
            raise BulkTiingoPipelineError("reviewed identity expansion failed")
        identity_payload = _parse_single_json(stdout, "identity expansion")
        summary["reviewed_instrument_count"] = identity_payload.get("instrument_count")
        summary["deferred_symbols"] = identity_payload.get("deferred_symbols", [])

        candidate_path = root / "evidence" / "instrument-identity" / "tiingo-reviewed-candidate.json"
        candidate = load_reviewed_identity_snapshot_candidate(candidate_path)
        reviewed_query_symbols = {
            item.query_symbol
            for item in candidate.provider_series_links
            if item.provider_id == "tiingo"
        }
        completed_symbols = {
            path.parent.name
            for path in workspace.tiingo_receipts_root.rglob("*.json")
            if path.parent != workspace.tiingo_receipts_root
        }
        unreviewed = sorted(completed_symbols - reviewed_query_symbols)
        review_queue_path = log_root / "unreviewed-durable-symbols.json"
        review_queue_path.write_text(
            json.dumps(
                {
                    "schema_version": "tiingo-unreviewed-durable-symbols-v0.1",
                    "durable_symbol_count": len(completed_symbols),
                    "reviewed_query_symbol_count": len(reviewed_query_symbols),
                    "unreviewed_symbol_count": len(unreviewed),
                    "symbols": unreviewed,
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        summary["unreviewed_durable_symbol_count"] = len(unreviewed)
        summary["review_queue_path"] = str(review_queue_path)

        promote_command = [
            sys.executable,
            str(repository_root / "scripts" / "promote_tiingo_reviewed_prices.py"),
            "--root",
            str(root),
        ]
        code, stdout, stderr = _run_stage(
            name="03-promote-reviewed",
            command=promote_command,
            cwd=repository_root,
            log_root=log_root,
        )
        summary["stages"]["promote_reviewed"] = {
            "returncode": code,
            "stdout_log": str(log_root / "03-promote-reviewed.stdout.txt"),
            "stderr_log": str(log_root / "03-promote-reviewed.stderr.txt"),
        }
        if code != 0:
            raise BulkTiingoPipelineError("reviewed identity/price promotion failed")
        promotion_payload = _parse_single_json(stdout, "reviewed promotion")
        dataset_version = promotion_payload.get("dataset_version")
        if not isinstance(dataset_version, str) or not dataset_version:
            raise BulkTiingoPipelineError("promotion output did not include dataset_version")
        summary["promoted_symbol_count"] = promotion_payload.get("symbol_count")
        summary["promoted_record_count"] = promotion_payload.get("record_count")
        summary["canonical_dataset_version"] = dataset_version

        if not args.no_select:
            workspace = configure_operator_workspace(
                load_operator_workspace(root),
                canonical_dataset_version=dataset_version,
                scanner_required_session=workspace.manifest.scanner_required_session,
            )
            summary["canonical_dataset_selected"] = True
        else:
            summary["canonical_dataset_selected"] = False

        final_workspace = load_operator_workspace(root)
        summary["final_workspace_status"] = workspace_status_payload(final_workspace)
        summary["status"] = "COMPLETE"
        summary["finished_at"] = datetime.now(UTC).isoformat()
        summary_path = log_root / "summary.json"
        summary_path.write_text(
            json.dumps(summary, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        print(json.dumps(summary, indent=2, sort_keys=True))
        print(f"bulk Tiingo summary: {summary_path}")
        return 0
    except (BulkTiingoPipelineError, OperatorWorkspaceError, TiingoProfileError) as exc:
        summary["status"] = "BLOCKED"
        summary["error"] = str(exc)
        summary["finished_at"] = datetime.now(UTC).isoformat()
        summary_path = log_root / "summary.json"
        summary_path.write_text(
            json.dumps(summary, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        print(f"Tiingo bulk pipeline error: {exc}", file=sys.stderr)
        print(f"bulk Tiingo summary: {summary_path}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
