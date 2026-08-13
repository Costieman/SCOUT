"""Predeclared multiple-testing metadata and deterministic p-value adjustment."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from math import isfinite


class MultiplicityMethod(StrEnum):
    """Multiplicity methods explicitly supported by the validation layer."""

    NONE_EXPLORATORY = "NONE_EXPLORATORY"
    BONFERRONI = "BONFERRONI"
    BENJAMINI_HOCHBERG = "BENJAMINI_HOCHBERG"


@dataclass(frozen=True, slots=True)
class HypothesisFamily:
    """Frozen hypothesis family declared before confirmatory evaluation."""

    family_id: str
    hypothesis_ids: tuple[str, ...]
    method: MultiplicityMethod
    alpha: float = 0.05

    def __post_init__(self) -> None:
        if not self.family_id.strip():
            raise ValueError("family_id must be non-empty")
        if not self.hypothesis_ids:
            raise ValueError("hypothesis family must contain at least one hypothesis")
        if any(not hypothesis_id.strip() for hypothesis_id in self.hypothesis_ids):
            raise ValueError("hypothesis IDs must be non-empty")
        if len(set(self.hypothesis_ids)) != len(self.hypothesis_ids):
            raise ValueError("hypothesis IDs must be unique within a family")
        if not isfinite(self.alpha) or not 0.0 < self.alpha < 1.0:
            raise ValueError("alpha must lie strictly between zero and one")


@dataclass(frozen=True, slots=True)
class AdjustedPValue:
    """One hypothesis p-value and its family-aware adjusted value."""

    hypothesis_id: str
    raw_p_value: float
    adjusted_p_value: float

    def __post_init__(self) -> None:
        if not self.hypothesis_id.strip():
            raise ValueError("hypothesis_id must be non-empty")
        for field_name, value in (
            ("raw_p_value", self.raw_p_value),
            ("adjusted_p_value", self.adjusted_p_value),
        ):
            if not isfinite(value) or not 0.0 <= value <= 1.0:
                raise ValueError(f"{field_name} must be finite and between zero and one")


def adjust_p_values(
    family: HypothesisFamily,
    raw_p_values: dict[str, float],
) -> tuple[AdjustedPValue, ...]:
    """Adjust a complete frozen hypothesis family without dropping unfavorable tests."""

    expected = set(family.hypothesis_ids)
    observed = set(raw_p_values)
    if observed != expected:
        missing = sorted(expected - observed)
        unexpected = sorted(observed - expected)
        raise ValueError(
            "p-value set must exactly match the registered hypothesis family; "
            f"missing={missing}, unexpected={unexpected}"
        )
    for hypothesis_id, p_value in raw_p_values.items():
        if not isfinite(p_value) or not 0.0 <= p_value <= 1.0:
            raise ValueError(f"invalid p-value for hypothesis {hypothesis_id!r}")

    if family.method is MultiplicityMethod.NONE_EXPLORATORY:
        adjusted = dict(raw_p_values)
    elif family.method is MultiplicityMethod.BONFERRONI:
        count = len(family.hypothesis_ids)
        adjusted = {
            hypothesis_id: min(1.0, p_value * count)
            for hypothesis_id, p_value in raw_p_values.items()
        }
    else:
        adjusted = _benjamini_hochberg(raw_p_values)

    return tuple(
        AdjustedPValue(
            hypothesis_id=hypothesis_id,
            raw_p_value=raw_p_values[hypothesis_id],
            adjusted_p_value=adjusted[hypothesis_id],
        )
        for hypothesis_id in family.hypothesis_ids
    )


def _benjamini_hochberg(raw_p_values: dict[str, float]) -> dict[str, float]:
    """Return monotone Benjamini-Hochberg adjusted p-values."""

    ordered = sorted(raw_p_values.items(), key=lambda item: (item[1], item[0]))
    count = len(ordered)
    adjusted: dict[str, float] = {}
    running_minimum = 1.0
    for reverse_index in range(count - 1, -1, -1):
        hypothesis_id, p_value = ordered[reverse_index]
        rank = reverse_index + 1
        candidate = min(1.0, p_value * count / rank)
        running_minimum = min(running_minimum, candidate)
        adjusted[hypothesis_id] = running_minimum
    return adjusted
