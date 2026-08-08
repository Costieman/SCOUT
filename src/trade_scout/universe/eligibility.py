"""Point-in-time universe eligibility without survivor or future-information leakage."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
from enum import StrEnum

from trade_scout.data.contracts import (
    DatasetVersion,
    InstrumentId,
    InstrumentRecord,
    QualityStatus,
    SecurityType,
)


class FutureEligibilityDataError(ValueError):
    """Raised when an eligibility decision would consume information from the future."""


class MixedDatasetVersionError(ValueError):
    """Raised when one universe snapshot mixes canonical dataset versions."""


class EligibilityReason(StrEnum):
    """Machine-readable reason an instrument is not eligible on a historical date."""

    BEFORE_FIRST_TRADE = "before_first_trade"
    AFTER_DELISTING = "after_delisting"
    EXCHANGE_EXCLUDED = "exchange_excluded"
    SECURITY_TYPE_EXCLUDED = "security_type_excluded"
    QUALITY_NOT_ALLOWED = "quality_not_allowed"
    MISSING_REFERENCE_PRICE = "missing_reference_price"
    BELOW_MIN_PRICE = "below_min_price"
    MISSING_LIQUIDITY = "missing_liquidity"
    BELOW_MIN_LIQUIDITY = "below_min_liquidity"
    MISSING_TRADING_HISTORY = "missing_trading_history"
    INSUFFICIENT_TRADING_HISTORY = "insufficient_trading_history"


@dataclass(frozen=True, slots=True)
class UniverseRules:
    """Explicit eligibility rules for one versioned historical universe definition."""

    version: str
    allowed_exchanges: frozenset[str]
    allowed_security_types: frozenset[SecurityType]
    allowed_quality_states: frozenset[QualityStatus]
    min_price: float | None = None
    min_avg_dollar_volume: float | None = None
    min_trading_sessions: int | None = None

    def __post_init__(self) -> None:
        if not self.version.strip():
            raise ValueError("universe rule version must be non-empty")
        if not self.allowed_exchanges:
            raise ValueError("at least one exchange must be explicitly allowed")
        if not self.allowed_security_types:
            raise ValueError("at least one security type must be explicitly allowed")
        if not self.allowed_quality_states:
            raise ValueError("at least one quality state must be explicitly allowed")
        if self.min_price is not None and self.min_price < 0:
            raise ValueError("minimum price must be non-negative")
        if self.min_avg_dollar_volume is not None and self.min_avg_dollar_volume < 0:
            raise ValueError("minimum average dollar volume must be non-negative")
        if self.min_trading_sessions is not None and self.min_trading_sessions < 0:
            raise ValueError("minimum trading sessions must be non-negative")


@dataclass(frozen=True, slots=True)
class EligibilityObservation:
    """Only the dated measurements permitted to support one universe decision."""

    instrument: InstrumentRecord
    measurement_as_of: date
    reference_price: float | None
    avg_dollar_volume: float | None
    trading_sessions: int | None
    quality_status: QualityStatus
    dataset_version: DatasetVersion

    def __post_init__(self) -> None:
        if self.reference_price is not None and self.reference_price < 0:
            raise ValueError("reference price must be non-negative")
        if self.avg_dollar_volume is not None and self.avg_dollar_volume < 0:
            raise ValueError("average dollar volume must be non-negative")
        if self.trading_sessions is not None and self.trading_sessions < 0:
            raise ValueError("trading sessions must be non-negative")


@dataclass(frozen=True, slots=True)
class UniverseMembershipRecord:
    """Auditable point-in-time eligibility result for one instrument and date."""

    instrument_id: InstrumentId
    as_of: date
    eligible: bool
    exclusion_reasons: tuple[EligibilityReason, ...]
    universe_version: str
    dataset_version: DatasetVersion
    measurement_as_of: date


@dataclass(frozen=True, slots=True)
class UniverseSnapshot:
    """Deterministic historical universe snapshot tied to one data and rule version."""

    as_of: date
    universe_version: str
    dataset_version: DatasetVersion
    membership: tuple[UniverseMembershipRecord, ...]

    @property
    def eligible_instrument_ids(self) -> tuple[InstrumentId, ...]:
        """Return eligible IDs in deterministic internal-ID order."""

        return tuple(record.instrument_id for record in self.membership if record.eligible)


def evaluate_eligibility(
    observation: EligibilityObservation,
    *,
    as_of: date,
    rules: UniverseRules,
) -> UniverseMembershipRecord:
    """Evaluate eligibility using only reference and market information known by ``as_of``."""

    if observation.measurement_as_of > as_of:
        raise FutureEligibilityDataError(
            f"eligibility data dated {observation.measurement_as_of} cannot be used for {as_of}"
        )

    instrument = observation.instrument
    reasons: list[EligibilityReason] = []

    if instrument.first_trade_date is not None and as_of < instrument.first_trade_date:
        reasons.append(EligibilityReason.BEFORE_FIRST_TRADE)
    if instrument.delisting_date is not None and as_of > instrument.delisting_date:
        reasons.append(EligibilityReason.AFTER_DELISTING)
    if instrument.exchange not in rules.allowed_exchanges:
        reasons.append(EligibilityReason.EXCHANGE_EXCLUDED)
    if instrument.security_type not in rules.allowed_security_types:
        reasons.append(EligibilityReason.SECURITY_TYPE_EXCLUDED)
    if observation.quality_status not in rules.allowed_quality_states:
        reasons.append(EligibilityReason.QUALITY_NOT_ALLOWED)

    _apply_price_rule(observation, rules, reasons)
    _apply_liquidity_rule(observation, rules, reasons)
    _apply_history_rule(observation, rules, reasons)

    frozen_reasons = tuple(reasons)
    return UniverseMembershipRecord(
        instrument_id=instrument.instrument_id,
        as_of=as_of,
        eligible=not frozen_reasons,
        exclusion_reasons=frozen_reasons,
        universe_version=rules.version,
        dataset_version=observation.dataset_version,
        measurement_as_of=observation.measurement_as_of,
    )


def build_universe_snapshot(
    observations: Iterable[EligibilityObservation],
    *,
    as_of: date,
    rules: UniverseRules,
) -> UniverseSnapshot:
    """Build one deterministic snapshot; mixed canonical dataset versions fail explicitly."""

    materialized = tuple(observations)
    if not materialized:
        raise ValueError("a universe snapshot requires at least one observation")

    versions = {observation.dataset_version for observation in materialized}
    if len(versions) != 1:
        raise MixedDatasetVersionError(
            "one universe snapshot cannot mix canonical dataset versions"
        )
    dataset_version = next(iter(versions))

    membership = tuple(
        sorted(
            (
                evaluate_eligibility(observation, as_of=as_of, rules=rules)
                for observation in materialized
            ),
            key=lambda record: str(record.instrument_id),
        )
    )
    return UniverseSnapshot(
        as_of=as_of,
        universe_version=rules.version,
        dataset_version=dataset_version,
        membership=membership,
    )


def _apply_price_rule(
    observation: EligibilityObservation,
    rules: UniverseRules,
    reasons: list[EligibilityReason],
) -> None:
    if rules.min_price is None:
        return
    if observation.reference_price is None:
        reasons.append(EligibilityReason.MISSING_REFERENCE_PRICE)
    elif observation.reference_price < rules.min_price:
        reasons.append(EligibilityReason.BELOW_MIN_PRICE)


def _apply_liquidity_rule(
    observation: EligibilityObservation,
    rules: UniverseRules,
    reasons: list[EligibilityReason],
) -> None:
    if rules.min_avg_dollar_volume is None:
        return
    if observation.avg_dollar_volume is None:
        reasons.append(EligibilityReason.MISSING_LIQUIDITY)
    elif observation.avg_dollar_volume < rules.min_avg_dollar_volume:
        reasons.append(EligibilityReason.BELOW_MIN_LIQUIDITY)


def _apply_history_rule(
    observation: EligibilityObservation,
    rules: UniverseRules,
    reasons: list[EligibilityReason],
) -> None:
    if rules.min_trading_sessions is None:
        return
    if observation.trading_sessions is None:
        reasons.append(EligibilityReason.MISSING_TRADING_HISTORY)
    elif observation.trading_sessions < rules.min_trading_sessions:
        reasons.append(EligibilityReason.INSUFFICIENT_TRADING_HISTORY)
