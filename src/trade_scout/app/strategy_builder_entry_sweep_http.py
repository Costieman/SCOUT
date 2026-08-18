"""HTTP-query adapter for governed Strategy Builder entry-parameter sweeps."""

from __future__ import annotations

from http import HTTPStatus
from urllib.parse import parse_qs

from trade_scout.app.entry_strategy_registry import EntryFamily, available_entry_strategies
from trade_scout.app.exit_policy_lab_service import parse_multiple_grid, parse_percentage_grid
from trade_scout.app.local_console import LocalConsoleConfig
from trade_scout.app.strategy_builder_entry_sweep import (
    EntrySweepParameter,
    StrategyBuilderEntrySweepService,
    materialize_entry_sweep_values,
)
from trade_scout.app.strategy_builder_entry_sweep_surface import attach_entry_sweep_html
from trade_scout.app.strategy_builder_service import StrategyBuilderError, StrategyBuilderRequest
from trade_scout.app.strategy_builder_surface import render_strategy_builder_html
from trade_scout.patterns.consolidation_breakout import TrendFilter
from trade_scout.statistics.strategy_research import available_strategy_features

INTERACTIVE_ENTRY_SWEEP_LIMIT = 8


def is_entry_sweep_query(query: str) -> bool:
    """Return whether one Strategy Builder request explicitly asks for an entry sweep."""

    parameters = parse_qs(query, keep_blank_values=True)
    return bool(parameters.get("entry_sweep_feature"))


def build_entry_sweep_page(
    query: str,
    config: LocalConsoleConfig,
) -> tuple[HTTPStatus, str]:
    """Run one declared entry-indicator sweep and return its Strategy Builder page."""

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
                error=(
                    "Strategy Builder entry sweeps require a configured canonical research source."
                ),
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
            expression=_one(parameters, "expression"),
            rank_feature=_one(parameters, "rank_feature", default="return_20"),
            descending=_one(parameters, "rank_direction", default="desc") == "desc",
            per_session_limit=int(_one(parameters, "per_session_limit", default="500")),
            duration=int(_one(parameters, "duration", default="20")),
            max_range_pct=float(_one(parameters, "max_range_pct", default="12")) / 100.0,
            trend_filter=TrendFilter(
                _one(parameters, "trend_filter", default=TrendFilter.ABOVE_SMA_50_100_200.value)
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
        target_feature_name = _one(parameters, "entry_sweep_feature")
        sweep_parameter = EntrySweepParameter(_one(parameters, "entry_sweep_parameter"))
        values = materialize_entry_sweep_values(
            start=float(_one(parameters, "entry_sweep_from")),
            end=float(_one(parameters, "entry_sweep_to")),
            step=float(_one(parameters, "entry_sweep_step")),
            parameter=sweep_parameter,
        )
        if len(values) > INTERACTIVE_ENTRY_SWEEP_LIMIT:
            raise ValueError(
                "interactive entry sweeps are temporarily limited to "
                f"{INTERACTIVE_ENTRY_SWEEP_LIMIT} values to protect local browser responsiveness; "
                "increase Step or narrow the range"
            )
        report = StrategyBuilderEntrySweepService(source).run(
            request,
            target_feature_name=target_feature_name,
            parameter=sweep_parameter,
            values=values,
        )
        html = render_strategy_builder_html(
            universes=universes,
            entries=entries,
            features=features,
            request=request,
        )
        return HTTPStatus.OK, attach_entry_sweep_html(html, report)
    except (ValueError, StrategyBuilderError) as exc:
        html = render_strategy_builder_html(
            universes=universes,
            entries=entries,
            features=features,
            request=request,
            error=str(exc),
        )
        return HTTPStatus.BAD_REQUEST, html


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


__all__ = [
    "INTERACTIVE_ENTRY_SWEEP_LIMIT",
    "build_entry_sweep_page",
    "is_entry_sweep_query",
]
