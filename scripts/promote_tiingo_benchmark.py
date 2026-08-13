"""Acquire and promote one explicitly identified Tiingo research benchmark."""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date
from pathlib import Path
from typing import Any
from urllib.parse import quote

from trade_scout.app.operator_workspace import (
    OperatorWorkspaceError,
    load_operator_workspace,
    validate_workspace_location,
    verify_operator_workspace,
)
from trade_scout.data.contracts import DatasetVersion, InstrumentId
from trade_scout.data.durable_raw_receipt import (
    create_durable_raw_receipt,
    persist_durable_raw_receipt,
)
from trade_scout.data.providers.tiingo import TiingoApiError, TiingoHttpClient
from trade_scout.data.providers.tiingo_benchmark import (
    TiingoBenchmarkDefinition,
    TiingoBenchmarkPromotionError,
    TiingoBenchmarkPromotionResult,
    promote_tiingo_benchmark_rows,
)
from trade_scout.data.providers.tiingo_receipt_capture import TiingoReceiptTrackingCapture
from trade_scout.data.raw_store import RawBatchStore


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Acquire one explicitly identified Tiingo benchmark and promote it into a standalone "
            "immutable canonical dataset."
        )
    )
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--provider-instrument-id", required=True)
    parser.add_argument("--instrument-id", required=True)
    parser.add_argument("--name", required=True)
    parser.add_argument("--exchange", required=True, choices=("XNYS", "XNAS"))
    parser.add_argument("--currency", default="USD")
    parser.add_argument("--first-trade-date", type=date.fromisoformat, required=True)
    parser.add_argument("--start-date", type=date.fromisoformat, required=True)
    parser.add_argument("--end-date", type=date.fromisoformat, required=True)
    parser.add_argument("--dataset-version", required=True)
    parser.add_argument("--dataset-id", default="research_benchmark_daily")
    args = parser.parse_args()

    repository_root = Path(__file__).resolve().parents[1]
    root = args.root.expanduser().resolve()
    try:
        validate_workspace_location(root, repository_root=repository_root)
        workspace = load_operator_workspace(root)
        verification = verify_operator_workspace(workspace)
        if not verification.is_consistent:
            raise OperatorWorkspaceError(
                "durable workspace evidence is inconsistent; benchmark acquisition is blocked"
            )
        api_token = os.environ.get("TIINGO_API_TOKEN", "").strip()
        if not api_token:
            raise OperatorWorkspaceError("TIINGO_API_TOKEN is not set")

        definition = TiingoBenchmarkDefinition(
            query_symbol=args.symbol,
            provider_instrument_id=args.provider_instrument_id,
            instrument_id=InstrumentId(args.instrument_id),
            name=args.name,
            exchange=args.exchange,
            currency=args.currency,
            first_trade_date=args.first_trade_date,
            dataset_start_date=args.start_date,
            dataset_end_date=args.end_date,
            dataset_version=DatasetVersion(args.dataset_version),
            dataset_id=args.dataset_id,
        )

        capture = TiingoReceiptTrackingCapture(RawBatchStore(workspace.tiingo_raw_root))
        client = TiingoHttpClient(api_token, raw_capture=capture)
        endpoint = f"/tiingo/daily/{quote(args.symbol.strip(), safe='')}/prices"
        response = client.get_json(
            endpoint,
            {
                "startDate": args.start_date.isoformat(),
                "endDate": args.end_date.isoformat(),
                "resampleFreq": "daily",
            },
        )
        rows = _rows(response)
        records = capture.captured_records
        if len(records) != 1:
            raise OperatorWorkspaceError(
                "benchmark acquisition expected exactly one durable Tiingo raw batch"
            )
        record = records[0]
        receipt = create_durable_raw_receipt(
            record,
            durable_root=workspace.tiingo_raw_root,
            storage_namespace=workspace.manifest.storage_namespace,
            subject_key=f"benchmark-{args.symbol.strip().upper()}",
        )
        receipt_path = (
            workspace.tiingo_root
            / "benchmark-receipts"
            / f"{args.symbol.strip().upper()}__{receipt.receipt_id}.json"
        )
        persist_durable_raw_receipt(receipt_path, receipt)

        result = promote_tiingo_benchmark_rows(
            rows,
            definition=definition,
            canonical_root=workspace.canonical_root,
            source_batch_ids=(record.manifest.batch_id,),
        )
        report_path = (
            workspace.root / "evidence" / "benchmarks" / f"{definition.dataset_version}.json"
        )
        _persist_report(report_path, definition, result, receipt.receipt_id)
    except (
        OperatorWorkspaceError,
        TiingoApiError,
        TiingoBenchmarkPromotionError,
        ValueError,
    ) as exc:
        print(f"Tiingo benchmark promotion error: {exc}", file=sys.stderr)
        return 2

    print(report_path.read_text(encoding="utf-8"), end="")
    return 0


def _rows(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        raise OperatorWorkspaceError("Tiingo benchmark response must be a JSON array")
    rows: list[dict[str, Any]] = []
    for item in value:
        if not isinstance(item, dict):
            raise OperatorWorkspaceError("Tiingo benchmark response contains a non-object row")
        rows.append(item)
    return rows


def _persist_report(
    path: Path,
    definition: TiingoBenchmarkDefinition,
    result: TiingoBenchmarkPromotionResult,
    receipt_id: str,
) -> None:
    manifest = result.manifest
    audit = result.session_audit
    payload = {
        "schema_version": "tiingo-benchmark-canonical-promotion-v0.1",
        "dataset_id": manifest.dataset_id,
        "dataset_version": str(manifest.dataset_version),
        "query_symbol": definition.query_symbol.strip().upper(),
        "provider_instrument_id": definition.provider_instrument_id,
        "instrument_id": str(definition.instrument_id),
        "benchmark_name": definition.name,
        "exchange": definition.exchange,
        "currency": definition.currency,
        "first_trade_date": definition.first_trade_date.isoformat(),
        "coverage_start_date": definition.dataset_start_date.isoformat(),
        "coverage_end_date": definition.dataset_end_date.isoformat(),
        "record_count": manifest.record_count,
        "split_event_count": result.split_event_count,
        "dividend_event_count": result.dividend_event_count,
        "session_calendar_definition_version": audit.calendar_definition_version,
        "session_completeness_passed": audit.complete,
        "source_receipt_id": receipt_id,
        "source_batch_ids": list(result.source_batch_ids),
        "content_checksum_sha256": manifest.content_checksum_sha256,
        "parquet_checksum_sha256": manifest.parquet_checksum_sha256,
        "transformation_version": manifest.transformation_version,
        "adjustment_policy_version": manifest.adjustment_policy_version,
        "quality_check_version": manifest.quality_check_version,
        "already_registered": result.already_registered,
        "provider_calls_made": True,
        "serving_selected": False,
        "historical_index_membership_claimed": False,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


if __name__ == "__main__":
    raise SystemExit(main())
