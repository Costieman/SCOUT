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
        return {"TEST": _bars()}


def _bars() -> tuple[ResearchBar, ...]:
    rows = []
    start = date(2024, 1, 1)
    for index in range(320):
        phase = index % 40
        close = 100.0
        high = 101.0
        low = 99.0
        if phase == 20:
            close = 103.0
            high = 104.0
            low = 100.0
        elif 20 < phase < 26:
            close = 104.0 + (phase - 20) * 0.5
            high = close + 1.0
            low = close - 1.0
        rows.append(
            ResearchBar(
                instrument_id=InstrumentId("tsi_risk_surface"),
                trade_date=start + timedelta(days=index),
                open=close,
                high=high,
                low=low,
                close=close,
                volume=1_000_000.0,
                eligibility=True,
                quality_status=QualityStatus.PASS,
                dataset_version=DatasetVersion("risk-surface-v1"),
                price_representation=PriceRepresentation.SPLIT_ADJUSTED,
            )
        )
    return tuple(rows)


def _sources(tmp_path: Path) -> DataHealthSourcePaths:
    return DataHealthSourcePaths(
        tiingo_acceptance_path=tmp_path / "tiingo.json",
        free_stack_acceptance_path=tmp_path / "free.json",
    )


def test_risk_route_renders_fixed_atr_structural_policy_comparison(tmp_path: Path) -> None:
    response = build_console_response(
        "/research/risk?universe=reviewed_canonical&lookback_years=1&horizon=5&duration=10&max_range_pct=5&trend_filter=none&volume_ratio=none&cost_bps=0",
        LocalConsoleConfig(
            sources=_sources(tmp_path),
            universe_research_source=_FakeUniverseSource(),
        ),
    )
    text = response.body.decode("utf-8")

    assert response.status_code == 200
    assert "Risk &amp; Stop Research" in text or "Risk & Stop Research" in text
    assert "Path first, stop second" in text
    assert "Fixed 2%" in text
    assert "ATR 1x" in text
    assert "Structural — consolidation low" in text
    assert "Premature stop" in text
    assert "Gap through" in text


def test_unconfigured_risk_route_is_visible_but_blocked(tmp_path: Path) -> None:
    response = build_console_response(
        "/research/risk",
        LocalConsoleConfig(sources=_sources(tmp_path)),
    )

    assert response.status_code == 503
    assert "not configured" in response.body.decode("utf-8")
