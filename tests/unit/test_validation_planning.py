"""Unit tests for time-ordered validation and robustness planning."""

from datetime import date

import pytest

from trade_scout.validation import (
    DateInterval,
    SampleAccounting,
    ValidationPlan,
    ValidationRole,
    ValidationSegment,
    build_fixed_holdout_plan,
    build_walk_forward_plan,
    consolidation_breakout_robustness_plan,
)


def test_fixed_holdout_plan_preserves_chronological_roles() -> None:
    plan = build_fixed_holdout_plan(
        plan_id="candidate-v1",
        development=DateInterval(date(2000, 1, 1), date(2015, 12, 31)),
        validation=DateInterval(date(2016, 1, 1), date(2020, 12, 31)),
        holdout=DateInterval(date(2021, 1, 1), date(2025, 12, 31)),
        primary_outcome="forward_return_60",
        comparator_id="trend-matched",
    )

    assert [segment.role for segment in plan.segments] == [
        ValidationRole.DEVELOPMENT,
        ValidationRole.VALIDATION,
        ValidationRole.HOLDOUT,
    ]
    assert plan.primary_outcome == "forward_return_60"
    assert plan.comparator_id == "trend-matched"


def test_validation_plan_rejects_overlapping_segments() -> None:
    with pytest.raises(ValueError, match="must not overlap"):
        ValidationPlan(
            plan_id="overlap",
            segments=(
                ValidationSegment(
                    "development",
                    ValidationRole.DEVELOPMENT,
                    DateInterval(date(2020, 1, 1), date(2021, 1, 1)),
                ),
                ValidationSegment(
                    "validation",
                    ValidationRole.VALIDATION,
                    DateInterval(date(2021, 1, 1), date(2022, 1, 1)),
                ),
            ),
        )


def test_holdout_must_be_last_segment() -> None:
    with pytest.raises(ValueError, match="chronologically last"):
        ValidationPlan(
            plan_id="bad-holdout",
            segments=(
                ValidationSegment(
                    "holdout",
                    ValidationRole.HOLDOUT,
                    DateInterval(date(2020, 1, 1), date(2020, 12, 31)),
                ),
                ValidationSegment(
                    "validation",
                    ValidationRole.VALIDATION,
                    DateInterval(date(2021, 1, 1), date(2021, 12, 31)),
                ),
            ),
        )


def test_walk_forward_plan_uses_only_prior_dates_for_each_fold() -> None:
    plan = build_walk_forward_plan(
        plan_id="wf-v1",
        boundaries=(
            date(2000, 1, 1),
            date(2005, 1, 1),
            date(2010, 1, 1),
            date(2015, 1, 1),
        ),
    )

    assert len(plan.walk_forward_folds) == 2
    assert plan.walk_forward_folds[0].development.end == date(2004, 12, 31)
    assert plan.walk_forward_folds[0].validation.start == date(2005, 1, 1)
    assert plan.walk_forward_folds[1].development.end == date(2009, 12, 31)
    assert plan.walk_forward_folds[1].validation.start == date(2010, 1, 1)
    assert all(
        fold.development.end < fold.validation.start for fold in plan.walk_forward_folds
    )


def test_sample_accounting_rejects_impossible_effective_sample_size() -> None:
    with pytest.raises(ValueError, match="cannot exceed raw event count"):
        SampleAccounting(
            raw_event_count=10,
            unique_instrument_count=8,
            effective_sample_size=11.0,
        )


def test_first_program_robustness_plan_declares_required_challenge_families() -> None:
    plan = consolidation_breakout_robustness_plan()

    assert len(plan.challenges) == 10
    challenge_ids = {challenge.challenge_id for challenge in plan.challenges}
    assert "entry-plus-one-session" in challenge_ids
    assert "nearby-duration" in challenge_ids
    assert "higher-cost-stress" in challenge_ids
    assert "corrected-dataset-rerun" in challenge_ids
