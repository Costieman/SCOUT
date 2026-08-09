"""Construct point-in-time universe state directly from canonical daily bars."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date

from trade_scout.data.contracts import (
    DailyBar,
    DatasetVersion,
    InstrumentId,
    InstrumentRecord,
    PriceRepresentation,
    QualityStatus,
)
from trade_scout.universe.eligibility import (
    EligibilityObservation,
    MixedDatasetVersionError,
    UniverseRules,
    UniverseSnapshot,
    build_universe_snapshot,
)


class UniverseConstructionError(ValueError):
    """Raised when canonical inputs cannot support an unambiguous historical universe."""


class DuplicateCanonicalBarError(UniverseConstructionError):
    """Raised when one instrument/session appears more than once in canonical input."""


class UnknownUniverseInstrumentError(UniverseConstructionError):
    """Raised when canonical bars reference an instrument absent from the supplied master."""


@dataclass(frozen=True, slots=True)
class UniverseMeasurementPolicy:
    """Versioned rules for deriving eligibility measurements from canonical bars."""

    version: str
    liquidity_lookback_sessions: int
    reference_price_representation: PriceRepresentation = PriceRepresentation.RAW

    def __post_init__(self) -> None:
        if not self.version.strip():
            raise ValueError("universe measurement policy version must be non-empty")
        if self.liquidity_lookback_sessions <= 0:
            raise ValueError("liquidity lookback must be positive")


@dataclass(frozen=True, slots=True)
class UniverseHistory:
    """Deterministic sequence of historical universe snapshots for one dataset version."""

    dataset_version: DatasetVersion
    rules_version: str
    measurement_policy_version: str
    snapshots: tuple[UniverseSnapshot, ...]

    @property
    def eligibility_by_key(self) -> Mapping[tuple[InstrumentId, date], bool]:
        """Return research-serving eligibility keyed by canonical instrument/session."""

        return {
            (record.instrument_id, snapshot.as_of): record.eligible
            for snapshot in self.snapshots
            for record in snapshot.membership
        }


def build_universe_history(
    bars: Iterable[DailyBar],
    instruments: Iterable[InstrumentRecord],
    *,
    rules: UniverseRules,
    measurement_policy: UniverseMeasurementPolicy,
    start: date | None = None,
    end: date | None = None,
) -> UniverseHistory:
    """Build point-in-time universe snapshots using only bars available on each session.

    Future bars may be present in the canonical dataset, but each snapshot uses only observations
    dated on or before that snapshot's ``as_of`` date. Liquidity requires the complete configured
    trailing window; shortened windows are represented as missing measurements and therefore fail
    closed when the corresponding eligibility rule is enabled.
    """

    materialized = tuple(bars)
    if not materialized:
        raise UniverseConstructionError("universe construction requires canonical bars")

    versions = {bar.dataset_version for bar in materialized}
    if len(versions) != 1:
        raise MixedDatasetVersionError("universe construction cannot mix canonical dataset versions")
    dataset_version = next(iter(versions))

    instrument_by_id = _instrument_index(instruments)
    ordered_bars = _validate_and_order_bars(materialized, instrument_by_id)
    sessions = tuple(
        sorted(
            {
                bar.trade_date
                for bar in ordered_bars
                if (start is None or bar.trade_date >= start)
                and (end is None or bar.trade_date <= end)
            }
        )
    )
    if not sessions:
        raise UniverseConstructionError("requested universe-history range contains no canonical sessions")

    snapshots = tuple(
        build_universe_snapshot(
            _observations_as_of(
                ordered_bars,
                instrument_by_id,
                as_of=session,
                measurement_policy=measurement_policy,
                dataset_version=dataset_version,
            ),
            as_of=session,
            rules=rules,
        )
        for session in sessions
    )
    return UniverseHistory(
        dataset_version=dataset_version,
        rules_version=rules.version,
        measurement_policy_version=measurement_policy.version,
        snapshots=snapshots,
    )


def _instrument_index(
    instruments: Iterable[InstrumentRecord],
) -> dict[InstrumentId, InstrumentRecord]:
    index: dict[InstrumentId, InstrumentRecord] = {}
    for instrument in instruments:
        if instrument.instrument_id in index:
            raise UniverseConstructionError(
                f"duplicate instrument master record: {instrument.instrument_id}"
            )
        index[instrument.instrument_id] = instrument
    if not index:
        raise UniverseConstructionError("universe construction requires instrument master records")
    return index


def _validate_and_order_bars(
    bars: tuple[DailyBar, ...],
    instruments: Mapping[InstrumentId, InstrumentRecord],
) -> tuple[DailyBar, ...]:
    seen: set[tuple[InstrumentId, date]] = set()
    for bar in bars:
        if bar.instrument_id not in instruments:
            raise UnknownUniverseInstrumentError(
                f"canonical bar references unknown instrument {bar.instrument_id}"
            )
        key = (bar.instrument_id, bar.trade_date)
        if key in seen:
            raise DuplicateCanonicalBarError(
                f"duplicate canonical bar for {bar.instrument_id} on {bar.trade_date}"
            )
        seen.add(key)
    return tuple(sorted(bars, key=lambda item: (str(item.instrument_id), item.trade_date)))


def _observations_as_of(
    bars: tuple[DailyBar, ...],
    instruments: Mapping[InstrumentId, InstrumentRecord],
    *,
    as_of: date,
    measurement_policy: UniverseMeasurementPolicy,
    dataset_version: DatasetVersion,
) -> tuple[EligibilityObservation, ...]:
    by_instrument: dict[InstrumentId, list[DailyBar]] = {
        instrument_id: [] for instrument_id in instruments
    }
    for bar in bars:
        if bar.trade_date <= as_of:
            by_instrument[bar.instrument_id].append(bar)

    return tuple(
        _observation_from_history(
            instrument,
            tuple(by_instrument[instrument.instrument_id]),
            measurement_policy=measurement_policy,
            dataset_version=dataset_version,
            as_of=as_of,
        )
        for instrument in sorted(instruments.values(), key=lambda item: str(item.instrument_id))
    )


def _observation_from_history(
    instrument: InstrumentRecord,
    history: tuple[DailyBar, ...],
    *,
    measurement_policy: UniverseMeasurementPolicy,
    dataset_version: DatasetVersion,
    as_of: date,
) -> EligibilityObservation:
    if not history:
        return EligibilityObservation(
            instrument=instrument,
            measurement_as_of=as_of,
            reference_price=None,
            avg_dollar_volume=None,
            trading_sessions=0,
            quality_status=QualityStatus.REJECT,
            dataset_version=dataset_version,
        )

    latest = history[-1]
    reference_price = _reference_close(latest, measurement_policy.reference_price_representation)
    lookback = measurement_policy.liquidity_lookback_sessions
    avg_dollar_volume = None
    if len(history) >= lookback:
        trailing = history[-lookback:]
        avg_dollar_volume = sum(bar.close_raw * bar.volume_raw for bar in trailing) / lookback

    return EligibilityObservation(
        instrument=instrument,
        measurement_as_of=latest.trade_date,
        reference_price=reference_price,
        avg_dollar_volume=avg_dollar_volume,
        trading_sessions=len(history),
        quality_status=latest.quality_status,
        dataset_version=dataset_version,
    )


def _reference_close(bar: DailyBar, representation: PriceRepresentation) -> float | None:
    if representation is PriceRepresentation.RAW:
        return bar.close_raw
    return bar.close_split_adjusted
