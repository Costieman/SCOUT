"""Unit coverage for evidence, multiplicity, and complete parameter-surface contracts."""

import pytest

from trade_scout.validation import (
    ComparatorDefinition,
    ComparatorKind,
    ConfidenceInterval,
    EffectEstimate,
    EvidenceRole,
    EvidenceSnapshot,
    HypothesisFamily,
    MetricEstimate,
    MultiplicityMethod,
    ParameterAxis,
    ParameterCell,
    ParameterSurface,
    SampleAccounting,
    ValidationEvidenceReport,
    adjust_p_values,
)


def _sample(count: int = 100) -> SampleAccounting:
    return SampleAccounting(
        raw_event_count=count,
        unique_instrument_count=max(1, count // 2),
        effective_sample_size=count * 0.7,
    )


def _comparator() -> ComparatorDefinition:
    return ComparatorDefinition(
        comparator_id="trend-matched-v1",
        kind=ComparatorKind.TREND_MATCHED,
        description="Same trend context without the registered breakout event.",
        matching_fields=("trend_context", "as_of_date"),
    )


def test_randomized_comparator_requires_recorded_seed() -> None:
    with pytest.raises(ValueError, match="require a recorded seed"):
        ComparatorDefinition(
            comparator_id="pseudo-events",
            kind=ComparatorKind.RANDOMIZED_PSEUDO_EVENT,
            description="Point-in-time pseudo-event dates.",
        )


def test_effect_estimate_preserves_uncertainty_and_comparator() -> None:
    interval = ConfidenceInterval(
        lower=0.002,
        upper=0.018,
        confidence_level=0.95,
        method="date-sector block bootstrap",
    )
    effect = EffectEstimate(
        effect_id="return-60-vs-trend",
        metric="forward_return_60_difference",
        estimate=0.01,
        units="fraction",
        comparator=_comparator(),
        sample=_sample(),
        interval=interval,
        p_value=0.03,
        adjusted_p_value=0.06,
    )

    assert effect.interval == interval
    assert effect.comparator.kind is ComparatorKind.TREND_MATCHED
    assert effect.adjusted_p_value == pytest.approx(0.06)


def test_evidence_snapshot_enforces_role_specific_identity() -> None:
    metric = MetricEstimate("median_forward_return_60", 0.04, "fraction")

    with pytest.raises(ValueError, match="requires fold_id"):
        EvidenceSnapshot(
            evidence_id="fold-evidence",
            role=EvidenceRole.WALK_FORWARD,
            sample=_sample(),
            metrics=(metric,),
        )

    robustness = EvidenceSnapshot(
        evidence_id="cost-stress",
        role=EvidenceRole.ROBUSTNESS,
        sample=_sample(),
        metrics=(metric,),
        challenge_id="higher-cost-stress",
    )
    assert robustness.challenge_id == "higher-cost-stress"


def test_validation_report_does_not_collapse_validation_roles() -> None:
    metric = MetricEstimate("win_probability_60", 0.58, "probability")
    validation = EvidenceSnapshot(
        evidence_id="validation",
        role=EvidenceRole.VALIDATION,
        sample=_sample(),
        metrics=(metric,),
    )
    holdout = EvidenceSnapshot(
        evidence_id="holdout",
        role=EvidenceRole.FINAL_HOLDOUT,
        sample=_sample(80),
        metrics=(metric,),
    )
    report = ValidationEvidenceReport(
        report_id="report-v1",
        experiment_id="exp-123",
        validation_plan_id="plan-v1",
        primary_outcome="forward_return_60",
        snapshots=(validation, holdout),
    )

    assert report.snapshots_for(EvidenceRole.VALIDATION) == (validation,)
    assert report.snapshots_for(EvidenceRole.FINAL_HOLDOUT) == (holdout,)


def test_bonferroni_requires_complete_registered_family() -> None:
    family = HypothesisFamily(
        family_id="duration-family",
        hypothesis_ids=("h10", "h20", "h30"),
        method=MultiplicityMethod.BONFERRONI,
    )

    with pytest.raises(ValueError, match="exactly match"):
        adjust_p_values(family, {"h10": 0.01, "h20": 0.02})

    adjusted = adjust_p_values(
        family,
        {"h10": 0.01, "h20": 0.02, "h30": 0.5},
    )
    assert [item.adjusted_p_value for item in adjusted] == pytest.approx([0.03, 0.06, 1.0])


def test_benjamini_hochberg_is_monotone_in_sorted_p_values() -> None:
    family = HypothesisFamily(
        family_id="tightness-family",
        hypothesis_ids=("a", "b", "c", "d"),
        method=MultiplicityMethod.BENJAMINI_HOCHBERG,
    )
    adjusted = adjust_p_values(
        family,
        {"a": 0.01, "b": 0.04, "c": 0.03, "d": 0.2},
    )
    by_raw = sorted(adjusted, key=lambda item: item.raw_p_value)

    assert [item.adjusted_p_value for item in by_raw] == pytest.approx(
        [0.04, 0.05333333333333334, 0.05333333333333334, 0.2]
    )


def _cell(duration: int, width: float, estimate: float) -> ParameterCell:
    return ParameterCell(
        coordinates=(("duration", duration), ("max_range", width)),
        metric="median_forward_return_60",
        estimate=estimate,
        units="fraction",
        sample=_sample(),
    )


def test_parameter_surface_requires_every_predeclared_cell() -> None:
    axes = (
        ParameterAxis("duration", (20, 30)),
        ParameterAxis("max_range", (0.06, 0.08)),
    )
    incomplete = (
        _cell(20, 0.06, 0.01),
        _cell(20, 0.08, 0.02),
        _cell(30, 0.06, 0.03),
    )

    with pytest.raises(ValueError, match="complete declared search space"):
        ParameterSurface(
            surface_id="duration-tightness",
            axes=axes,
            metric="median_forward_return_60",
            units="fraction",
            cells=incomplete,
        )


def test_parameter_surface_preserves_neighbors_without_ranking_them() -> None:
    axes = (
        ParameterAxis("duration", (20, 30)),
        ParameterAxis("max_range", (0.06, 0.08)),
    )
    surface = ParameterSurface(
        surface_id="duration-tightness",
        axes=axes,
        metric="median_forward_return_60",
        units="fraction",
        cells=(
            _cell(20, 0.06, 0.01),
            _cell(20, 0.08, 0.02),
            _cell(30, 0.06, 0.03),
            _cell(30, 0.08, 0.025),
        ),
    )

    assert len(surface.declared_coordinates()) == 4
    assert surface.cell_at(duration=30, max_range=0.08).estimate == pytest.approx(0.025)
