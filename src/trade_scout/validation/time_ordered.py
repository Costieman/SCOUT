"""Deterministic helpers for explicit time-ordered validation designs."""

from __future__ import annotations

from datetime import date

from trade_scout.validation.contracts import DateInterval, ValidationPlan, ValidationRole, ValidationSegment, WalkForwardFold


def build_fixed_holdout_plan(
    *,
    plan_id: str,
    development: DateInterval,
    validation: DateInterval,
    holdout: DateInterval | None = None,
    primary_outcome: str | None = None,
    comparator_id: str | None = None,
    robustness_checks: tuple[str, ...] = (),
) -> ValidationPlan:
    """Build a fixed, chronologically ordered development/validation/holdout plan."""

    segments = [
        ValidationSegment("development", ValidationRole.DEVELOPMENT, development),
        ValidationSegment("validation", ValidationRole.VALIDATION, validation),
    ]
    if holdout is not None:
        segments.append(ValidationSegment("holdout", ValidationRole.HOLDOUT, holdout))
    return ValidationPlan(
        plan_id=plan_id,
        segments=tuple(segments),
        primary_outcome=primary_outcome,
        comparator_id=comparator_id,
        robustness_checks=robustness_checks,
    )


def build_walk_forward_plan(
    *,
    plan_id: str,
    boundaries: tuple[date, ...],
    primary_outcome: str | None = None,
    comparator_id: str | None = None,
    robustness_checks: tuple[str, ...] = (),
) -> ValidationPlan:
    """Build expanding-window walk-forward folds from strictly increasing boundaries.

    Boundaries define consecutive inclusive calendar blocks. For N boundaries, N-2 folds are
    produced. Fold k develops from the first boundary through the day before boundary k+1 and
    validates from boundary k+1 through the day before boundary k+2.
    """

    if len(boundaries) < 3:
        raise ValueError("walk-forward planning requires at least three boundaries")
    if any(current >= following for current, following in zip(boundaries, boundaries[1:])):
        raise ValueError("walk-forward boundaries must be strictly increasing")

    from datetime import timedelta

    folds: list[WalkForwardFold] = []
    for index in range(len(boundaries) - 2):
        development = DateInterval(boundaries[0], boundaries[index + 1] - timedelta(days=1))
        validation = DateInterval(boundaries[index + 1], boundaries[index + 2] - timedelta(days=1))
        folds.append(WalkForwardFold(f"fold-{index + 1:02d}", development, validation))

    segments = (
        ValidationSegment(
            "walk-forward-development-envelope",
            ValidationRole.DEVELOPMENT,
            DateInterval(boundaries[0], boundaries[-2] - timedelta(days=1)),
        ),
        ValidationSegment(
            "walk-forward-final-validation",
            ValidationRole.VALIDATION,
            DateInterval(boundaries[-2], boundaries[-1] - timedelta(days=1)),
        ),
    )
    return ValidationPlan(
        plan_id=plan_id,
        segments=segments,
        walk_forward_folds=tuple(folds),
        primary_outcome=primary_outcome,
        comparator_id=comparator_id,
        robustness_checks=robustness_checks,
    )
