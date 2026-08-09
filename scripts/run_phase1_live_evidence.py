"""Run the remaining live Phase 1 provider-evidence campaigns from one resumable entry point."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

from trade_scout.data.live_evidence_preflight import (
    LiveEvidencePreflight,
    assess_live_evidence_preflight,
)
from trade_scout.data.providers.eodhd_campaign_plan import load_eodhd_campaign_plan
from trade_scout.data.providers.eodhd_daily_update_plan import plan_eodhd_daily_update_probe
from trade_scout.data.runtime_evidence_registration import register_runtime_evidence

_PRIMARY_ROOT = Path("runtime/eodhd-campaign-suite")
_DAILY_ROOT = Path("runtime/eodhd-daily-update-live")
_SECONDARY_ROOT = Path("runtime/eodhd-tiingo-cross-validation")
_MANIFEST = Path("runtime/phase1-evidence/manifest.json")
_REPRESENTATIVE_POLICY = Path("configs/representative_storage_sample_v0.1.json")
_PROVIDER_LEDGER = Path("configs/provider_acceptance_eodhd_v0.1.json")
_DATA_LEDGER = Path("configs/data_foundation_acceptance_v0.1.json")
_REPRESENTATIVE_PLAN = Path(
    "runtime/eodhd-representative-plan/eodhd-phase1-representative-v0.1.json"
)


def _positive_int(value: str) -> int:
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError("value must be positive")
    return parsed


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Advance the remaining Phase 1 live provider evidence in a conservative order: "
            "representative EODHD campaign, live correction-lookback probe, then bounded "
            "EODHD/Tiingo validation. Every stage is resumable."
        )
    )
    parser.add_argument("--max-new-cases", type=_positive_int, default=10)
    parser.add_argument("--primary-root", type=Path, default=_PRIMARY_ROOT)
    parser.add_argument("--daily-root", type=Path, default=_DAILY_ROOT)
    parser.add_argument("--secondary-root", type=Path, default=_SECONDARY_ROOT)
    parser.add_argument("--manifest", type=Path, default=_MANIFEST)
    parser.add_argument(
        "--skip-daily-update",
        action="store_true",
        help="Do not run the live EODHD correction-lookback probe after primary completion.",
    )
    parser.add_argument(
        "--skip-secondary",
        action="store_true",
        help="Do not run EODHD/Tiingo validation after primary completion.",
    )
    parser.add_argument(
        "--status-only",
        action="store_true",
        help="Report persisted live-evidence state without provider calls.",
    )
    parser.add_argument(
        "--preflight",
        action="store_true",
        help="Validate local prerequisites and report the next safe action without provider calls.",
    )
    return parser


def _run(*parts: str) -> int:
    command = [sys.executable, *parts]
    print("+", " ".join(command))
    return subprocess.run(command, check=False).returncode


def _latest_primary_summary(root: Path) -> dict[str, object] | None:
    candidates = sorted((root / "report").glob("*/campaign-summary.json"))
    if not candidates:
        return None
    payload = json.loads(candidates[-1].read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise SystemExit("Primary EODHD campaign summary is not a JSON object")
    return payload


def _latest_daily_report(root: Path) -> dict[str, object] | None:
    candidates = sorted((root / "report").glob("*/daily-update-evidence.json"))
    if not candidates:
        return None
    payload = json.loads(candidates[-1].read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise SystemExit("EODHD daily-update report is not a JSON object")
    return payload


def _secondary_report(root: Path) -> Path:
    return root / "report" / "cross-provider-evidence.json"


def _print_status(primary_root: Path, daily_root: Path, secondary_root: Path) -> None:
    summary = _latest_primary_summary(primary_root)
    if summary is None:
        print("Representative EODHD campaign: not started")
    else:
        print(
            "Representative EODHD campaign: "
            f"{summary.get('completed_case_count', 0)}/{summary.get('expected_case_count', '?')} "
            f"cases complete; complete={summary.get('complete') is True}"
        )

    daily = _latest_daily_report(daily_root)
    if daily is None:
        print("EODHD correction-lookback probe: not started")
    else:
        overlap = int(daily.get("revised_count", 0)) + int(
            daily.get("unchanged_incoming_count", 0)
        )
        print(
            "EODHD correction-lookback probe: "
            f"live={daily.get('live_provider_observation') is True}; overlap={overlap}; "
            f"target={daily.get('target_dataset_version', '?')}"
        )

    report = _secondary_report(secondary_root)
    if not report.is_file():
        print("EODHD/Tiingo validation: not started")
        return
    payload = json.loads(report.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise SystemExit("Secondary validation report is not a JSON object")
    print(
        "EODHD/Tiingo validation: "
        f"{payload.get('completed_case_count', 0)}/{payload.get('expected_case_count', '?')} "
        f"cases complete; complete={payload.get('complete') is True}; "
        f"unresolved={payload.get('unresolved_discrepancy_count', '?')}"
    )


def _preflight() -> LiveEvidencePreflight:
    return assess_live_evidence_preflight(
        environment=os.environ,
        representative_policy=_REPRESENTATIVE_POLICY,
        provider_ledger=_PROVIDER_LEDGER,
        data_ledger=_DATA_LEDGER,
        representative_plan=_REPRESENTATIVE_PLAN,
    )


def _print_preflight() -> bool:
    report = _preflight()
    print("Phase 1 live-evidence preflight")
    print(f"Primary EODHD stage ready: {report.primary_ready}")
    print(f"Secondary EODHD/Tiingo stage ready: {report.secondary_ready}")
    print(f"Frozen representative plan present: {report.plan_present}")
    if report.blockers:
        print("Blockers:")
        for blocker in report.blockers:
            print(f"- {blocker}")
    else:
        print("Blockers: none")
    if report.notes:
        print("Notes:")
        for note in report.notes:
            print(f"- {note}")
    if report.primary_ready:
        print(
            "Next safe action: uv run python scripts/run_phase1_live_evidence.py --max-new-cases 10"
        )
    else:
        print("Next safe action: resolve the blockers above; do not start provider calls yet.")
    return report.primary_ready


def _has_tiingo_token() -> bool:
    return bool(os.environ.get("TIINGO_API_KEY", "").strip())


def _run_daily_update_probe(*, daily_root: Path, manifest: Path) -> int:
    campaign = load_eodhd_campaign_plan(_REPRESENTATIVE_PLAN)
    probe = plan_eodhd_daily_update_probe(campaign, run_date=datetime.now(UTC).date())
    print(
        "Planned EODHD correction-lookback probe: "
        f"{probe.symbol} {probe.start}..{probe.end} -> {probe.target_dataset_version}"
    )
    return _run(
        "scripts/run_eodhd_live_daily_update.py",
        "--symbol",
        probe.symbol,
        "--start",
        probe.start.isoformat(),
        "--end",
        probe.end.isoformat(),
        "--target-version",
        str(probe.target_dataset_version),
        "--output-root",
        str(daily_root),
        "--manifest",
        str(manifest),
    )


def _register_secondary(report: Path, *, manifest: Path) -> None:
    artifact = register_runtime_evidence(
        report_path=report,
        evidence_root=Path("runtime"),
        manifest_path=manifest,
        artifact_id="eodhd-tiingo-cross-validation-v0.1",
        producer="scripts/run_phase1_live_evidence.py",
        provider_ids=("eodhd", "tiingo"),
    )
    print(f"Registered secondary runtime evidence: {artifact.artifact_id}")


def main() -> int:
    args = _parser().parse_args()
    primary_root: Path = args.primary_root
    daily_root: Path = args.daily_root
    secondary_root: Path = args.secondary_root

    if args.preflight:
        return 0 if _print_preflight() else 2
    if args.status_only:
        _print_status(primary_root, daily_root, secondary_root)
        return 0

    if not _preflight().primary_ready:
        _print_preflight()
        return 2

    primary_code = _run(
        "scripts/run_phase1_eodhd_evidence.py",
        "--output-root",
        str(primary_root),
        "--manifest",
        str(args.manifest),
        "--max-new-cases",
        str(args.max_new_cases),
    )
    if primary_code != 0:
        print("Primary EODHD evidence stage did not complete cleanly; later stages withheld.")
        return primary_code

    summary = _latest_primary_summary(primary_root)
    _print_status(primary_root, daily_root, secondary_root)
    if summary is None or summary.get("complete") is not True:
        print("Primary campaign remains checkpointed; rerun this identical command to continue.")
        return 0

    if not args.skip_daily_update:
        daily_code = _run_daily_update_probe(daily_root=daily_root, manifest=args.manifest)
        if daily_code != 0:
            print(
                "Daily-update evidence remains outstanding or needs review; secondary validation "
                "can still proceed independently."
            )
    else:
        print("Primary campaign is complete; daily-update probe was explicitly skipped.")

    if args.skip_secondary:
        print("Secondary validation was explicitly skipped.")
        return 0
    if not _has_tiingo_token():
        print(
            "Primary campaign is complete, but TIINGO_API_KEY is not configured. "
            "Secondary validation remains outstanding."
        )
        return 0

    secondary_code = _run(
        "scripts/run_eodhd_tiingo_cross_validation.py",
        "--output-root",
        str(secondary_root),
    )
    report = _secondary_report(secondary_root)
    if report.is_file():
        _register_secondary(report, manifest=args.manifest)
    if secondary_code != 0:
        print("Secondary validation is checkpointed or requires discrepancy review.")
        return secondary_code

    _print_status(primary_root, daily_root, secondary_root)
    print("Live provider evidence advanced. Checked-in acceptance ledgers remain authoritative.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
