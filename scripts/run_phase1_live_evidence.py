"""Run the remaining live Phase 1 provider-evidence campaigns from one resumable entry point."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

from trade_scout.data.runtime_evidence_registration import register_runtime_evidence

_PRIMARY_ROOT = Path("runtime/eodhd-campaign-suite")
_SECONDARY_ROOT = Path("runtime/eodhd-tiingo-cross-validation")
_MANIFEST = Path("runtime/phase1-evidence/manifest.json")


def _positive_int(value: str) -> int:
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError("value must be positive")
    return parsed


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Advance the remaining Phase 1 live provider evidence in a conservative order: "
            "representative EODHD campaign first, then bounded EODHD/Tiingo validation. "
            "Every stage is resumable and runtime evidence is checksum-registered when available."
        )
    )
    parser.add_argument("--max-new-cases", type=_positive_int, default=10)
    parser.add_argument("--primary-root", type=Path, default=_PRIMARY_ROOT)
    parser.add_argument("--secondary-root", type=Path, default=_SECONDARY_ROOT)
    parser.add_argument("--manifest", type=Path, default=_MANIFEST)
    parser.add_argument(
        "--skip-secondary",
        action="store_true",
        help="Advance only the representative EODHD campaign.",
    )
    parser.add_argument(
        "--status-only",
        action="store_true",
        help="Report persisted live-evidence state without provider calls.",
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


def _secondary_report(root: Path) -> Path:
    return root / "report" / "cross-provider-evidence.json"


def _print_status(primary_root: Path, secondary_root: Path) -> None:
    summary = _latest_primary_summary(primary_root)
    if summary is None:
        print("Representative EODHD campaign: not started")
    else:
        print(
            "Representative EODHD campaign: "
            f"{summary.get('completed_case_count', 0)}/{summary.get('expected_case_count', '?')} "
            f"cases complete; complete={summary.get('complete') is True}"
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


def _has_eodhd_token() -> bool:
    return bool(
        os.environ.get("EODHD_API_TOKEN", "").strip() or os.environ.get("EODHD_API_KEY", "").strip()
    )


def _has_tiingo_token() -> bool:
    return bool(os.environ.get("TIINGO_API_KEY", "").strip())


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
    secondary_root: Path = args.secondary_root

    if args.status_only:
        _print_status(primary_root, secondary_root)
        return 0

    if not _has_eodhd_token():
        raise SystemExit("EODHD_API_TOKEN or EODHD_API_KEY is not configured")

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
        print(
            "Primary EODHD evidence stage did not complete cleanly; secondary validation withheld."
        )
        return primary_code

    summary = _latest_primary_summary(primary_root)
    _print_status(primary_root, secondary_root)
    if summary is None or summary.get("complete") is not True:
        print("Primary campaign remains checkpointed; rerun this identical command to continue.")
        return 0

    if args.skip_secondary:
        print("Primary campaign is complete; secondary validation was explicitly skipped.")
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

    _print_status(primary_root, secondary_root)
    print("Live provider evidence advanced. Checked-in acceptance ledgers remain authoritative.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
