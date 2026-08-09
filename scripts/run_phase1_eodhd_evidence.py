"""Run or resume the Phase 1 EODHD evidence workflow from one operational entry point."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

from trade_scout.data.runtime_evidence_registration import register_runtime_evidence

_DEFAULT_PLAN = Path("runtime/eodhd-representative-plan/eodhd-phase1-representative-v0.1.json")
_DEFAULT_ROOT = Path("runtime/eodhd-campaign-suite")
_DEFAULT_POLICY = Path("configs/representative_storage_sample_v0.1.json")
_DEFAULT_MANIFEST = Path("runtime/phase1-evidence/manifest.json")
_DATASET_VERSION = "eodhd-phase1-representative-aggregate-v0.1"


def _positive_int(value: str) -> int:
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError("value must be positive")
    return parsed


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Create the representative EODHD plan when needed, run a bounded resumable batch, "
            "and automatically aggregate, benchmark, and register evidence once the campaign "
            "completes. Re-running the same command resumes completed work."
        )
    )
    parser.add_argument("--plan", type=Path, default=_DEFAULT_PLAN)
    parser.add_argument("--output-root", type=Path, default=_DEFAULT_ROOT)
    parser.add_argument("--policy", type=Path, default=_DEFAULT_POLICY)
    parser.add_argument("--manifest", type=Path, default=_DEFAULT_MANIFEST)
    parser.add_argument("--max-new-cases", type=_positive_int, default=10)
    parser.add_argument(
        "--status-only",
        action="store_true",
        help="Report locally persisted campaign progress without provider calls.",
    )
    return parser


def _run(*parts: str) -> None:
    command = [sys.executable, *parts]
    print("+", " ".join(command))
    subprocess.run(command, check=True)


def _latest_summary(root: Path) -> tuple[Path, dict[str, object]] | None:
    candidates = sorted((root / "report").glob("*/campaign-summary.json"))
    if not candidates:
        return None
    path = candidates[-1]
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise SystemExit(f"Campaign summary is not a JSON object: {path}")
    return path, payload


def _print_status(root: Path) -> None:
    latest = _latest_summary(root)
    if latest is None:
        print("Campaign status: not started")
        return
    path, payload = latest
    print(f"Campaign status file: {path}")
    print(f"Campaign ID: {payload.get('campaign_id', '-')}")
    print(
        "Cases: "
        f"{payload.get('completed_case_count', 0)}/{payload.get('expected_case_count', '?')} "
        f"completed; {payload.get('remaining_case_count', '?')} remaining"
    )
    print(f"Complete: {payload.get('complete') is True}")


def _require_eodhd_token() -> None:
    token = (
        os.environ.get("EODHD_API_TOKEN", "").strip()
        or os.environ.get("EODHD_API_KEY", "").strip()
    )
    if not token:
        raise SystemExit("EODHD_API_TOKEN or EODHD_API_KEY is not configured")


def main() -> int:
    args = _parser().parse_args()
    output_root: Path = args.output_root
    plan: Path = args.plan

    if args.status_only:
        _print_status(output_root)
        return 0

    _require_eodhd_token()
    if not plan.is_file():
        print("No frozen representative plan found; creating it from the live EODHD inventory.")
        _run("scripts/plan_eodhd_representative_campaign.py", "--output", str(plan))

    _run(
        "scripts/run_eodhd_campaign_suite.py",
        "--plan",
        str(plan),
        "--output-root",
        str(output_root),
        "--max-new-cases",
        str(args.max_new_cases),
    )

    latest = _latest_summary(output_root)
    if latest is None:
        raise SystemExit("Campaign runner completed without producing a campaign summary")
    _, summary = latest
    _print_status(output_root)
    if summary.get("complete") is not True:
        print("Campaign is checkpointed. Re-run this identical command to continue.")
        return 0

    campaign_id = summary.get("campaign_id")
    if not isinstance(campaign_id, str) or not campaign_id:
        raise SystemExit("Completed campaign summary is missing campaign_id")

    aggregate_report = output_root / "representative-aggregate" / "report" / f"{campaign_id}.json"
    if not aggregate_report.is_file():
        _run(
            "scripts/aggregate_eodhd_campaign.py",
            "--campaign-id",
            campaign_id,
            "--output-root",
            str(output_root),
            "--dataset-version",
            _DATASET_VERSION,
        )

    plan_payload = json.loads(plan.read_text(encoding="utf-8"))
    cases = plan_payload.get("cases") if isinstance(plan_payload, dict) else None
    if not isinstance(cases, list) or not cases:
        raise SystemExit("Representative campaign plan has no cases")
    starts = [case.get("start") for case in cases if isinstance(case, dict)]
    ends = [case.get("end") for case in cases if isinstance(case, dict)]
    if not starts or not ends or any(not isinstance(item, str) for item in (*starts, *ends)):
        raise SystemExit("Representative campaign plan contains invalid case dates")

    benchmark_report = output_root / "representative-aggregate" / "report" / "storage-evidence.json"
    if not benchmark_report.is_file():
        _run(
            "scripts/run_eodhd_campaign_benchmark.py",
            "--source-root",
            str(output_root / "representative-aggregate" / "data"),
            "--dataset-version",
            _DATASET_VERSION,
            "--aggregate-report",
            str(aggregate_report),
            "--policy",
            str(args.policy),
            "--benchmark-root",
            str(output_root / "representative-aggregate" / "benchmark"),
            "--query-start",
            min(starts),
            "--query-end",
            max(ends),
            "--report",
            str(benchmark_report),
        )

    artifact = register_runtime_evidence(
        report_path=benchmark_report,
        evidence_root=Path("runtime"),
        manifest_path=args.manifest,
        artifact_id=f"eodhd-storage-benchmark:{campaign_id}",
        producer="scripts/run_phase1_eodhd_evidence.py",
        provider_ids=("eodhd",),
    )
    print(f"Registered runtime evidence: {artifact.artifact_id}")
    print(f"Evidence manifest: {args.manifest}")
    print("Phase 1 acceptance is still controlled by semantic review and the checked-in ledgers.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
