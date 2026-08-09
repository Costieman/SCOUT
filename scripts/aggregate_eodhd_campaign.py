"""Aggregate one completed EODHD representative campaign into a benchmarkable dataset."""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

from trade_scout.data.canonical_storage import CanonicalDailyBarStore
from trade_scout.data.contracts import DatasetVersion
from trade_scout.data.providers.eodhd_campaign_aggregate import aggregate_eodhd_campaign


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Verify a completed EODHD campaign and aggregate its immutable per-case canonical "
            "datasets into one canonical dataset suitable for representative-sample assessment."
        )
    )
    parser.add_argument("--campaign-id", required=True)
    parser.add_argument(
        "--output-root",
        type=Path,
        default=Path("runtime/eodhd-campaign-suite"),
    )
    parser.add_argument(
        "--dataset-version",
        default="eodhd-phase1-representative-aggregate-v0.1",
    )
    return parser


def main() -> int:
    args = _parser().parse_args()
    output_root: Path = args.output_root
    aggregate = aggregate_eodhd_campaign(
        campaign_root=output_root / "campaign-state" / args.campaign_id,
        case_runtime_root=output_root / "case-runtime",
        target_store=CanonicalDailyBarStore(output_root / "representative-aggregate" / "data"),
        dataset_id="eodhd-phase1-representative-aggregate",
        dataset_version=DatasetVersion(args.dataset_version),
        created_at=datetime.now(UTC),
    )
    manifest = aggregate.manifest
    summary = {
        "schema_version": "eodhd-campaign-aggregate-v0.1",
        "campaign_id": aggregate.campaign_id,
        "case_count": aggregate.case_count,
        "instrument_count": len(aggregate.instruments),
        "dataset_version": str(manifest.dataset_version),
        "record_count": manifest.record_count,
        "first_trade_date": manifest.first_trade_date.isoformat(),
        "last_trade_date": manifest.last_trade_date.isoformat(),
        "source_batch_count": len(manifest.source_batch_ids),
        "content_checksum_sha256": manifest.content_checksum_sha256,
        "parquet_checksum_sha256": manifest.parquet_checksum_sha256,
        "instruments": [
            {
                "instrument_id": str(instrument.instrument_id),
                "symbol": instrument.primary_symbol,
                "name": instrument.name,
                "exchange": instrument.exchange,
                "security_type": str(instrument.security_type),
                "currency": instrument.currency,
                "first_trade_date": (
                    instrument.first_trade_date.isoformat()
                    if instrument.first_trade_date is not None
                    else None
                ),
                "delisting_date": (
                    instrument.delisting_date.isoformat()
                    if instrument.delisting_date is not None
                    else None
                ),
                "provider_instrument_id": instrument.provider_ids["eodhd"],
            }
            for instrument in aggregate.instruments
        ],
        "representative_sample_accepted": False,
        "acceptance_note": (
            "Aggregation only assembles verified campaign outputs. Representativeness remains "
            "controlled by the separate representative-sample policy and benchmark gate."
        ),
    }
    report_root = output_root / "representative-aggregate" / "report"
    report_root.mkdir(parents=True, exist_ok=True)
    report_path = report_root / f"{args.campaign_id}.json"
    report_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(report_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
