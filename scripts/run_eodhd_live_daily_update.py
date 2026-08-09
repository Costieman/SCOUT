"""Run one live EODHD correction-lookback cycle against an existing canonical parent dataset."""

from __future__ import annotations

import argparse
import os
from datetime import UTC, date, datetime
from pathlib import Path

from trade_scout.data.acceptance import AcceptanceEvidenceStatus
from trade_scout.data.canonical_storage import CanonicalDailyBarStore
from trade_scout.data.contracts import DatasetVersion
from trade_scout.data.providers.eodhd_campaign import EodhdCampaignCase, run_eodhd_canonical_case
from trade_scout.data.providers.eodhd_daily_update import (
    assess_eodhd_daily_update,
    matching_eodhd_parent_bars,
)
from trade_scout.data.providers.eodhd_daily_update_report import write_eodhd_daily_update_report
from trade_scout.data.runtime_evidence_dispatch import assess_runtime_evidence
from trade_scout.data.runtime_evidence_registration import register_runtime_evidence

_DEFAULT_PARENT_ROOT = Path("runtime/eodhd-campaign-suite/representative-aggregate/data")
_DEFAULT_PARENT_VERSION = "eodhd-phase1-representative-aggregate-v0.1"
_DEFAULT_OUTPUT = Path("runtime/eodhd-daily-update-live")
_DEFAULT_MANIFEST = Path("runtime/phase1-evidence/manifest.json")


def _iso_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("dates must use YYYY-MM-DD") from exc


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Fetch one explicit EODHD symbol over a correction-lookback window, compare the live "
            "canonical observations with an immutable parent dataset, emit strict incremental-"
            "update evidence, and register it only when live overlap is demonstrated."
        )
    )
    parser.add_argument("--symbol", required=True, help="EODHD symbol, e.g. AAPL.US")
    parser.add_argument("--start", type=_iso_date, required=True)
    parser.add_argument("--end", type=_iso_date, required=True)
    parser.add_argument("--parent-root", type=Path, default=_DEFAULT_PARENT_ROOT)
    parser.add_argument("--parent-version", default=_DEFAULT_PARENT_VERSION)
    parser.add_argument("--target-version", required=True)
    parser.add_argument("--output-root", type=Path, default=_DEFAULT_OUTPUT)
    parser.add_argument("--manifest", type=Path, default=_DEFAULT_MANIFEST)
    return parser


def _token() -> str:
    token = (
        os.environ.get("EODHD_API_TOKEN", "").strip() or os.environ.get("EODHD_API_KEY", "").strip()
    )
    if not token:
        raise SystemExit("EODHD_API_TOKEN or EODHD_API_KEY is not configured")
    return token


def main() -> int:
    args = _parser().parse_args()
    if args.end < args.start:
        raise SystemExit("--end must not precede --start")

    parent_version = DatasetVersion(args.parent_version)
    target_version = DatasetVersion(args.target_version)
    if parent_version == target_version:
        raise SystemExit("--target-version must differ from --parent-version")

    parent_store = CanonicalDailyBarStore(args.parent_root)
    parent = parent_store.load(parent_version)

    incoming_root = args.output_root / "incoming" / str(target_version)
    incoming_store = CanonicalDailyBarStore(incoming_root / "data")
    if incoming_store.get_manifest(target_version) is None:
        case = EodhdCampaignCase(
            symbol=args.symbol,
            start=args.start,
            end=args.end,
            expected_active=True,
        )
        run_eodhd_canonical_case(
            _token(),
            case,
            raw_root=incoming_root / "raw",
            canonical_store=incoming_store,
            dataset_id="eodhd-live-daily-update-evidence",
            dataset_version=target_version,
            created_at=datetime.now(UTC),
            transformation_version="provider-normalization-v1",
            adjustment_policy_version="split-only-v1",
            universe_construction_version="bounded-live-update-evidence-v1",
            quality_check_version="daily-bar-quality-v1",
        )
    else:
        print(f"Reusing checkpointed live incoming dataset: {target_version}")

    incoming = incoming_store.load(target_version)
    parent_slice = matching_eodhd_parent_bars(parent, incoming)

    evidence = assess_eodhd_daily_update(
        parent_slice,
        incoming,
        target_dataset_version=target_version,
        correction_window_start=args.start,
    )
    report_path = args.output_root / "report" / str(target_version) / "daily-update-evidence.json"
    write_eodhd_daily_update_report(
        evidence,
        path=report_path,
        live_provider_observation=True,
    )
    assessment = assess_runtime_evidence(report_path)
    print(f"Daily-update evidence: {assessment.evidence.status.value}")
    print(assessment.evidence.note)
    print(f"Report: {report_path}")

    if assessment.evidence.status is not AcceptanceEvidenceStatus.DEMONSTRATED:
        print(
            "Evidence was not registered because this run did not demonstrate live correction-"
            "lookback overlap. Re-run with a window that overlaps the parent dataset."
        )
        return 2

    artifact = register_runtime_evidence(
        report_path=report_path,
        evidence_root=Path("runtime"),
        manifest_path=args.manifest,
        artifact_id=f"eodhd-daily-update:{target_version}",
        producer="scripts/run_eodhd_live_daily_update.py",
        provider_ids=("eodhd",),
    )
    print(f"Registered runtime evidence: {artifact.artifact_id}")
    print(f"Evidence manifest: {args.manifest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
