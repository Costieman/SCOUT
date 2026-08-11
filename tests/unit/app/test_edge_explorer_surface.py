from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

from trade_scout.app.data_health_service import DataHealthSourcePaths
from trade_scout.app.edge_explorer_service import EdgeExplorerRequest, EdgeExplorerService
from trade_scout.app.local_console import LocalConsoleConfig, build_console_response
from trade_scout.data.contracts import (
    DatasetVersion,
    InstrumentId,
    PriceRepresentation,
    QualityStatus,
    ResearchBar,
)
from trade_scout.patterns.consolidation_breakout import TrendFilter


class _FakeSource:
    def __init__(self, bars: tuple[ResearchBar, ...]) -> None:
        self._bars = bars

    def available_symbols(self) -> tuple[str, ...]:
        return ("TEST",)

    def research_bars(self, symbol: str) -> tuple[ResearchBar, ...]:
        if symbol.upper() != "TEST":
            raise ValueError("unknown symbol")
        return self._bars


def _bars() -> tuple[ResearchBar, ...]:
    rows = []
    for index in range(320):
        drift = 80 + index * 0.10
        cycle = (index % 20) * 0.03
        close = drift + cycle
        if index % 55 == 0 and index > 220:
            close += 3.0
        rows.append(
            ResearchBar(
                instrument_id=InstrumentId("tsi_test"),
                trade_date=date(2020, 1, 1) + timedelta(days=index),
                open=close - 0.15,
                high=close + 0.30,
                low=close - 0.35,
                close=close,
                volume=1_000_000.0,
                eligibility=True,
                quality_status=QualityStatus.PASS,
                dataset_version=DatasetVersion("test-edge-v1"),
                price_representation=PriceRepresentation.SPLIT_ADJUSTED,
            )
        )
    return tuple(rows)


def _sources(tmp_path: Path) -> DataHealthSourcePaths:
    return DataHealthSourcePaths(
        tiingo_acceptance_path=tmp_path / "tiingo.json",
        free_stack_acceptance_path=tmp_path / "free.json",
    )


def test_edge_service_builds_parameter_surface() -> None:
    report = EdgeExplorerService(_FakeSource(_bars())).run(
        EdgeExplorerRequest(
            symbol="TEST",
            horizon=20,
            duration=20,
            max_range_pct=0.12,
            trend_filter=TrendFilter.NONE,
        )
    )

    assert report.symbol == "TEST"
    assert len(report.parameter_surface) == 25
    assert report.dataset_version == "test-edge-v1"
    assert report.research_state == "EXPLORATORY"


def test_local_console_edge_route_renders_inputs_and_provenance(tmp_path: Path) -> None:
    config = LocalConsoleConfig(
        sources=_sources(tmp_path),
        edge_explorer_source=_FakeSource(_bars()),
    )

    response = build_console_response(
        "/research/edge?symbol=TEST&strategy=consolidation_breakout&horizon=20&duration=20&max_range_pct=12&trend_filter=none",
        config,
    )
    text = response.body.decode("utf-8")

    assert response.status_code == 200
    assert "Edge Explorer" in text
    assert "Where does the apparent edge live?" in text
    assert "Exploratory only" in text
    assert "test-edge-v1" in text
    assert "form-action 'self'" in dict(response.headers)["Content-Security-Policy"]


def test_unconfigured_edge_route_is_visible_but_blocked(tmp_path: Path) -> None:
    response = build_console_response(
        "/research/edge",
        LocalConsoleConfig(sources=_sources(tmp_path)),
    )

    assert response.status_code == 503
    assert "not configured" in response.body.decode("utf-8")
