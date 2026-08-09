"""Versioned plan loading for reproducible EODHD Phase 1 evidence campaigns."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from trade_scout.data.contracts import DatasetVersion
from trade_scout.data.providers.eodhd_campaign_suite import EodhdCampaignSuiteCase


class EodhdCampaignPlanError(ValueError):
    """Raised when a checked-in or local EODHD campaign plan is malformed."""


@dataclass(frozen=True, slots=True)
class EodhdCampaignPlan:
    """Explicit, versioned provider-evidence plan with no inferred securities or dates."""

    plan_version: str
    cases: tuple[EodhdCampaignSuiteCase, ...]


def load_eodhd_campaign_plan(path: Path) -> EodhdCampaignPlan:
    """Load a v0.1 campaign plan and fail closed on omissions or unknown structure."""

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise EodhdCampaignPlanError(f"cannot read EODHD campaign plan: {path}") from exc
    except json.JSONDecodeError as exc:
        raise EodhdCampaignPlanError("EODHD campaign plan is invalid JSON") from exc
    if not isinstance(payload, dict):
        raise EodhdCampaignPlanError("EODHD campaign plan root must be an object")
    if set(payload) != {"schema_version", "plan_version", "cases"}:
        raise EodhdCampaignPlanError(
            "EODHD campaign plan contains missing or unknown top-level fields"
        )
    if payload.get("schema_version") != "eodhd-campaign-plan-v0.1":
        raise EodhdCampaignPlanError("unsupported EODHD campaign plan schema_version")
    plan_version = payload.get("plan_version")
    raw_cases = payload.get("cases")
    if not isinstance(plan_version, str) or not plan_version.strip():
        raise EodhdCampaignPlanError("EODHD campaign plan_version must be non-empty text")
    if not isinstance(raw_cases, list) or not raw_cases:
        raise EodhdCampaignPlanError("EODHD campaign plan requires a non-empty cases array")
    cases = tuple(_case_from_payload(item) for item in raw_cases)
    _validate_campaign_coverage(cases)
    return EodhdCampaignPlan(plan_version=plan_version.strip(), cases=cases)


def _case_from_payload(payload: object) -> EodhdCampaignSuiteCase:
    if not isinstance(payload, dict):
        raise EodhdCampaignPlanError("EODHD campaign case must be an object")
    required = {
        "case_id",
        "symbol",
        "start",
        "end",
        "expected_state",
        "dataset_version",
    }
    if set(payload) != required:
        raise EodhdCampaignPlanError("EODHD campaign case contains missing or unknown fields")
    case_id = payload["case_id"]
    symbol = payload["symbol"]
    expected_state = payload["expected_state"]
    dataset_version = payload["dataset_version"]
    if not all(
        isinstance(item, str) for item in (case_id, symbol, expected_state, dataset_version)
    ):
        raise EodhdCampaignPlanError("EODHD campaign case text fields must be strings")
    if expected_state not in {"active", "delisted"}:
        raise EodhdCampaignPlanError("EODHD expected_state must be active or delisted")
    try:
        start = date.fromisoformat(str(payload["start"]))
        end = date.fromisoformat(str(payload["end"]))
    except ValueError as exc:
        raise EodhdCampaignPlanError("EODHD campaign dates must use YYYY-MM-DD") from exc
    return EodhdCampaignSuiteCase(
        case_id=case_id,
        symbol=symbol,
        start=start,
        end=end,
        expected_active=expected_state == "active",
        dataset_version=DatasetVersion(dataset_version),
    )


def _validate_campaign_coverage(cases: tuple[EodhdCampaignSuiteCase, ...]) -> None:
    """Require both active and delisted evidence before a campaign can claim provider coverage."""

    if not any(case.expected_active for case in cases):
        raise EodhdCampaignPlanError("EODHD campaign requires at least one active-security case")
    if not any(not case.expected_active for case in cases):
        raise EodhdCampaignPlanError("EODHD campaign requires at least one delisted-security case")
