"""Editable research-suite catalog for the SCOUT Strategy Builder.

A suite is a research starting point, not a validated or production-eligible strategy.  Built-in
suites package documented hypotheses into editable recipes over existing entry families and feature
primitives.  Structural methodologies that still require a dedicated pattern detector are exposed
honestly as partial research templates rather than being approximated silently.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import StrEnum


class SuiteEvidenceClass(StrEnum):
    """Origin of the hypothesis, not SCOUT's validation result."""

    ACADEMIC = "A"
    SYSTEMATIC = "B"
    PRACTITIONER = "C"
    HEURISTIC = "D"
    USER_DEFINED = "USER"


class SuiteImplementationKind(StrEnum):
    """How a suite resolves into the current research architecture."""

    FEATURE_EXPRESSION = "feature_expression"
    CONSOLIDATION_BREAKOUT = "consolidation_breakout"
    STRUCTURAL_PATTERN = "structural_pattern"


class SuiteImplementationStatus(StrEnum):
    """Current executable support without overstating incomplete structural logic."""

    READY = "ready"
    PARTIAL = "partial"
    REQUIRES_PATTERN = "requires_pattern"


@dataclass(frozen=True, slots=True)
class StrategySuite:
    """One editable, versioned research starting configuration."""

    suite_id: str
    name: str
    family: str
    evidence_class: SuiteEvidenceClass
    implementation_kind: SuiteImplementationKind
    implementation_status: SuiteImplementationStatus
    canonical_timeframe: str
    description: str
    canonical_recipe: tuple[str, ...]
    required_capabilities: tuple[str, ...]
    parameter_axes: tuple[str, ...]
    source_basis: tuple[str, ...]
    version: str = "0.1.0"
    built_in: bool = True
    editable: bool = True

    def __post_init__(self) -> None:
        if not self.suite_id.strip() or not self.name.strip():
            raise ValueError("strategy suite id and name must be non-empty")
        if not self.family.strip() or not self.description.strip():
            raise ValueError("strategy suite family and description must be non-empty")
        if not self.canonical_timeframe.strip() or not self.version.strip():
            raise ValueError("strategy suite timeframe and version must be non-empty")
        if not self.canonical_recipe:
            raise ValueError("strategy suite must contain a canonical recipe")
        if not self.required_capabilities:
            raise ValueError("strategy suite must declare required capabilities")


def _suite(
    number: int,
    slug: str,
    name: str,
    family: str,
    evidence: SuiteEvidenceClass,
    kind: SuiteImplementationKind,
    status: SuiteImplementationStatus,
    timeframe: str,
    description: str,
    recipe: tuple[str, ...],
    capabilities: tuple[str, ...],
    axes: tuple[str, ...],
    sources: tuple[str, ...],
) -> StrategySuite:
    return StrategySuite(
        suite_id=f"TS-S{number:02d}-{slug}",
        name=name,
        family=family,
        evidence_class=evidence,
        implementation_kind=kind,
        implementation_status=status,
        canonical_timeframe=timeframe,
        description=description,
        canonical_recipe=recipe,
        required_capabilities=capabilities,
        parameter_axes=axes,
        source_basis=sources,
    )


