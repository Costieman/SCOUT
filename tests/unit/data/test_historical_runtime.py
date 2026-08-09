from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from trade_scout.data.historical_evidence import (
    HistoricalEvidenceCase,
    HistoricalEvidenceCaseResult,
    HistoricalEvidenceCheck,
    HistoricalEvidenceState,
)
from trade_scout.data.historical_runtime import (
    case_configuration_id,
    load_checkpoint,
    new_checkpoint,
    record_completed_case,
    record_failure,
    write_checkpoint,
)


def _case(symbol: str = "ABC") -> HistoricalEvidenceCase:
    return HistoricalEvidenceCase(
        case_id=f"{symbol}-2020",
        provider_symbol=symbol,
        start=date(2020, 1, 1),
        end=date(2020, 12, 31),
        minimum_observations=200,
    )


def _result(case: HistoricalEvidenceCase) -> HistoricalEvidenceCaseResult:
    return HistoricalEvidenceCaseResult(
        case_id=case.case_id,
        provider_symbol=case.provider_symbol,
        observation_count=252,
        first_trade_date=date(2020, 1, 2),
        last_trade_date=date(2020, 12, 31),
        checks=(
            HistoricalEvidenceCheck(
                check_id="repeatability",
                state=HistoricalEvidenceState.PASS,
                detail="fixture",
            ),
        ),
    )


def test_configuration_id_is_stable_and_order_sensitive() -> None:
    first = _case("ABC")
    second = _case("XYZ")

    assert case_configuration_id((first, second)) == case_configuration_id((first, second))
    assert case_configuration_id((first, second)) != case_configuration_id((second, first))


def test_checkpoint_round_trip_preserves_completed_case_and_failure(tmp_path: Path) -> None:
    case = _case()
    checkpoint = new_checkpoint((case,))
    record_completed_case(checkpoint, _result(case))
    record_failure(checkpoint, case_id="next-case", error=RuntimeError("provider unavailable"))
    path = tmp_path / "checkpoint.json"

    write_checkpoint(path, checkpoint)
    loaded = load_checkpoint(path, (case,))

    assert case.case_id in loaded["completed_cases"]
    assert loaded["last_failure"]["case_id"] == "next-case"


def test_completed_case_clears_prior_failure() -> None:
    case = _case()
    checkpoint = new_checkpoint((case,))
    record_failure(checkpoint, case_id=case.case_id, error=RuntimeError("temporary"))

    record_completed_case(checkpoint, _result(case))

    assert checkpoint["last_failure"] is None


def test_changed_case_configuration_refuses_existing_checkpoint(tmp_path: Path) -> None:
    original = (_case("ABC"),)
    path = tmp_path / "checkpoint.json"
    write_checkpoint(path, new_checkpoint(original))

    with pytest.raises(ValueError, match="configuration does not match"):
        load_checkpoint(path, (_case("XYZ"),))
