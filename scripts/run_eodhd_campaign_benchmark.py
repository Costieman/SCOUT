"""Assess and benchmark an aggregated representative EODHD Phase 1 dataset."""

from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path

from trade_scout.data.contracts import DatasetVersion, InstrumentId, InstrumentRecord, SecurityType
from trade_scout.data.eodhd_campaign_benchmark import assess_and_benchmark_eodhd_campaign
from trade_scout.data.representative_sample import load_representative_sample_policy


def _iso_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("expected ISO date YYYY-MM-DD") from exc


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Apply the explicit representative-sample policy to one aggregated EODHD canonical "
            "dataset and benchmark it only if the scope gate passes."
        )
    )
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--dataset-version", required=True)
    parser.add_argument("--instrument-manifest", type=Path, required=True)
    parser.add_argument("--policy", type=Path, required=True)
    parser.add_argument("--benchmark-root", type=Path, required=True)
    parser.add_argument("--query-start", type=_iso_date, required=True)
    parser.add_argument("--query-end", type=_iso_date, required=True)
    parser.add_argument("--report", type=Path, required=True)
    return parser


def main() -> int:
    args = _parser().parse_args()
    instruments = _load_instruments(args.instrument_manifest)
    policy = load_representative_sample_policy(args.policy)
    evidence = assess_and_benchmark_eodhd_campaign(
        source_root=args.source_root,
        dataset_version=DatasetVersion(args.dataset_version),
        instruments=instruments,
        policy=policy,
        benchmark_root=args.benchmark_root,
        query_start=args.query_start,
        query_end=args.query_end,
    )
    assessment = evidence.representative_sample
    benchmark = evidence.storage_benchmark
    report = {
        "schema_version": "eodhd-campaign-storage-evidence-v0.1",
        "dataset_version": str(evidence.dataset_version),
        "representative_sample_accepted": evidence.representative_sample_accepted,
        "representative_sample": {
            "policy_version": assessment.policy_version,
            "record_count": assessment.record_count,
            "unique_instrument_count": assessment.unique_instrument_count,
            "first_trade_date": assessment.first_trade_date.isoformat(),
            "last_trade_date": assessment.last_trade_date.isoformat(),
            "span_days": assessment.span_days,
            "delisted_instrument_count": assessment.delisted_instrument_count,
            "exchange_count": assessment.exchange_count,
            "common_stock_count": assessment.common_stock_count,
            "failures": list(assessment.failures),
        },
        "storage_benchmark": None if benchmark is None else {
            "record_count": benchmark.record_count,
            "unique_instrument_count": benchmark.unique_instrument_count,
            "first_trade_date": benchmark.first_trade_date.isoformat(),
            "last_trade_date": benchmark.last_trade_date.isoformat(),
            "parquet_bytes": benchmark.parquet_bytes,
            "metadata_bytes": benchmark.metadata_bytes,
            "promote_seconds": benchmark.promote_seconds,
            "full_load_seconds": benchmark.full_load_seconds,
            "filtered_query_seconds": benchmark.filtered_query_seconds,
            "filtered_query_count": benchmark.filtered_query_count,
            "records_per_parquet_megabyte": benchmark.records_per_parquet_megabyte,
        },
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(args.report)
    return 0 if evidence.representative_sample_accepted else 2


def _load_instruments(path: Path) -> tuple[InstrumentRecord, ...]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError("instrument manifest must be a JSON list")
    instruments: list[InstrumentRecord] = []
    for raw in payload:
        if not isinstance(raw, dict):
            raise ValueError("instrument manifest entries must be objects")
        instruments.append(
            InstrumentRecord(
                instrument_id=InstrumentId(_text(raw, "instrument_id")),
                primary_symbol=_text(raw, "primary_symbol"),
                name=_text(raw, "name"),
                exchange=_text(raw, "exchange"),
                security_type=SecurityType(_text(raw, "security_type")),
                currency=_text(raw, "currency"),
                first_trade_date=_optional_date(raw.get("first_trade_date")),
                delisting_date=_optional_date(raw.get("delisting_date")),
                provider_ids={"eodhd": _text(raw, "provider_instrument_id")},
            )
        )
    return tuple(instruments)


def _text(payload: dict[str, object], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"instrument manifest {key} must be non-empty text")
    return value.strip()


def _optional_date(value: object) -> date | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("instrument manifest dates must be ISO dates or null")
    return date.fromisoformat(value)


if __name__ == "__main__":
    raise SystemExit(main())
