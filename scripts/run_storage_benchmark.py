"""Replay a registered canonical dataset through the Parquet/DuckDB benchmark path."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from datetime import date
from pathlib import Path

from trade_scout.data.contracts import DatasetVersion
from trade_scout.data.storage_benchmark import StorageBenchmarkResult, benchmark_registered_dataset


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
    parser.add_argument("--benchmark-root", type=Path, required=True)
    parser.add_argument("--query-start", type=_date, required=True)
    parser.add_argument("--query-end", type=_date, required=True)
    return parser


def main() -> int:
    args = _parser().parse_args()
    result = benchmark_registered_dataset(
        source_root=args.source_root,
        dataset_version=DatasetVersion(args.dataset_version),
        benchmark_root=args.benchmark_root,
        query_start=args.query_start,
        query_end=args.query_end,
    )
    report_root = args.benchmark_root / "report"
    report_root.mkdir(parents=True, exist_ok=True)
    payload = _payload(result, source_root=args.source_root)
    json_path = report_root / "storage-benchmark.json"
    json_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    markdown_path = report_root / "storage-benchmark.md"
    markdown_path.write_text(_markdown(payload), encoding="utf-8")
    print(markdown_path.read_text(encoding="utf-8"))
    return 0


def _payload(result: StorageBenchmarkResult, *, source_root: Path) -> dict[str, object]:
    payload = asdict(result)
    payload["dataset_version"] = str(result.dataset_version)
    payload["first_trade_date"] = result.first_trade_date.isoformat()
    payload["last_trade_date"] = result.last_trade_date.isoformat()
    payload["records_per_parquet_megabyte"] = result.records_per_parquet_megabyte
    payload["source_root"] = str(source_root)
    payload["representative_sample_accepted"] = False
    payload["acceptance_note"] = (
        "Measurements alone do not establish that the source dataset is representative enough "
        "to close the Phase 1 storage-benchmark criterion. Sample scope must be reviewed "
        "separately."
    )
    return payload


def _markdown(payload: dict[str, object]) -> str:
    return "\n".join(
        [
            "# Canonical storage benchmark",
            "",
            f"Dataset version: `{payload['dataset_version']}`",
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
            "## Phase 1 interpretation",
            "",
            "**Representative-sample acceptance is not automatic.** "
            + str(payload["acceptance_note"]),
            "",
        ]
    )


if __name__ == "__main__":
    raise SystemExit(main())
