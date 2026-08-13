"""Run one frozen consolidation-breakout definition across reviewed canonical symbols."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import defaultdict
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

from trade_scout.app.operator_workspace import load_operator_workspace, validate_workspace_location
from trade_scout.data.canonical_storage import CanonicalDailyBarStore
from trade_scout.data.contracts import (
    DailyBar,
    DatasetVersion,
    PriceRepresentation,
    QualityStatus,
    ResearchBar,
    to_research_bar,
)
from trade_scout.data.reviewed_identity_snapshot import load_reviewed_identity_snapshot_candidate
from trade_scout.patterns.consolidation_breakout import ConsolidationBreakoutConfig, TrendFilter
from trade_scout.statistics.consolidation_batch import build_consolidation_batch_report


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run exploratory consolidation research across the reviewed canonical universe."
    )
    parser.add_argument("--root", type=Path, required=True, help="Private operator workspace root")
    parser.add_argument("--dataset-version", default=None)
    parser.add_argument("--horizon", type=int, default=20, choices=(5, 10, 20, 40, 60))
    parser.add_argument("--duration", type=int, default=20)
    parser.add_argument("--max-range-pct", type=float, default=0.12)
    parser.add_argument(
        "--trend-filter",
        default=TrendFilter.ABOVE_RISING_SMA_200.value,
        choices=tuple(item.value for item in TrendFilter),
    )
    parser.add_argument("--output", type=Path, default=None)
    return parser


def main() -> int:
    args = _parser().parse_args()
    repository_root = Path(__file__).resolve().parents[1]
    validate_workspace_location(args.root, repository_root=repository_root)
    workspace = load_operator_workspace(args.root)

    dataset_version = args.dataset_version or workspace.manifest.canonical_dataset_version
    if dataset_version is None:
        raise SystemExit("operator workspace has no selected canonical dataset")

    identity_path = (
        workspace.root / "evidence" / "instrument-identity" / "tiingo-reviewed-candidate.json"
    )
    if not identity_path.is_file():
        raise SystemExit("reviewed Tiingo identity candidate is missing")

    candidate = load_reviewed_identity_snapshot_candidate(identity_path)
    blocked = {gap.instrument_id for gap in candidate.coverage_gaps}
    links = tuple(
        item
        for item in candidate.provider_series_links
        if item.provider_id == "tiingo" and item.instrument_id not in blocked
    )
    if not links:
        raise SystemExit("reviewed identity candidate contains no fully covered Tiingo series")

    symbol_by_instrument = {item.instrument_id: item.query_symbol.upper() for item in links}
    if len(symbol_by_instrument) != len(links):
        raise SystemExit("reviewed Tiingo identity candidate contains duplicate instrument links")

    canonical = CanonicalDailyBarStore(workspace.canonical_root).load(
        DatasetVersion(dataset_version)
    )
    selected_by_symbol: dict[str, list[DailyBar]] = defaultdict(list)
    for bar in canonical:
        symbol = symbol_by_instrument.get(bar.instrument_id)
        if symbol is not None:
            selected_by_symbol[symbol].append(bar)

    missing = tuple(sorted(set(symbol_by_instrument.values()) - set(selected_by_symbol)))
    if missing:
        raise SystemExit(
            "selected canonical dataset is missing reviewed symbols: " + ", ".join(missing)
        )

    series_by_symbol: dict[str, tuple[ResearchBar, ...]] = {}
    for symbol in sorted(selected_by_symbol):
        bars = tuple(selected_by_symbol[symbol])
        if any(item.quality_status is not QualityStatus.PASS for item in bars):
            raise SystemExit(f"canonical rows for {symbol} include non-PASS quality states")
        series_by_symbol[symbol] = tuple(
            to_research_bar(
                item,
                representation=PriceRepresentation.SPLIT_ADJUSTED,
                eligibility=True,
            )
            for item in bars
        )

    config = ConsolidationBreakoutConfig(
        duration=args.duration,
        max_range_pct=args.max_range_pct,
        trend_filter=TrendFilter(args.trend_filter),
        cooldown_sessions=5,
    )
    report = build_consolidation_batch_report(
        series_by_symbol,
        config=config,
        selected_horizon=args.horizon,
    )

    report_payload = asdict(report)
    logical_json = json.dumps(report_payload, sort_keys=True, separators=(",", ":"))
    report_checksum = hashlib.sha256(logical_json.encode("utf-8")).hexdigest()
    payload = {
        "schema_version": "consolidation-batch-report-v0.1",
        "created_at": datetime.now(UTC).isoformat(),
        "identity_snapshot_version": candidate.snapshot_version,
        "identity_candidate_schema_version": candidate.schema_version,
        "provider_calls_made": False,
        "report_checksum_sha256": report_checksum,
        "report": report_payload,
    }

    output = args.output or (
        workspace.root
        / "evidence"
        / "research-batches"
        / (
            f"{dataset_version}__consolidation-batch-v0.1__"
            f"d{args.duration}__r{args.max_range_pct:.4f}__h{args.horizon}.json"
        )
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(output)

    print(
        json.dumps(
            {
                "dataset_version": report.dataset_version,
                "identity_snapshot_version": candidate.snapshot_version,
                "requested_symbol_count": report.requested_symbol_count,
                "completed_symbol_count": report.completed_symbol_count,
                "skipped_symbols": list(report.skipped_symbols),
                "total_event_count": report.total_event_count,
                "selected_horizon": report.selected_horizon,
                "report_checksum_sha256": report_checksum,
                "report_path": str(output),
                "provider_calls_made": False,
                "research_state": report.research_state,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
