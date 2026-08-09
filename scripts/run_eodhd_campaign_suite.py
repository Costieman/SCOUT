"""Run a versioned, resumable EODHD Phase 1 evidence campaign."""

from __future__ import annotations

import argparse
import json
import os
from datetime import UTC, datetime
from pathlib import Path

from trade_scout.data.canonical_storage import CanonicalDailyBarStore
from trade_scout.data.providers.eodhd_campaign import EodhdCampaignCase, run_eodhd_canonical_case
from trade_scout.data.providers.eodhd_campaign_plan import load_eodhd_campaign_plan
from trade_scout.data.providers.eodhd_campaign_suite import (
    EodhdCampaignSuiteCase,
    run_eodhd_campaign_suite,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run an explicit active+delisted EODHD evidence plan through the immutable raw, "
            "corporate-action, normalization, quality, and canonical-storage path. Completed "
            "cases are checkpointed and are not repeated on resume."
        )
    )
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument(
        "--output-root",
        type=Path,
        default=Path("runtime/eodhd-campaign-suite"),
    )
    return parser


def main() -> int:
    args = _parser().parse_args()
    token = os.environ.get("EODHD_API_KEY", "").strip()
    if not token:
        raise SystemExit("EODHD_API_KEY is not configured")

    plan = load_eodhd_campaign_plan(args.plan)
    output_root: Path = args.output_root

    def run_case(case: EodhdCampaignSuiteCase) -> dict[str, object]:
        case_root = output_root / "case-runtime" / case.case_id
        evidence = run_eodhd_canonical_case(
            token,
            EodhdCampaignCase(
                symbol=case.symbol,
                start=case.start,
                end=case.end,
                expected_active=case.expected_active,
            ),
            raw_root=case_root / "raw",
            canonical_store=CanonicalDailyBarStore(case_root / "data"),
            dataset_id=f"eodhd-provider-evidence:{plan.plan_version}",
            dataset_version=case.dataset_version,
            created_at=datetime.now(UTC),
            transformation_version="provider-normalization-v1",
            adjustment_policy_version="split-only-v1",
            universe_construction_version="bounded-provider-evidence-v1",
            quality_check_version="daily-bar-quality-v1",
        )
        return {
            "case_id": case.case_id,
            "symbol": evidence.symbol,
            "provider_instrument_id": evidence.provider_instrument_id,
            "expected_state": "active" if case.expected_active else "delisted",
            "requested_start": case.start.isoformat(),
            "requested_end": case.end.isoformat(),
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
        }

    state = run_eodhd_campaign_suite(
        plan.cases,
        root=output_root / "campaign-state",
        case_runner=run_case,
    )
    summary = {
        "evaluation_id": "eodhd-provider-evidence-campaign-v0.1",
        "provider_id": "eodhd",
        "plan_version": plan.plan_version,
        "campaign_id": state.campaign_id,
        "expected_case_count": state.expected_case_count,
        "completed_case_ids": list(state.completed_case_ids),
        "complete": state.complete,
        "provider_accepted": False,
        "acceptance_note": (
            "Campaign completion is evidence input only. Provider acceptance remains controlled "
            "by the provider-specific acceptance gate and requires all criteria to be demonstrated."
        ),
    }
    report_root = output_root / "report" / state.campaign_id
    report_root.mkdir(parents=True, exist_ok=True)
    report_path = report_root / "campaign-summary.json"
    report_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(report_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
