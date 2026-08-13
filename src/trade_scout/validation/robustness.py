"""Explicit robustness-test planning for frozen research definitions."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class RobustnessKind(StrEnum):
    """Supported families of specification-level robustness challenges."""

    ENTRY_SHIFT = "ENTRY_SHIFT"
    PARAMETER_NEIGHBORHOOD = "PARAMETER_NEIGHBORHOOD"
    LIQUIDITY_THRESHOLD = "LIQUIDITY_THRESHOLD"
    ALTERNATE_BOUNDARY = "ALTERNATE_BOUNDARY"
    EXCLUDE_TIME_PERIOD = "EXCLUDE_TIME_PERIOD"
    EXCLUDE_EXTREME_WINNERS = "EXCLUDE_EXTREME_WINNERS"
    EXCLUDE_SECTOR = "EXCLUDE_SECTOR"
    COST_STRESS = "COST_STRESS"
    DATASET_REVISION = "DATASET_REVISION"


@dataclass(frozen=True, slots=True)
class RobustnessChallenge:
    """One predeclared perturbation that may challenge, but never rewrite, a fixed rule."""

    challenge_id: str
    kind: RobustnessKind
    description: str
    changed_fields: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.challenge_id.strip():
            raise ValueError("challenge_id must be non-empty")
        if not self.description.strip():
            raise ValueError("robustness challenge description must be non-empty")
        if not self.changed_fields:
            raise ValueError("robustness challenge must declare changed fields")
        if any(not field.strip() for field in self.changed_fields):
            raise ValueError("robustness changed-field names must be non-empty")


@dataclass(frozen=True, slots=True)
class RobustnessPlan:
    """Immutable set of predeclared robustness challenges."""

    plan_id: str
    challenges: tuple[RobustnessChallenge, ...]

    def __post_init__(self) -> None:
        if not self.plan_id.strip():
            raise ValueError("robustness plan_id must be non-empty")
        if not self.challenges:
            raise ValueError("robustness plan must contain at least one challenge")
        identities = [challenge.challenge_id for challenge in self.challenges]
        if len(identities) != len(set(identities)):
            raise ValueError("robustness challenge IDs must be unique")


def consolidation_breakout_robustness_plan() -> RobustnessPlan:
    """Return the Version 0.1 robustness families required by the first research program."""

    return RobustnessPlan(
        plan_id="consolidation-breakout-v0.1",
        challenges=(
            RobustnessChallenge(
                "entry-plus-one-session",
                RobustnessKind.ENTRY_SHIFT,
                "Shift the executable entry by one trading session.",
                ("entry_convention",),
            ),
            RobustnessChallenge(
                "nearby-duration",
                RobustnessKind.PARAMETER_NEIGHBORHOOD,
                "Evaluate nearby consolidation durations around the frozen candidate region.",
                ("patterns.duration_sessions",),
            ),
            RobustnessChallenge(
                "nearby-tightness",
                RobustnessKind.PARAMETER_NEIGHBORHOOD,
                "Evaluate nearby tightness thresholds around the frozen candidate region.",
                ("patterns.tightness",),
            ),
            RobustnessChallenge(
                "alternate-liquidity",
                RobustnessKind.LIQUIDITY_THRESHOLD,
                "Apply a nearby reasonable point-in-time liquidity threshold.",
                ("universe.min_dollar_volume",),
            ),
            RobustnessChallenge(
                "alternate-breakout-boundary",
                RobustnessKind.ALTERNATE_BOUNDARY,
                "Use an alternate reasonable pre-trigger breakout boundary.",
                ("events.boundary_definition",),
            ),
            RobustnessChallenge(
                "exclude-strongest-years",
                RobustnessKind.EXCLUDE_TIME_PERIOD,
                "Re-estimate results after excluding the strongest calendar years.",
                ("validation.excluded_periods",),
            ),
            RobustnessChallenge(
                "exclude-largest-winners",
                RobustnessKind.EXCLUDE_EXTREME_WINNERS,
                "Re-estimate results after excluding the largest individual winners.",
                ("statistics.extreme_winner_exclusion",),
            ),
            RobustnessChallenge(
                "exclude-concentrated-sector",
                RobustnessKind.EXCLUDE_SECTOR,
                "Re-estimate after excluding selected high-concentration sectors.",
                ("validation.excluded_sectors",),
            ),
            RobustnessChallenge(
                "higher-cost-stress",
                RobustnessKind.COST_STRESS,
                "Re-evaluate tradable expectancy under higher transaction-cost assumptions.",
                ("costs",),
            ),
            RobustnessChallenge(
                "corrected-dataset-rerun",
                RobustnessKind.DATASET_REVISION,
                "Rerun the frozen hypothesis on a later corrected immutable dataset version.",
                ("data.dataset_version",),
            ),
        ),
    )
