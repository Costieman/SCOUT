from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

from trade_scout.app.data_health_service import DataHealthSourcePaths
from trade_scout.app.local_console import LocalConsoleConfig, build_console_response
from trade_scout.app.universe_research_service import UniverseOption
from trade_scout.data.contracts import (
    DatasetVersion,
    InstrumentId,
    PriceRepresentation,
    QualityStatus,
    ResearchBar,
)


class _FakeUniverseSource:
    def available_universes(self) -> tuple[UniverseOption, ...]:
        return (
            UniverseOption(
                universe_id="reviewed_canonical",
                label="Synthetic reviewed universe",
                point_in_time_membership=False,
            ),
        )

    def research_series(self, universe_id: str) -> dict[str, tuple[ResearchBar, ...]]:
        if universe_id != "reviewed_canonical":
            raise ValueError("unknown universe")
        return {"AAA": _bars("AAA"), "BBB": _bars("BBB", offset=10.0)}


def _bars(symbol: str, *, offset: float = 0.0) -> tuple[ResearchBar, ...]:
    rows: list[ResearchBar] = []
    for index in range(800):
        close = 80.0 + offset + index * 0.04
        volume = 1_000_000.0
        if index in {520, 610, 700}:
            close += 3.0
            volume = 2_000_000.0
        rows.append(
            ResearchBar(
                instrument_id=InstrumentId(f"tsi_{symbol.lower()}"),
                trade_date=date(2023, 1, 1) + timedelta(days=index),
                open=close - 0.1,
                high=close + 0.3,
                low=close - 0.3,
                close=close,
                volume=volume,
                eligibility=True,
                quality_status=QualityStatus.PASS,
                dataset_version=DatasetVersion("surface-test-v1"),
                price_representation=PriceRepresentation.SPLIT_ADJUSTED,
            )
        )
    return tuple(rows)


def _sources(tmp_path: Path) -> DataHealthSourcePaths:
    return DataHealthSourcePaths(
        tiingo_acceptance_path=tmp_path / "tiingo.json",
        free_stack_acceptance_path=tmp_path / "free.json",
    )


def test_universe_research_route_is_visible_before_running(tmp_path: Path) -> None:
    response = build_console_response(
        "/research/universe",
        LocalConsoleConfig(
            sources=_sources(tmp_path),
            universe_research_source=_FakeUniverseSource(),
        ),
    )
    text = response.body.decode("utf-8")

    assert response.status_code == 200
    assert "Market-Wide Strategy Lab" in text
    assert "Full-universe mode" in text
    assert "Run across full universe" in text
    assert "Run baseline:" in text
    assert "Close above SMA 50, 100 and 200" in text
    assert "2-session bars" in text
    assert "Synthetic reviewed universe" in text


def test_universe_research_route_runs_market_wide_analysis(tmp_path: Path) -> None:
    response = build_console_response(
        "/research/universe?universe=reviewed_canonical&strategy=consolidation_breakout"
        "&lookback_years=2&horizon=5&duration=20&max_range_pct=5"
        "&trend_filter=none&volume_ratio=1.5",
        LocalConsoleConfig(
            sources=_sources(tmp_path),
            universe_research_source=_FakeUniverseSource(),
        ),
    )
    text = response.body.decode("utf-8")

    assert response.status_code == 200
    assert "Stocks scanned" in text
    assert "Historical setups" in text
    assert "Opportunity availability by month" in text
    assert "Where does the apparent edge live?" in text
    assert "surface-test-v1" in text
    assert "EXPLORATORY" in text


def test_unconfigured_universe_route_fails_closed(tmp_path: Path) -> None:
    response = build_console_response(
        "/research/universe",
        LocalConsoleConfig(sources=_sources(tmp_path)),
    )

    assert response.status_code == 503
    assert "not configured" in response.body.decode("utf-8")
