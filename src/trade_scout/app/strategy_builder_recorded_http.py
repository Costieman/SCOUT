"""Recorded HTTP adapter for normal Strategy Builder research requests.

The legacy local-console route remains usable without an experiment recorder. The research workbench
uses this adapter when durable experiment capture is configured so the same validated request model
and analytical service execute inside the existing ExperimentRunner.
"""

from __future__ import annotations

from http import HTTPStatus
from urllib.parse import parse_qs

from trade_scout.app.entry_strategy_registry import EntryFamily, available_entry_strategies
from trade_scout.app.exit_policy_lab_service import parse_multiple_grid, parse_percentage_grid
from trade_scout.app.local_console import LocalConsoleConfig
from trade_scout.app.strategy_builder_experiments import (
    StrategyBuilderExperimentRecorder,
    attach_experiment_record_html,
)
from trade_scout.app.strategy_builder_service import StrategyBuilderError, StrategyBuilderRequest
from trade_scout.app.strategy_builder_surface import render_strategy_builder_html
from trade_scout.patterns.consolidation_breakout import TrendFilter
from trade_scout.statistics.strategy_research import available_strategy_features


def build_recorded_strategy_page(
    query: str,
    config: LocalConsoleConfig,
    recorder: StrategyBuilderExperimentRecorder,
) -> tuple[HTTPStatus, str]:
    """Run one normal Strategy Builder request as a durable governed experiment."""

    source = config.strategy_builder_source
    entries = available_entry_strategies()
    features = available_strategy_features()
    if source is None:
        return (
            HTTPStatus.SERVICE_UNAVAILABLE,
            render_strategy_builder_html(
                universes=(),
                entries=entries,
                features=features,
                error="Strategy Builder experiment capture requires a configured canonical source.",
            ),
        )
    try:
        universes = source.available_universes()
    except Exception as exc:
        return (
            HTTPStatus.SERVICE_UNAVAILABLE,
            render_strategy_builder_html(
                universes=(),
                entries=entries,
                features=features,
                error=f"Cannot load research-universe scope: {type(exc).__name__}: {exc}",
            ),
        )

    parameters = parse_qs(query, keep_blank_values=True)
    request: StrategyBuilderRequest | None = None
    try:
        request = StrategyBuilderRequest(
            universe_id=_one(parameters, "universe", default="reviewed_canonical"),
            entry_family=EntryFamily(
                _one(parameters, "entry_family", default=EntryFamily.FEATURE_EXPRESSION.value)
            ),
            lookback_years=int(_one(parameters, "lookback_years", default="2")),
            horizon=int(_one(parameters, "horizon", default="20")),
            expression=_one(
                parameters,
                "expression",
                default=(
                    "return_20 >= 0.05 and relative_volume_20 >= 1.5 and distance_sma_200_pct > 0"
                ),
            ),
            rank_feature=_one(parameters, "rank_feature", default="return_20"),
            descending=_one(parameters, "rank_direction", default="desc") == "desc",
            per_session_limit=int(_one(parameters, "per_session_limit", default="500")),
            duration=int(_one(parameters, "duration", default="20")),
            max_range_pct=float(_one(parameters, "max_range_pct", default="12")) / 100.0,
            trend_filter=TrendFilter(
                _one(parameters, "trend_filter", default=TrendFilter.ABOVE_SMA_50_100_200.value)
            ),
            min_breakout_volume_ratio=_optional_volume_ratio(
                _one(parameters, "volume_ratio", default="none")
            ),
            fixed_percentages=parse_percentage_grid(_one(parameters, "fixed_stops", default="")),
            trailing_percentages=parse_percentage_grid(
                _one(parameters, "trailing_stops", default="")
            ),
            atr_multiples=parse_multiple_grid(_one(parameters, "atr_stops", default="")),
            trailing_atr_multiples=parse_multiple_grid(
                _one(parameters, "trailing_atr", default="")
            ),
            entry_slippage_bps=float(_one(parameters, "entry_slip", default="0")),
            exit_slippage_bps=float(_one(parameters, "exit_slip", default="0")),
            stop_slippage_bps=float(_one(parameters, "stop_slip", default="0")),
            commission_bps_per_side=float(_one(parameters, "commission", default="0")),
        )
        recorded = recorder.run_strategy(source, request)
        html = render_strategy_builder_html(
            universes=universes,
            entries=entries,
            features=features,
            request=request,
            report=recorded.report,
        )
        return HTTPStatus.OK, attach_experiment_record_html(html, recorded.manifest)
    except (ValueError, StrategyBuilderError) as exc:
        html = render_strategy_builder_html(
            universes=universes,
            entries=entries,
            features=features,
            request=request,
            error=str(exc),
        )
        return HTTPStatus.BAD_REQUEST, html


def _optional_volume_ratio(value: str) -> float | None:
    if value.strip().lower() == "none":
        return None
    result = float(value)
    if result <= 0:
        raise ValueError("volume_ratio must be positive or 'none'")
    return result


def _one(
    parameters: dict[str, list[str]],
    name: str,
    *,
    default: str | None = None,
) -> str:
    values = parameters.get(name)
    if not values:
        if default is None:
            raise ValueError(f"missing query parameter {name}")
        return default
    if len(values) != 1:
        raise ValueError(f"query parameter {name} must appear once")
    return values[0]


__all__ = ["build_recorded_strategy_page"]
