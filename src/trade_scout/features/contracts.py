"""Typed contracts for point-in-time Trade Scout feature values."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from enum import StrEnum

from trade_scout.data.contracts import DatasetVersion, InstrumentId, PriceRepresentation

FeatureParameter = str | int | float | bool


class FeatureAvailabilityStatus(StrEnum):
    """Whether a feature value is usable at one instrument/session."""

    AVAILABLE = "AVAILABLE"
    WARMUP = "WARMUP"
    INPUT_UNAVAILABLE = "INPUT_UNAVAILABLE"


@dataclass(frozen=True, slots=True)
class FeatureDefinition:
    """Versioned mathematical definition for one feature family/materialization."""

    feature_name: str
    feature_version: str
    description: str
    required_price_representation: PriceRepresentation
    resolved_parameters: Mapping[str, FeatureParameter]
    units: str
    minimum_observations: int

    def __post_init__(self) -> None:
        if not self.feature_name.strip():
            raise ValueError("feature_name must be non-empty")
        if not self.feature_version.strip():
            raise ValueError("feature_version must be non-empty")
        if not self.description.strip():
            raise ValueError("description must be non-empty")
        if not self.units.strip():
            raise ValueError("units must be non-empty")
        if self.minimum_observations <= 0:
            raise ValueError("minimum_observations must be positive")


@dataclass(frozen=True, slots=True)
class FeatureValue:
    """One deterministic point-in-time feature observation with provenance."""

    instrument_id: InstrumentId
    trade_date: date
    feature_name: str
    feature_version: str
    resolved_parameters: Mapping[str, FeatureParameter]
    value: float | None
    units: str
    availability_status: FeatureAvailabilityStatus
    dataset_version: DatasetVersion
    feature_set_version: str

    def __post_init__(self) -> None:
        if not self.feature_name.strip():
            raise ValueError("feature_name must be non-empty")
        if not self.feature_version.strip():
            raise ValueError("feature_version must be non-empty")
        if not self.units.strip():
            raise ValueError("units must be non-empty")
        if not self.feature_set_version.strip():
            raise ValueError("feature_set_version must be non-empty")
        if self.availability_status is FeatureAvailabilityStatus.AVAILABLE and self.value is None:
            raise ValueError("AVAILABLE feature values must contain a numeric value")
        if (
            self.availability_status is not FeatureAvailabilityStatus.AVAILABLE
            and self.value is not None
        ):
            raise ValueError("unavailable feature values must not contain a numeric value")


@dataclass(frozen=True, slots=True)
class FeatureSetDefinition:
    """Versioned collection of registered features requested together."""

    feature_set_version: str
    definitions: tuple[FeatureDefinition, ...]

    def __post_init__(self) -> None:
        if not self.feature_set_version.strip():
            raise ValueError("feature_set_version must be non-empty")
        if not self.definitions:
            raise ValueError("feature set must contain at least one definition")
        identities = tuple(
            (definition.feature_name, definition.feature_version) for definition in self.definitions
        )
        if len(set(identities)) != len(identities):
            raise ValueError("feature set contains duplicate feature identities")
