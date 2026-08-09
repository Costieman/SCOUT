"""Deterministic planning for a representative-scale EODHD Phase 1 sample."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import date

from trade_scout.data.contracts import SecurityType
from trade_scout.data.provider import ProviderInstrument


class EodhdRepresentativeSampleError(ValueError):
    """Raised when provider inventory cannot satisfy the representative-sample policy."""


@dataclass(frozen=True, slots=True)
class EodhdRepresentativeSamplePolicy:
    """Explicit minimum composition for a frozen representative EODHD campaign plan."""

    active_count: int = 500
    delisted_count: int = 25
    min_exchanges: int = 2
    start: date = date(2015, 1, 2)
    end: date = date(2025, 12, 31)
    seed: str = "trade-scout-phase1-eodhd-representative-v0.1"

    def __post_init__(self) -> None:
        if self.active_count < 1:
            raise ValueError("representative active_count must be positive")
        if self.delisted_count < 1:
            raise ValueError("representative delisted_count must be positive")
        if self.min_exchanges < 1:
            raise ValueError("representative min_exchanges must be positive")
        if self.end <= self.start:
            raise ValueError("representative sample end must be after start")
        if not self.seed.strip():
            raise ValueError("representative sample seed must be non-empty")


@dataclass(frozen=True, slots=True)
class EodhdRepresentativeSelection:
    """Frozen provider inventory selection that can be serialized into a campaign plan."""

    active: tuple[ProviderInstrument, ...]
    delisted: tuple[ProviderInstrument, ...]
    exchanges: tuple[str, ...]
    policy: EodhdRepresentativeSamplePolicy

    @property
    def instruments(self) -> tuple[ProviderInstrument, ...]:
        return self.active + self.delisted


def select_eodhd_representative_sample(
    instruments: tuple[ProviderInstrument, ...],
    *,
    policy: EodhdRepresentativeSamplePolicy | None = None,
) -> EodhdRepresentativeSelection:
    """Select a reproducible ISIN-backed common-stock sample without ticker-based identity."""

    policy = policy or EodhdRepresentativeSamplePolicy()
    eligible = tuple(item for item in instruments if _eligible(item))
    active = tuple(item for item in eligible if item.active)
    delisted = tuple(item for item in eligible if not item.active)
    if len(active) < policy.active_count:
        raise EodhdRepresentativeSampleError(
            f"eligible active inventory {len(active)} is below required {policy.active_count}"
        )
    if len(delisted) < policy.delisted_count:
        raise EodhdRepresentativeSampleError(
            f"eligible delisted inventory {len(delisted)} is below required {policy.delisted_count}"
        )

    active_selected = _select_with_exchange_floor(
        active,
        count=policy.active_count,
        min_exchanges=policy.min_exchanges,
        seed=policy.seed + ":active",
    )
    delisted_selected = _ranked(delisted, seed=policy.seed + ":delisted")[: policy.delisted_count]
    exchanges = tuple(sorted({item.exchange for item in active_selected + delisted_selected}))
    if len(exchanges) < policy.min_exchanges:
        raise EodhdRepresentativeSampleError(
            f"selected inventory spans {len(exchanges)} exchanges; required {policy.min_exchanges}"
        )
    return EodhdRepresentativeSelection(
        active=active_selected,
        delisted=delisted_selected,
        exchanges=exchanges,
        policy=policy,
    )


def campaign_payload(
    selection: EodhdRepresentativeSelection,
    *,
    plan_version: str = "phase1-representative-v0.1",
) -> dict[str, object]:
    """Render the strict v0.1 EODHD campaign-plan schema for later live execution."""

    if not plan_version.strip():
        raise ValueError("plan_version must be non-empty")
    cases: list[dict[str, str]] = []
    for state, items in (("active", selection.active), ("delisted", selection.delisted)):
        for item in items:
            token = hashlib.sha256(item.provider_instrument_id.encode()).hexdigest()[:12]
            cases.append(
                {
                    "case_id": f"representative-{state}-{token}",
                    "symbol": item.symbol,
                    "start": selection.policy.start.isoformat(),
                    "end": selection.policy.end.isoformat(),
                    "expected_state": state,
                    "dataset_version": f"eodhd-representative-{token}-v0.1",
                }
            )
    return {
        "schema_version": "eodhd-campaign-plan-v0.1",
        "plan_version": plan_version,
        "cases": cases,
    }


def _eligible(item: ProviderInstrument) -> bool:
    return (
        item.provider_id == "eodhd"
        and item.security_type is SecurityType.COMMON_STOCK
        and item.currency.upper() == "USD"
        and item.provider_instrument_id.startswith("eodhd:isin:")
        and bool(item.exchange.strip())
        and bool(item.symbol.strip())
    )


def _ranked(
    instruments: tuple[ProviderInstrument, ...],
    *,
    seed: str,
) -> tuple[ProviderInstrument, ...]:
    return tuple(
        sorted(
            instruments,
            key=lambda item: (
                hashlib.sha256(f"{seed}|{item.provider_instrument_id}".encode()).hexdigest(),
                item.provider_instrument_id,
            ),
        )
    )


def _select_with_exchange_floor(
    instruments: tuple[ProviderInstrument, ...],
    *,
    count: int,
    min_exchanges: int,
    seed: str,
) -> tuple[ProviderInstrument, ...]:
    ranked = _ranked(instruments, seed=seed)
    by_exchange: dict[str, list[ProviderInstrument]] = {}
    for item in ranked:
        by_exchange.setdefault(item.exchange, []).append(item)
    if len(by_exchange) < min_exchanges:
        message = (
            f"eligible active inventory spans {len(by_exchange)} exchanges; "
            f"required {min_exchanges}"
        )
        raise EodhdRepresentativeSampleError(message)

    chosen: list[ProviderInstrument] = []
    chosen_ids: set[str] = set()
    exchange_order = sorted(
        by_exchange,
        key=lambda exchange: hashlib.sha256(f"{seed}|exchange|{exchange}".encode()).hexdigest(),
    )
    for exchange in exchange_order[:min_exchanges]:
        item = by_exchange[exchange][0]
        chosen.append(item)
        chosen_ids.add(item.provider_instrument_id)
    for item in ranked:
        if len(chosen) >= count:
            break
        if item.provider_instrument_id in chosen_ids:
            continue
        chosen.append(item)
        chosen_ids.add(item.provider_instrument_id)
    if len(chosen) != count:
        raise EodhdRepresentativeSampleError("unable to fill representative active sample")
    return tuple(chosen)
