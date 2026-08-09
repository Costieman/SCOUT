"""Replay a registered canonical dataset through the Parquet/DuckDB benchmark path."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from datetime import date
from pathlib import Path

from trade_scout.data.canonical_storage import CanonicalDailyBarStore
from trade_scout.data.contracts import DatasetVersion
from trade_scout.data.instrument_storage import InstrumentMasterStore
from trade_scout.data.representative_sample import (
    RepresentativeSampleAssessment,
    assess_representative_sample,
    load_representative_sample_policy,
)
from trade_scout.data.storage_benchmark import StorageBenchmarkResult, benchmark_registered_dataset

_DEFAULT_REPRESENTATIVE_POLICY = Path("configs/representative_storage_sample_v0.1.json")


def _date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("dates must use YYYY-MM-DD") from exc


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Benchmark an already registered canonical Trade Scout dataset by replaying it into "
            "a separate fresh Parquet/DuckDB benchmark root."
        )
    )
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--dataset-version", required=True)
    parser.add_argument("--instrument-snapshot-version", required=True)
    parser.add_argument(
        "--representative-policy", type=Path, default=_DEFAULT_REPRESENTATIVE_POLICY
    )
    parser.add_argument("--benchmark-root", type=Path, required=True)
    parser.add_argument("--query-start", type=_date, required=True)
    parser.add_argument("--query-end", type=_date, required=True)
    return parser


def main() -> int:
    args = _parser().parse_args()
    dataset_version = DatasetVersion(args.dataset_version)
    source_bars = CanonicalDailyBarStore(args.source_root).load(dataset_version)
    instrument_snapshot = InstrumentMasterStore(args.source_root).load(
        args.instrument_snapshot_version
    )
    policy = load_representative_sample_policy(args.representative_policy)
    representative_assessment = assess_representative_sample(
        source_bars,
        instrument_snapshot.instruments,
        policy=policy,
    )

    result = benchmark_registered_dataset(
        source_root=args.source_root,
        dataset_version=dataset_version,
        benchmark_root=args.benchmark_root,
        query_start=args.query_start,
        query_end=args.query_end,
    )
    report_root = args.benchmark_root / "report"
    report_root.mkdir(parents=True, exist_ok=True)
    payload = _payload(
        result,
        source_root=args.source_root,
        instrument_snapshot_version=args.instrument_snapshot_version,
        representative_assessment=representative_assessment,
    )
    json_path = report_root / "storage-benchmark.json"
    json_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    markdown_path = report_root / "storage-benchmark.md"
    markdown_path.write_text(_markdown(payload), encoding="utf-8")
    print(markdown_path.read_text(encoding="utf-8"))
    return 0


def _payload(
    result: StorageBenchmarkResult,
    *,
    source_root: Path,
    instrument_snapshot_version: str,
    representative_assessment: RepresentativeSampleAssessment,
) -> dict[str, object]:
    payload = asdict(result)
    payload["dataset_version"] = str(result.dataset_version)
    payload["first_trade_date"] = result.first_trade_date.isoformat()
    payload["last_trade_date"] = result.last_trade_date.isoformat()
    payload["records_per_parquet_megabyte"] = result.records_per_parquet_megabyte
    payload["source_root"] = str(source_root)
    payload["instrument_snapshot_version"] = instrument_snapshot_version
    payload["representative_sample_policy_version"] = representative_assessment.policy_version
    payload["representative_sample_accepted"] = representative_assessment.accepted
    payload["representative_sample_failures"] = list(representative_assessment.failures)
    payload["representative_sample_scope"] = {
        "record_count": representative_assessment.record_count,
        "unique_instrument_count": representative_assessment.unique_instrument_count,
        "first_trade_date": representative_assessment.first_trade_date.isoformat(),
        "last_trade_date": representative_assessment.last_trade_date.isoformat(),
        "span_days": representative_assessment.span_days,
        "delisted_instrument_count": representative_assessment.delisted_instrument_count,
        "exchange_count": representative_assessment.exchange_count,
        "common_stock_count": representative_assessment.common_stock_count,
    }
    payload["acceptance_note"] = (
        "The sample satisfied the checked-in Phase 1 representativeness policy."
        if representative_assessment.accepted
        else "The benchmark completed, but the sample does not satisfy the checked-in Phase 1 "
        "representativeness policy; storage acceptance must remain partial."
    )
    return payload


def _markdown(payload: dict[str, object]) -> str:
    failures = payload["representative_sample_failures"]
    if not isinstance(failures, list):
        raise TypeError("representative sample failures must be a list")
    failure_text = ", ".join(str(item) for item in failures) if failures else "none"
    return "\n".join(
        [
            "# Canonical storage benchmark",
            "",
            f"Dataset version: `{payload['dataset_version']}`",
            f"Instrument snapshot: `{payload['instrument_snapshot_version']}`",
            f"Source root: `{payload['source_root']}`",
            f"Records: {payload['record_count']}",
            f"Unique instruments: {payload['unique_instrument_count']}",
            f"Date coverage: {payload['first_trade_date']} to {payload['last_trade_date']}",
            f"Parquet bytes: {payload['parquet_bytes']}",
            f"DuckDB metadata bytes: {payload['metadata_bytes']}",
            f"Promotion seconds: {float(payload['promote_seconds']):.6f}",
            f"Full-load seconds: {float(payload['full_load_seconds']):.6f}",
            f"Filtered-query seconds: {float(payload['filtered_query_seconds']):.6f}",
            f"Filtered-query rows: {payload['filtered_query_count']}",
            "",
            "## Phase 1 representativeness gate",
            "",
            f"Policy: `{payload['representative_sample_policy_version']}`",
            f"Accepted: **{payload['representative_sample_accepted']}**",
            f"Failed conditions: {failure_text}",
            "",
            str(payload["acceptance_note"]),
            "",
        ]
    )


if __name__ == "__main__":
    raise SystemExit(main())