_BUILT_IN_SUITES = (
    _suite(
        1,
        "CONSOLIDATION-BREAKOUT",
        "Trend + Consolidation Breakout",
        "structural breakout / trend continuation",
        SuiteEvidenceClass.SYSTEMATIC,
        SuiteImplementationKind.CONSOLIDATION_BREAKOUT,
        SuiteImplementationStatus.READY,
        "daily",
        "SCOUT's primary hypothesis: a bounded base inside a positive trend breaks upward.",
        (
            "close > SMA200 and SMA200 slope > 0",
            "30-session qualified consolidation with configurable tightness",
            "close above the prior qualified resistance boundary",
        ),
        ("sma", "sma_slope", "consolidation_state", "close_breakout", "relative_volume"),
        ("base_duration", "tightness", "trend_filter", "breakout_margin", "relative_volume"),
        ("Trade Scout First Research Program: Consolidation Breakouts",),
    ),
    _suite(
        2,
        "DONCHIAN-BREAKOUT",
        "Donchian / Trading-Range Breakout",
        "price-channel breakout",
        SuiteEvidenceClass.ACADEMIC,
        SuiteImplementationKind.FEATURE_EXPRESSION,
        SuiteImplementationStatus.READY,
        "daily",
        "Tests continuation after a close exceeds the prior N-session high.",
        ("prior-high period = 20", "close > prior 20-session high"),
        ("prior_high", "prior_high_breakout"),
        ("channel_period", "trigger_type", "trend_filter", "atr_margin"),
        ("Brock, Lakonishok & LeBaron trading-range rules", "Donchian methodology"),
    ),
    _suite(
        3,
        "TURTLE-TREND",
        "Turtle-Style Trend Breakout",
        "mechanical trend following",
        SuiteEvidenceClass.SYSTEMATIC,
        SuiteImplementationKind.FEATURE_EXPRESSION,
        SuiteImplementationStatus.PARTIAL,
        "daily",
        "Separates channel-breakout entry from a stateful trend-preserving channel exit.",
        ("20-session or 55-session prior-high breakout", "evaluate shorter trailing-channel exit"),
        ("prior_high", "atr", "stateful_channel_exit"),
        ("entry_channel", "exit_channel", "atr_risk"),
        ("Turtle Trading methodology",),
    ),
    _suite(
        4,
        "BB-SQUEEZE",
        "Bollinger Squeeze Breakout",
        "volatility contraction / expansion",
        SuiteEvidenceClass.PRACTITIONER,
        SuiteImplementationKind.FEATURE_EXPRESSION,
        SuiteImplementationStatus.READY,
        "daily",
        "Tests directional expansion after unusually low Bollinger bandwidth.",
        ("Bollinger 20, 2 sigma", "bandwidth trailing percentile <= 10", "close above upper band"),
        ("bollinger_bands", "bb_bandwidth_percentile"),
        ("bb_period", "standard_deviations", "rank_period", "percentile_threshold"),
        ("Bollinger Band squeeze methodology",),
    ),
    _suite(
        5,
        "BB-TREND-PULLBACK",
        "Bollinger Trend Pullback",
        "trend continuation after mean reversion",
        SuiteEvidenceClass.HEURISTIC,
        SuiteImplementationKind.FEATURE_EXPRESSION,
        SuiteImplementationStatus.READY,
        "daily",
        "Tests recovery after a Bollinger mean/lower-band pullback inside a long-term uptrend.",
        ("close > SMA200 and SMA200 slope > 0", "Bollinger pullback", "recovery trigger"),
        ("bollinger_bands", "moving_average", "sma_slope"),
        ("bb_period", "pullback_depth", "trend_period", "recovery_trigger"),
        ("Bollinger trend/pullback practice",),
    ),
    _suite(
        6,
        "KELTNER-BREAKOUT",
        "Keltner / ATR Channel Breakout",
        "volatility-adjusted channel breakout",
        SuiteEvidenceClass.PRACTITIONER,
        SuiteImplementationKind.FEATURE_EXPRESSION,
        SuiteImplementationStatus.READY,
        "daily",
        "Tests closes outside an EMA-centered ATR envelope.",
        ("EMA20 center", "Wilder ATR20", "upper/lower channel = EMA +/- 2 ATR", "upper cross"),
        ("keltner_channel", "ema", "atr"),
        ("ema_period", "atr_period", "channel_multiplier", "trend_filter"),
        ("Keltner Channel methodology",),
    ),
    _suite(
        7,
        "BB-KC-SQUEEZE",
        "Bollinger-Keltner Squeeze",
        "relative volatility compression / expansion",
        SuiteEvidenceClass.HEURISTIC,
        SuiteImplementationKind.FEATURE_EXPRESSION,
        SuiteImplementationStatus.PARTIAL,
        "daily",
        "Tests releases from periods where Bollinger width is compressed relative to an ATR channel.",
        (
            "Bollinger 20, 2 sigma and Keltner 20, 1.5 ATR",
            "derive squeeze state from envelope relationship",
            "bullish release and directional close",
        ),
        ("bollinger_bands", "keltner_channel", "persistent_condition_state"),
        ("minimum_squeeze_age", "bb_width", "kc_multiplier", "release_trigger"),
        ("Bollinger-Keltner squeeze practitioner methodology",),
    ),
    _suite(
        8,
        "VCP",
        "Minervini Volatility Contraction Pattern",
        "sequential volatility contraction / breakout",
        SuiteEvidenceClass.PRACTITIONER,
        SuiteImplementationKind.STRUCTURAL_PATTERN,
        SuiteImplementationStatus.REQUIRES_PATTERN,
        "daily",
        "Requires objective peak-trough-recovery legs with successively smaller contractions.",
        ("positive trend template", "2-5 progressively smaller contractions", "break final pivot"),
        ("sequential_contraction_geometry", "pivot_boundary", "relative_volume"),
        ("contraction_count", "contraction_ratio", "final_width", "volume_contraction"),
        ("Mark Minervini VCP methodology",),
    ),
    _suite(
        9,
        "DARVAS-BOX",
        "Darvas Box Breakout",
        "persistent range / momentum breakout",
        SuiteEvidenceClass.PRACTITIONER,
        SuiteImplementationKind.STRUCTURAL_PATTERN,
        SuiteImplementationStatus.REQUIRES_PATTERN,
        "daily",
        "Requires confirmed upper/lower box boundaries and persistent in-box state before breakout.",
        ("positive momentum", "confirmed persistent box", "close above box top"),
        ("confirmed_pivot", "persistent_box", "box_breakout"),
        ("boundary_confirmation", "box_duration", "box_width", "breakout_margin"),
        ("Nicolas Darvas box methodology",),
    ),
    _suite(
        10,
        "WEINSTEIN-STAGE2",
        "Weinstein Stage-2 Breakout",
        "long-cycle base to advancing trend",
        SuiteEvidenceClass.PRACTITIONER,
        SuiteImplementationKind.STRUCTURAL_PATTERN,
        SuiteImplementationStatus.REQUIRES_PATTERN,
        "weekly",
        "Requires an objective Stage-1 base and transition into a rising long-term weekly trend.",
        ("Stage-1 base", "weekly close above resistance", "rising 30-week moving average"),
        ("weekly_timeframe", "stage_lifecycle", "resistance", "moving_average_slope"),
        ("stage1_duration", "ma_flatness", "breakout_margin", "relative_volume"),
        ("Stan Weinstein Stage Analysis",),
    ),
    _suite(
        11,
        "CANSLIM-TECHNICAL",
        "CAN SLIM Technical Breakout",
        "growth-leader technical breakout",
        SuiteEvidenceClass.PRACTITIONER,
        SuiteImplementationKind.CONSOLIDATION_BREAKOUT,
        SuiteImplementationStatus.PARTIAL,
        "daily",
        "Technical-only research template: leader rank plus base breakout and volume confirmation.",
        ("relative-strength percentile >= 80", "qualified base/pivot", "breakout RVOL >= 1.4"),
        ("cross_sectional_rank", "consolidation_state", "relative_volume"),
        ("rs_threshold", "base_definition", "volume_threshold", "market_context"),
        ("William O'Neil CAN SLIM technical methodology",),
    ),
    _suite(
        12,
        "52W-HIGH",
        "52-Week-High Momentum",
        "reference-point momentum",
        SuiteEvidenceClass.ACADEMIC,
        SuiteImplementationKind.FEATURE_EXPRESSION,
        SuiteImplementationStatus.READY,
        "daily",
        "Tests continuation as price approaches or exceeds its prior 252-session high.",
        ("prior-high period = 252", "rank or threshold by distance to prior high"),
        ("prior_high", "cross_sectional_rank_optional"),
        ("high_window", "proximity_threshold", "rank_threshold", "trend_filter"),
        ("George & Hwang 52-week-high momentum",),
    ),
    _suite(
        13,
        "XSEC-MOMENTUM",
        "Cross-Sectional Momentum Leaders",
        "relative momentum",
        SuiteEvidenceClass.ACADEMIC,
        SuiteImplementationKind.FEATURE_EXPRESSION,
        SuiteImplementationStatus.PARTIAL,
        "daily",
        "Ranks point-in-time eligible equities by trailing return and studies the winner cohort.",
        ("12-to-1-month trailing return", "cross-sectional top decile", "fixed holding horizon"),
        ("price_roc", "cross_sectional_rank"),
        ("formation_period", "skip_period", "rank_cutoff", "holding_horizon"),
        ("Jegadeesh & Titman momentum",),
    ),
    _suite(
        14,
        "TIME-SERIES-MOMENTUM",
        "Time-Series / Absolute Momentum",
        "absolute trend persistence",
        SuiteEvidenceClass.ACADEMIC,
        SuiteImplementationKind.FEATURE_EXPRESSION,
        SuiteImplementationStatus.READY,
        "daily",
        "Tests whether a security's own positive trailing trend persists.",
        ("trailing return > 0", "evaluate fixed-horizon or trend-failure exit"),
        ("price_roc", "moving_average", "historical_volatility"),
        ("lookback", "trend_measure", "volatility_normalization"),
        ("Moskowitz, Ooi & Pedersen time-series momentum",),
    ),
    _suite(
        15,
        "MA-CROSSOVER",
        "Moving-Average Crossover",
        "trend transition",
        SuiteEvidenceClass.ACADEMIC,
        SuiteImplementationKind.FEATURE_EXPRESSION,
        SuiteImplementationStatus.READY,
        "daily",
        "Tests forward outcomes after a configurable fast moving average crosses a slow average.",
        ("SMA50 crosses above SMA200",),
        ("moving_average", "ma_cross_up"),
        ("fast_period", "slow_period", "average_type", "trend_context"),
        ("Brock, Lakonishok & LeBaron moving-average rules",),
    ),
    _suite(
        16,
        "MACD-TREND",
        "MACD Trend Continuation",
        "momentum / trend continuation",
        SuiteEvidenceClass.PRACTITIONER,
        SuiteImplementationKind.FEATURE_EXPRESSION,
        SuiteImplementationStatus.READY,
        "daily",
        "Tests MACD momentum reacceleration while a longer-term trend remains positive.",
        ("close > SMA200", "MACD 12/26/9 bullish crossover"),
        ("macd", "moving_average"),
        ("fast_period", "slow_period", "signal_period", "trend_period"),
        ("MACD technical methodology",),
    ),
    _suite(
        17,
        "RSI2-MEAN-REVERSION",
        "RSI(2) Trend Mean Reversion",
        "short-term mean reversion in trend",
        SuiteEvidenceClass.PRACTITIONER,
        SuiteImplementationKind.FEATURE_EXPRESSION,
        SuiteImplementationStatus.READY,
        "daily",
        "Tests unusually weak short-term momentum inside an established long-term uptrend.",
        ("close > SMA200", "Wilder RSI(2) < 5"),
        ("rsi", "moving_average"),
        ("rsi_period", "oversold_threshold", "trend_period", "exit_rule"),
        ("Connors-style RSI(2) methodology",),
    ),
    _suite(
        18,
        "BB-RSI-MEAN-REVERSION",
        "Bollinger + RSI Mean Reversion",
        "volatility excursion / momentum exhaustion",
        SuiteEvidenceClass.HEURISTIC,
        SuiteImplementationKind.FEATURE_EXPRESSION,
        SuiteImplementationStatus.READY,
        "daily",
        "Tests whether a lower-band excursion plus oversold RSI improves a mean-reversion event.",
        ("Bollinger 20, 2 sigma lower band reached", "RSI14 <= 30"),
        ("bollinger_bands", "rsi"),
        ("bb_period", "standard_deviations", "rsi_period", "oversold_threshold"),
        ("Bollinger/RSI technical practice",),
    ),
    _suite(
        19,
        "NR7-BREAKOUT",
        "NR7 Narrow-Range Breakout",
        "one-bar volatility contraction / breakout",
        SuiteEvidenceClass.PRACTITIONER,
        SuiteImplementationKind.FEATURE_EXPRESSION,
        SuiteImplementationStatus.READY,
        "daily",
        "Qualifies a strict narrowest-in-N range bar for a later bullish boundary break.",
        ("current high-low range is strictly narrowest of 7 sessions", "break NR7 high"),
        ("narrow_range", "prior_high_or_setup_boundary"),
        ("nr_period", "trigger_age", "trigger_type", "trend_filter"),
        ("NR7 technical methodology",),
    ),
    _suite(
        20,
        "SHORT-TERM-REVERSAL",
        "Short-Term Cross-Sectional Reversal",
        "contrarian / mean reversion",
        SuiteEvidenceClass.ACADEMIC,
        SuiteImplementationKind.FEATURE_EXPRESSION,
        SuiteImplementationStatus.PARTIAL,
        "daily",
        "Studies the long loser leg of short-horizon cross-sectional reversal with explicit costs.",
        ("rank trailing 20-session return", "bottom decile", "observe short forward horizons"),
        ("price_roc", "cross_sectional_rank", "liquidity"),
        ("lookback", "rank_cutoff", "holding_horizon", "liquidity_filter"),
        ("Jegadeesh short-term reversal", "New York Fed short-term reversal research"),
    ),
)


