"""Run one bounded EODHD case through the full Phase 1 canonical promotion path."""

from __future__ import annotations

import argparse
import json
import os
from datetime import UTC, date, datetime
from pathlib import Path

from trade_scout.data.canonical_storage import CanonicalDailyBarStore
from trade_scout.data.contracts import DatasetVersion
from trade_scout.data.providers.eodhd_campaign import EodhdCampaignCase, run_eodhd_canonical_case


def _date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("dates must use YYYY-MM-DD") from exc


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Fetch one explicit EODHD active/delisted security, preserve exact raw responses, "
            "materialize split-only adjustment evidence, run normalization/quality gates, and "
            "promote a bounded immutable canonical dataset for Phase 1 evaluation."
        )
    )
    parser.add_argument("--symbol", required=True, help="EODHD symbol, e.g. AAPL.US")
    parser.add_argument("--start", type=_date, required=True)
    parser.add_argument("--end", type=_date, required=True)
    parser.add_argument("--expected-state", choices=("active", "delisted"), required=True)
    parser.add_argument("--dataset-version", required=True)
    parser.add_argument(
        "--output-root",
        type=Path,
        default=Path("runtime/eodhd-canonical-campaign"),
    )
    return parser


def main() -> int:
    args = _parser().parse_args()
    token = os.environ.get("EODHD_API_KEY", "").strip()
    if not token:
        raise SystemExit("EODHD_API_KEY is not configured")

    output_root: Path = args.output_root
    dataset_version = DatasetVersion(args.dataset_version)
    case = EodhdCampaignCase(
        symbol=args.symbol,
        start=args.start,
        end=args.end,
        expected_active=args.expected_state == "active",
    )
    evidence = run_eodhd_canonical_case(
        token,
        case,
        raw_root=output_root / "raw",
        canonical_store=CanonicalDailyBarStore(output_root / "data"),
        dataset_id="eodhd-canonical-evaluation",
        dataset_version=dataset_version,
        created_at=datetime.now(UTC),
        transformation_version="provider-normalization-v1",
        adjustment_policy_version="split-only-v1",
        universe_construction_version="bounded-evaluation-scope-v1",
        quality_check_version="daily-bar-quality-v1",
    )

    report_root = output_root / "report" / str(dataset_version)
    report_root.mkdir(parents=True, exist_ok=True)
    payload = {
        "evaluation_id": "eodhd-canonical-campaign-v0.1",
        "provider_id": "eodhd",
        "symbol": evidence.symbol,
        "provider_instrument_id": evidence.provider_instrument_id,
        "expected_state": args.expected_state,
        "requested_start": args.start.isoformat(),
        "requested_end": args.end.isoformat(),
        "bar_count": evidence.bar_count,
        "action_count": evidence.action_count,
        "split_count": evidence.split_count,
        "dividend_count": evidence.dividend_count,
        "raw_batch_ids": list(evidence.raw_batch_ids),
        "dataset_version": str(evidence.manifest.dataset_version),
        "canonical_record_count": evidence.manifest.record_count,
        "canonical_first_trade_date": evidence.manifest.first_trade_date.isoformat(),
        "canonical_last_trade_date": evidence.manifest.last_trade_date.isoformat(),
        "canonical_content_checksum_sha256": evidence.manifest.content_checksum_sha256,
        "canonical_parquet_checksum_sha256": evidence.manifest.parquet_checksum_sha256,
        "provider_accepted": False,
        "representative_sample_accepted": False,
        "acceptance_note": (
            "A successful bounded case proves this exact identity/date scope can traverse the raw, "
            "corporate-action, normalization, quality, provenance, and canonical-storage path. "
            "It does not establish representative multi-year coverage or primary-provider acceptance."
        ),
    }
    json_path = report_root / "eodhd-canonical-campaign.json"
    json_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    markdown_path = report_root / "eodhd-canonical-campaign.md"
    markdown_path.write_text(_markdown(payload), encoding="utf-8")
    print(markdown_path.read_text(encoding="utf-8"))
    return 0


def _markdown(payload: dict[str, object]) -> str:
    return "\n".join(
        [
            "# EODHD canonical Phase 1 evaluation case",
            "",
            f"Symbol: `{payload['symbol']}`",
            f"Provider identity: `{payload['provider_instrument_id']}`",
            f"Requested state: `{payload['expected_state']}`",
            f"Requested range: {payload['requested_start']} to {payload['requested_end']}",
            f"Canonical range: {payload['canonical_first_trade_date']} to "
            f"{payload['canonical_last_trade_date']}",
            f"Canonical records: {payload['canonical_record_count']}",
            f"Corporate actions: {payload['action_count']} "
            f"(splits={payload['split_count']}, dividends={payload['dividend_count']})",
            f"Raw batches preserved: {len(payload['raw_batch_ids']) if isinstance(payload['raw_batch_ids'], list) else 0}",
            "",
            "**Provider accepted: false. Representative sample accepted: false.**",
            "",
            str(payload["acceptance_note"]),
            "",
        ]
    )


if __name__ == "__main__":
    raise SystemExit(main())
