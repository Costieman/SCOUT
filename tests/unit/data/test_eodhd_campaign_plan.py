from __future__ import annotations

import json
from pathlib import Path

import pytest

from trade_scout.data.providers.eodhd_campaign_plan import (
    EodhdCampaignPlanError,
    load_eodhd_campaign_plan,
)


def _write(path: Path, payload: object) -> Path:
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _payload() -> dict[str, object]:
    return {
        "schema_version": "eodhd-campaign-plan-v0.1",
        "plan_version": "phase1-eodhd-v1",
        "cases": [
            {
                "case_id": "active",
                "symbol": "AAA.US",
                "start": "2020-01-01",
                "end": "2020-12-31",
                "expected_state": "active",
                "dataset_version": "active-v1",
            },
            {
                "case_id": "delisted",
                "symbol": "OLD.US",
                "start": "2018-01-01",
                "end": "2020-12-31",
                "expected_state": "delisted",
                "dataset_version": "delisted-v1",
            },
        ],
    }


def test_plan_requires_explicit_active_and_delisted_cases(tmp_path: Path) -> None:
    plan = load_eodhd_campaign_plan(_write(tmp_path / "plan.json", _payload()))

    assert plan.plan_version == "phase1-eodhd-v1"
    assert tuple(case.case_id for case in plan.cases) == ("active", "delisted")
    assert plan.cases[0].expected_active is True
    assert plan.cases[1].expected_active is False


def test_unknown_fields_fail_closed(tmp_path: Path) -> None:
    payload = _payload()
    payload["optimistic_acceptance"] = True

    with pytest.raises(EodhdCampaignPlanError, match="top-level"):
        load_eodhd_campaign_plan(_write(tmp_path / "plan.json", payload))


def test_delisted_case_is_required(tmp_path: Path) -> None:
    payload = _payload()
    payload["cases"] = [payload["cases"][0]]  # type: ignore[index]

    with pytest.raises(EodhdCampaignPlanError, match="delisted-security"):
        load_eodhd_campaign_plan(_write(tmp_path / "plan.json", payload))


def test_invalid_state_or_date_is_rejected(tmp_path: Path) -> None:
    payload = _payload()
    cases = payload["cases"]
    assert isinstance(cases, list)
    first = cases[0]
    assert isinstance(first, dict)
    first["expected_state"] = "unknown"

    with pytest.raises(EodhdCampaignPlanError, match="expected_state"):
        load_eodhd_campaign_plan(_write(tmp_path / "state.json", payload))

    payload = _payload()
    cases = payload["cases"]
    assert isinstance(cases, list)
    first = cases[0]
    assert isinstance(first, dict)
    first["start"] = "not-a-date"

    with pytest.raises(EodhdCampaignPlanError, match="YYYY-MM-DD"):
        load_eodhd_campaign_plan(_write(tmp_path / "date.json", payload))