def built_in_strategy_suites() -> tuple[StrategySuite, ...]:
    """Return the immutable twenty-suite research catalog."""

    return _BUILT_IN_SUITES


def strategy_suite(suite_id: str) -> StrategySuite:
    """Resolve a built-in suite by stable id."""

    normalized = suite_id.strip().upper()
    for suite in _BUILT_IN_SUITES:
        if suite.suite_id.upper() == normalized:
            return suite
    raise KeyError(f"unknown strategy suite {suite_id!r}")


def build_custom_suite(
    *,
    suite_id: str,
    name: str,
    family: str,
    canonical_timeframe: str,
    description: str,
    canonical_recipe: tuple[str, ...],
    required_capabilities: tuple[str, ...],
    parameter_axes: tuple[str, ...] = (),
    implementation_kind: SuiteImplementationKind = SuiteImplementationKind.FEATURE_EXPRESSION,
    implementation_status: SuiteImplementationStatus = SuiteImplementationStatus.READY,
) -> StrategySuite:
    """Create an editable user suite without granting it validation or production status."""

    normalized_id = suite_id.strip()
    if not normalized_id:
        raise ValueError("custom suite id must be non-empty")
    if any(item.suite_id.upper() == normalized_id.upper() for item in _BUILT_IN_SUITES):
        raise ValueError("custom suite id cannot replace a built-in suite")
    return StrategySuite(
        suite_id=normalized_id,
        name=name,
        family=family,
        evidence_class=SuiteEvidenceClass.USER_DEFINED,
        implementation_kind=implementation_kind,
        implementation_status=implementation_status,
        canonical_timeframe=canonical_timeframe,
        description=description,
        canonical_recipe=canonical_recipe,
        required_capabilities=required_capabilities,
        parameter_axes=parameter_axes,
        source_basis=("user-defined research hypothesis",),
        built_in=False,
    )


