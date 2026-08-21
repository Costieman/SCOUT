from dataclasses import replace
from datetime import date

from trade_scout.app.strategy_builder_entry_population_cache import (
    FrozenEntryPopulation,
    frozen_entry_population_cache_stats,
    frozen_entry_population_fingerprint,
    get_or_compute_frozen_entry_population,
    reset_frozen_entry_population_cache,
)
from trade_scout.data.contracts import DatasetVersion, InstrumentId
from trade_scout.events.contracts import EventRecord


def _event(event_id: str = "evt-1") -> EventRecord:
    return EventRecord(
        event_id=event_id,
        instrument_id=InstrumentId("cache-test"),
        event_type="feature_expression_signal",
        signal_date=date(2026, 1, 5),
        event_date=date(2026, 1, 5),
        event_definition_version="entry-v1",
        dataset_version=DatasetVersion("daily-v1"),
        source_pattern_id=None,
        metadata={},
    )


def _fingerprint(*, period: int = 20, dataset: str = "daily-v1"):
    return frozen_entry_population_fingerprint(
        dataset_version=dataset,
        universe_id="reviewed_canonical",
        analysis_start="2025-01-01",
        analysis_end="2026-01-01",
        entry_family="feature_expression",
        entry_definition_version="entry-v1",
        canonical_scope=(("cache-test", "2024-01-01", "2026-01-01", 500),),
        entry_parameters={"expression": f"return_{period} > 0", "rank_feature": f"return_{period}"},
    )


def test_reuses_exact_frozen_population() -> None:
    reset_frozen_entry_population_cache()
    calls = 0

    def compute() -> FrozenEntryPopulation:
        nonlocal calls
        calls += 1
        event = _event()
        return FrozenEntryPopulation((("cache-test", (event,)),), 1, "entry-v1")

    first, first_hit = get_or_compute_frozen_entry_population(_fingerprint(), compute)
    second, second_hit = get_or_compute_frozen_entry_population(_fingerprint(), compute)

    assert first == second
    assert first_hit is False
    assert second_hit is True
    assert calls == 1
    assert frozen_entry_population_cache_stats().hits == 1


def test_downstream_exit_settings_are_not_part_of_entry_fingerprint() -> None:
    base = _fingerprint()
    # Stop, target, slippage and commission are intentionally not accepted by the fingerprint API.
    # Therefore changing those downstream settings cannot invalidate frozen entry membership.
    same_entry = _fingerprint()
    assert base == same_entry


def test_entry_parameter_change_invalidates_population() -> None:
    assert _fingerprint(period=20) != _fingerprint(period=50)


def test_dataset_change_invalidates_population() -> None:
    assert _fingerprint(dataset="daily-v1") != _fingerprint(dataset="daily-v2")


def test_population_rejects_inconsistent_event_count() -> None:
    reset_frozen_entry_population_cache()

    def compute() -> FrozenEntryPopulation:
        return FrozenEntryPopulation((("cache-test", (_event(),)),), 2, "entry-v1")

    try:
        get_or_compute_frozen_entry_population(_fingerprint(), compute)
    except ValueError as exc:
        assert "event_count" in str(exc)
    else:
        raise AssertionError("inconsistent frozen population must fail visibly")
