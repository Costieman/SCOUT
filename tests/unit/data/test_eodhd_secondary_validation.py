from __future__ import annotations

import json
from pathlib import Path

import pytest

from trade_scout.data.providers.eodhd_secondary_validation import (
    EodhdSecondaryValidationError,
    load_eodhd_secondary_validation_plan,
)


def _write(path: Path, payload: object) -> Path:
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _payload() -> dict[str, object]:
    return {
        "version": "eodhd-tiingo-secondary-validation-v0.1",
        "cases": [
            {
                "case_id": "aapl-2020",
                "eodhd_symbol": "AAPL.US",
                "tiingo_symbol": "AAPL",
                "instrument_id": "instrument:aapl",
                "eodhd_provider_instrument_id": "eodhd:isin:US0378331005",
                "tiingo_provider_instrument_id": "tiingo:security:aapl",
                "start": "2020-01-02",
                "end": "2020-12-31",
            }
        ],
    }


def test_loads_strict_validation_plan(tmp_path: Path) -> None:
    plan = load_eodhd_secondary_validation_plan(_write(tmp_path / "plan.json", _payload()))

    assert plan.version == "eodhd-tiingo-secondary-validation-v0.1"
    assert len(plan.cases) == 1
    assert plan.cases[0].eodhd_symbol == "AAPL.US"
    assert plan.cases[0].tiingo_symbol == "AAPL"
    evidence = plan.cases[0].evidence_case()
    assert evidence.primary_provider_id == "eodhd"
    assert evidence.secondary_provider_id == "tiingo"
    assert evidence.primary_provider_instrument_id == "eodhd:isin:US0378331005"


def test_rejects_unknown_fields(tmp_path: Path) -> None:
    payload = _payload()
    payload["optimistic_acceptance"] = True

    with pytest.raises(EodhdSecondaryValidationError, match="unknown=optimistic_acceptance"):
        load_eodhd_secondary_validation_plan(_write(tmp_path / "plan.json", payload))


def test_rejects_duplicate_case_ids(tmp_path: Path) -> None:
    payload = _payload()
    cases = payload["cases"]
    assert isinstance(cases, list)
    cases.append(dict(cases[0]))

    with pytest.raises(EodhdSecondaryValidationError, match="case IDs must be unique"):
        load_eodhd_secondary_validation_plan(_write(tmp_path / "plan.json", payload))


def test_rejects_reversed_date_range(tmp_path: Path) -> None:
    payload = _payload()
    cases = payload["cases"]
    assert isinstance(cases, list)
    case = cases[0]
    assert isinstance(case, dict)
    case["start"] = "2021-01-01"
    case["end"] = "2020-01-01"

    with pytest.raises(EodhdSecondaryValidationError, match="end must be on or after start"):
        load_eodhd_secondary_validation_plan(_write(tmp_path / "plan.json", payload))
