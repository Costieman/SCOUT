from datetime import date

from trade_scout.app.cached_windowed_canonical_source import (
    CachedWindowedCanonicalUniverseResearchSource,
)
from trade_scout.app.windowed_canonical_source import WindowedCanonicalUniverseResearchSource


def _source(tmp_path):
    return CachedWindowedCanonicalUniverseResearchSource(
        canonical_root=tmp_path,
        dataset_version="test-dataset",
        identity_candidate_path=tmp_path / "identity.json",
        strategy_window_cache_limit=2,
    )


def test_research_series_is_loaded_once_and_returned_as_a_copy(tmp_path, monkeypatch) -> None:
    calls = 0
    payload = {"instrument": ()}

    def fake_research_series(self, universe_id):
        nonlocal calls
        calls += 1
        return payload

    monkeypatch.setattr(
        WindowedCanonicalUniverseResearchSource,
        "research_series",
        fake_research_series,
    )
    source = _source(tmp_path)

    first = source.research_series("reviewed_canonical")
    second = source.research_series("reviewed_canonical")

    assert calls == 1
    assert first == payload
    assert second == payload
    assert first is not second


def test_strategy_window_cache_reuses_identical_window_and_is_bounded(tmp_path, monkeypatch) -> None:
    calls: list[tuple[date, date, int]] = []

    def fake_window(self, universe_id, *, signal_start, signal_end, warmup_observations):
        calls.append((signal_start, signal_end, warmup_observations))
        return ()

    monkeypatch.setattr(
        WindowedCanonicalUniverseResearchSource,
        "strategy_builder_daily_bars",
        fake_window,
    )
    source = _source(tmp_path)
    end = date(2026, 8, 19)
    starts = [date(2024, 8, 19), date(2023, 8, 19), date(2022, 8, 19)]

    source.strategy_builder_daily_bars(
        "reviewed_canonical", signal_start=starts[0], signal_end=end, warmup_observations=220
    )
    source.strategy_builder_daily_bars(
        "reviewed_canonical", signal_start=starts[0], signal_end=end, warmup_observations=220
    )
    assert len(calls) == 1

    for start in starts[1:]:
        source.strategy_builder_daily_bars(
            "reviewed_canonical", signal_start=start, signal_end=end, warmup_observations=220
        )
    assert len(source._strategy_window_cache) == 2

    source.strategy_builder_daily_bars(
        "reviewed_canonical", signal_start=starts[0], signal_end=end, warmup_observations=220
    )
    assert len(calls) == 4


def test_clear_research_cache_forces_fresh_read(tmp_path, monkeypatch) -> None:
    calls = 0

    def fake_research_series(self, universe_id):
        nonlocal calls
        calls += 1
        return {}

    monkeypatch.setattr(
        WindowedCanonicalUniverseResearchSource,
        "research_series",
        fake_research_series,
    )
    source = _source(tmp_path)
    source.research_series("reviewed_canonical")
    source.clear_research_cache()
    source.research_series("reviewed_canonical")

    assert calls == 2
