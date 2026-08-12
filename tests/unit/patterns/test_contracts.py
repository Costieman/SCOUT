from __future__ import annotations

from datetime import date

import pytest

from trade_scout.data.contracts import InstrumentId, QualityStatus
from trade_scout.patterns import PatternLifecycleState, PatternState


def _state(**overrides: object) -> PatternState:
    values: dict[str, object] = {
        "pattern_instance_id": "tsi_test:consolidation-v1:2024-01-01:2024-01-20",
        "instrument_id": InstrumentId("tsi_test"),
        "pattern_family": "consolidation",
        "pattern_version": "1.0.0",
        "as_of_date": date(2024, 1, 20),
        "state": PatternLifecycleState.QUALIFIED,
        "formation_start": date(2024, 1, 1),
        "formation_end": date(2024, 1, 19),
        "resolved_parameters": {"duration": 20, "max_range_pct": 0.1},
        "structural_boundaries": {"resistance": 105.0, "support": 95.0},
        "feature_set_version": "features-v1",
        "dataset_version": "dataset-v1",
        "quality_status": QualityStatus.PASS,
    }
    values.update(overrides)
    return PatternState(**values)  # type: ignore[arg-type]


def test_pattern_state_preserves_registered_identity_and_lifecycle() -> None:
    state = _state()

    assert state.state is PatternLifecycleState.QUALIFIED
    assert state.pattern_family == "consolidation"
    assert state.structural_boundaries["resistance"] == 105.0
    assert state.quality_status is QualityStatus.PASS


def test_pattern_state_rejects_future_formation_interval() -> None:
    with pytest.raises(ValueError, match="cannot extend beyond as_of_date"):
        _state(formation_end=date(2024, 1, 21))


def test_pattern_state_rejects_reversed_formation_interval() -> None:
    with pytest.raises(ValueError, match="formation_start"):
        _state(formation_start=date(2024, 1, 22), formation_end=date(2024, 1, 21), as_of_date=date(2024, 1, 23))
