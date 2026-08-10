"""Render the Trade Scout shell from persisted Phase 1 data-health evidence."""

from __future__ import annotations

import argparse
from datetime import UTC, date, datetime
from pathlib import Path

from trade_scout.app.application_snapshot_service import build_phase1_application_snapshot
from trade_scout.app.data_health_service import DataHealthSourcePaths, build_data_health_summary
from trade_scout.app.low_fidelity import render_application_html


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
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
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("runtime/ui-data-health/index.html"),
    )
    return parser


def main() -> int:
    args = _parser().parse_args()
    health = build_data_health_summary(
        DataHealthSourcePaths(
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
    )
    snapshot = build_phase1_application_snapshot(
        health,
        generated_at=datetime.now(UTC),
        build_label="data-health-v0.1",
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(render_application_html(snapshot), encoding="utf-8")
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