def duplicate_suite(
    source: StrategySuite,
    *,
    suite_id: str,
    name: str | None = None,
) -> StrategySuite:
    """Copy a suite into an editable user-owned research template."""

    normalized_id = suite_id.strip()
    if not normalized_id:
        raise ValueError("duplicate suite id must be non-empty")
    if any(item.suite_id.upper() == normalized_id.upper() for item in _BUILT_IN_SUITES):
        raise ValueError("duplicate suite id cannot replace a built-in suite")
    return replace(
        source,
        suite_id=normalized_id,
        name=name.strip() if name is not None else f"{source.name} copy",
        evidence_class=SuiteEvidenceClass.USER_DEFINED,
        source_basis=(f"derived from {source.suite_id}",),
        version="0.1.0",
        built_in=False,
        editable=True,
    )


def edit_suite(source: StrategySuite, **changes: object) -> StrategySuite:
    """Return a new suite value with explicit edits; built-ins are never mutated in place."""

    prohibited = {"built_in", "evidence_class"}
    if prohibited.intersection(changes):
        raise ValueError("suite ownership/evidence class cannot be edited directly")
    candidate = replace(source, **changes)
    if source.built_in:
        candidate = replace(
            candidate,
            evidence_class=SuiteEvidenceClass.USER_DEFINED,
            source_basis=(f"derived from {source.suite_id}",),
            built_in=False,
        )
    return candidate


if len(_BUILT_IN_SUITES) != 20:
    raise RuntimeError("the baseline strategy-suite catalog must contain exactly twenty suites")
if len({suite.suite_id for suite in _BUILT_IN_SUITES}) != len(_BUILT_IN_SUITES):
    raise RuntimeError("built-in strategy-suite ids must be unique")


__all__ = [
    "StrategySuite",
    "SuiteEvidenceClass",
    "SuiteImplementationKind",
    "SuiteImplementationStatus",
    "build_custom_suite",
    "built_in_strategy_suites",
    "duplicate_suite",
    "edit_suite",
    "strategy_suite",
]
