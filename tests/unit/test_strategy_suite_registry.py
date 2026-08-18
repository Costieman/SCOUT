from __future__ import annotations

from trade_scout.app.strategy_suite_registry import (
    SuiteEvidenceClass,
    SuiteImplementationKind,
    SuiteImplementationStatus,
    build_custom_suite,
    built_in_strategy_suites,
    duplicate_suite,
    edit_suite,
    strategy_suite,
)
from trade_scout.app.strategy_suite_store import StrategySuiteStore


def test_baseline_catalog_contains_exactly_twenty_unique_editable_suites() -> None:
    suites = built_in_strategy_suites()

    assert len(suites) == 20
    assert len({suite.suite_id for suite in suites}) == 20
    assert all(suite.built_in for suite in suites)
    assert all(suite.editable for suite in suites)
    assert {suite.evidence_class for suite in suites}.issubset(
        {
            SuiteEvidenceClass.ACADEMIC,
            SuiteEvidenceClass.SYSTEMATIC,
            SuiteEvidenceClass.PRACTITIONER,
            SuiteEvidenceClass.HEURISTIC,
        }
    )


def test_catalog_exposes_new_phase_three_primitives_without_overstating_structural_support() -> None:
    keltner = strategy_suite("TS-S06-KELTNER-BREAKOUT")
    nr7 = strategy_suite("TS-S19-NR7-BREAKOUT")
    vcp = strategy_suite("TS-S08-VCP")

    assert keltner.implementation_status is SuiteImplementationStatus.READY
    assert "keltner_channel" in keltner.required_capabilities
    assert nr7.implementation_status is SuiteImplementationStatus.READY
    assert "narrow_range" in nr7.required_capabilities
    assert vcp.implementation_status is SuiteImplementationStatus.REQUIRES_PATTERN
    assert vcp.implementation_kind is SuiteImplementationKind.STRUCTURAL_PATTERN


def test_duplicate_builtin_becomes_user_owned_without_mutating_source() -> None:
    source = strategy_suite("TS-S17-RSI2-MEAN-REVERSION")

    duplicate = duplicate_suite(source, suite_id="my-rsi2", name="My RSI2")

    assert source.built_in
    assert duplicate.built_in is False
    assert duplicate.evidence_class is SuiteEvidenceClass.USER_DEFINED
    assert duplicate.name == "My RSI2"
    assert duplicate.source_basis == ("derived from TS-S17-RSI2-MEAN-REVERSION",)


def test_editing_builtin_returns_user_owned_copy() -> None:
    source = strategy_suite("TS-S04-BB-SQUEEZE")

    edited = edit_suite(
        source,
        suite_id="bb-squeeze-15pct",
        name="BB Squeeze 15th Percentile",
        canonical_recipe=(
            "Bollinger 20, 2 sigma",
            "bandwidth trailing percentile <= 15",
            "close above upper band",
        ),
    )

    assert edited.built_in is False
    assert edited.evidence_class is SuiteEvidenceClass.USER_DEFINED
    assert edited.suite_id == "bb-squeeze-15pct"
    assert source.suite_id == "TS-S04-BB-SQUEEZE"


def test_build_custom_suite_and_store_round_trip(tmp_path) -> None:
    suite = build_custom_suite(
        suite_id="custom-macd-rsi",
        name="Custom MACD RSI",
        family="custom momentum",
        canonical_timeframe="daily",
        description="User-defined test combining MACD and RSI without claiming validation.",
        canonical_recipe=("MACD bullish cross", "RSI14 > 50"),
        required_capabilities=("macd", "rsi"),
        parameter_axes=("rsi_threshold",),
    )
    store = StrategySuiteStore(tmp_path / "strategy-suites")

    path = store.save(suite)
    loaded = store.load("custom-macd-rsi")

    assert path.exists()
    assert loaded == suite
    assert store.list() == (suite,)

    store.delete("custom-macd-rsi")
    assert store.list() == ()
