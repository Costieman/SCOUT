"""Reusable evidence harness for evaluating candidate market-data provider adapters."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import StrEnum

from trade_scout.data.contracts import CorporateActionType, DatasetVersion, QualityStatus
from trade_scout.data.instrument_master import instrument_from_primary_provider
from trade_scout.data.normalization import normalize_provider_daily_bars
from trade_scout.data.provider import (
    CorporateActionRequest,
    DailyBarRequest,
    DataFamily,
    ProviderAdapter,
    ProviderCapabilities,
    ProviderHealth,
    ProviderHealthStatus,
    ProviderInstrument,
)


class EvaluationState(StrEnum):
    """Machine-readable result of one provider-evaluation check."""

    PASS = "PASS"
    FAIL = "FAIL"
    NOT_EVALUATED = "NOT_EVALUATED"


@dataclass(frozen=True, slots=True)
class ProviderEvaluationCase:
    """One provider-specific sample case executed through the common adapter boundary."""

    case_id: str
    provider_instrument_id: str
    provider_symbol: str
    start: date
    end: date
    expected_active: bool | None = None
    required_action_types: frozenset[CorporateActionType] = frozenset()
    require_symbol_history: bool = False

    def __post_init__(self) -> None:
        if not self.case_id.strip():
            raise ValueError("provider evaluation case_id must be non-empty")
        if not self.provider_instrument_id.strip():
            raise ValueError("provider evaluation instrument ID must be non-empty")
        if not self.provider_symbol.strip():
            raise ValueError("provider evaluation symbol must be non-empty")
        if self.end < self.start:
            raise ValueError("provider evaluation end date must be on or after start date")


@dataclass(frozen=True, slots=True)
class EvaluationCheck:
    """One auditable automated or explicitly deferred provider-evaluation assertion."""

    check_id: str
    state: EvaluationState
    detail: str


@dataclass(frozen=True, slots=True)
class ProviderCaseEvaluation:
    """Automated evidence collected for one targeted provider sample case."""

    case_id: str
    checks: tuple[EvaluationCheck, ...]
    daily_bar_count: int
    corporate_action_count: int
    normalization_status: QualityStatus | None

    @property
    def automated_gate_passed(self) -> bool:
        """Return whether no automated check in this case failed."""

        return all(check.state is not EvaluationState.FAIL for check in self.checks)


@dataclass(frozen=True, slots=True)
class ProviderEvaluationReport:
    """Provider-boundary evidence that remains distinct from final provider acceptance."""

    provider_id: str
    capabilities: ProviderCapabilities
    health: ProviderHealth
    checks: tuple[EvaluationCheck, ...]
    cases: tuple[ProviderCaseEvaluation, ...]
    unresolved_manual_gates: tuple[str, ...]

    @property
    def automated_gate_passed(self) -> bool:
        """Return whether capability and case checks contain no automated failure."""

        return all(check.state is not EvaluationState.FAIL for check in self.checks) and all(
            case.automated_gate_passed for case in self.cases
        )

    @property
    def provider_accepted(self) -> bool:
        """Remain false while licensing/raw/revision evidence still requires external validation."""

        return self.automated_gate_passed and not self.unresolved_manual_gates


def evaluate_provider_adapter(
    adapter: ProviderAdapter,
    cases: tuple[ProviderEvaluationCase, ...],
    *,
    dataset_version: DatasetVersion,
) -> ProviderEvaluationReport:
    """Run a repeatable provider-neutral screen without declaring final provider acceptance."""

    capabilities = adapter.describe_capabilities()
    health = adapter.health_check()
    instruments = tuple(adapter.get_instruments(as_of=None))

    top_level_checks = (
        _identity_check(adapter.provider_id, capabilities, health),
        _health_check(health),
        _capability_check(capabilities, DataFamily.INSTRUMENTS),
        _capability_check(capabilities, DataFamily.DAILY_BARS),
        _capability_check(capabilities, DataFamily.CORPORATE_ACTIONS),
        _delisting_capability_check(capabilities),
    )

    evaluated_cases = tuple(
        _evaluate_case(
            adapter,
            capabilities,
            instruments,
            case,
            dataset_version=dataset_version,
        )
        for case in cases
    )

    return ProviderEvaluationReport(
        provider_id=adapter.provider_id,
        capabilities=capabilities,
        health=health,
        checks=top_level_checks,
        cases=evaluated_cases,
        unresolved_manual_gates=(
            "confirm licensing permits intended local raw/canonical storage and use",
            "verify exact raw vendor payload preservation in the concrete adapter transport path",
            "characterize provider correction/revision behavior across retrieval times",
            "run the sample on real historical active, inactive, corporate-action, and symbol-change cases",
        ),
    )


def _evaluate_case(
    adapter: ProviderAdapter,
    capabilities: ProviderCapabilities,
    instruments: tuple[ProviderInstrument, ...],
    case: ProviderEvaluationCase,
    *,
    dataset_version: DatasetVersion,
) -> ProviderCaseEvaluation:
    instrument_matches = tuple(
        instrument
        for instrument in instruments
        if instrument.provider_id == adapter.provider_id
        and instrument.provider_instrument_id == case.provider_instrument_id
    )

    checks: list[EvaluationCheck] = []
    if len(instrument_matches) != 1:
        checks.append(
            EvaluationCheck(
                check_id="instrument_identity",
                state=EvaluationState.FAIL,
                detail=f"expected one exact provider identity, found {len(instrument_matches)}",
            )
        )
        return ProviderCaseEvaluation(
            case_id=case.case_id,
            checks=tuple(checks),
            daily_bar_count=0,
            corporate_action_count=0,
            normalization_status=None,
        )

    instrument = instrument_matches[0]
    checks.append(
        EvaluationCheck(
            check_id="instrument_identity",
            state=EvaluationState.PASS,
            detail="exact provider instrument identity was discoverable",
        )
    )

    if case.expected_active is not None:
        checks.append(
            EvaluationCheck(
                check_id="active_status",
                state=(
                    EvaluationState.PASS
                    if instrument.active is case.expected_active
                    else EvaluationState.FAIL
                ),
                detail=f"provider active={instrument.active}; expected {case.expected_active}",
            )
        )

    request = DailyBarRequest(
        start=case.start,
        end=case.end,
        provider_symbols=(case.provider_symbol,),
        run_id=f"provider-evaluation:{case.case_id}",
    )
    first_bars = tuple(adapter.get_daily_bars(request))
    second_bars = tuple(adapter.get_daily_bars(request))
    checks.append(
        EvaluationCheck(
            check_id="bounded_daily_retrieval",
            state=EvaluationState.PASS if first_bars else EvaluationState.FAIL,
            detail=f"retrieved {len(first_bars)} daily bars",
        )
    )
    checks.append(
        EvaluationCheck(
            check_id="repeatability",
            state=EvaluationState.PASS if first_bars == second_bars else EvaluationState.FAIL,
            detail="repeated bounded request returned identical normalized records",
        )
    )

    out_of_range = tuple(
        bar for bar in first_bars if not case.start <= bar.trade_date <= case.end
    )
    wrong_identity = tuple(
        bar
        for bar in first_bars
        if bar.provider_id != adapter.provider_id
        or bar.provider_instrument_id != case.provider_instrument_id
    )
    checks.append(
        EvaluationCheck(
            check_id="daily_bar_scope",
            state=(
                EvaluationState.PASS
                if not out_of_range and not wrong_identity
                else EvaluationState.FAIL
            ),
            detail=(
                f"out_of_range={len(out_of_range)}, wrong_identity={len(wrong_identity)}"
            ),
        )
    )

    canonical_instrument = instrument_from_primary_provider(instrument)
    normalized = normalize_provider_daily_bars(
        first_bars,
        instruments=(canonical_instrument,),
        dataset_version=dataset_version,
    )
    normalization_passed = normalized.status in {QualityStatus.PASS, QualityStatus.WARN}
    checks.append(
        EvaluationCheck(
            check_id="canonical_normalization",
            state=EvaluationState.PASS if normalization_passed else EvaluationState.FAIL,
            detail=(
                f"status={normalized.status}; canonical_bars={len(normalized.bars)}; "
                f"normalization_issues={len(normalized.normalization_issues)}; "
                f"quality_issues={len(normalized.quality_issues)}"
            ),
        )
    )

    actions = tuple(
        adapter.get_corporate_actions(
            CorporateActionRequest(
                start=case.start,
                end=case.end,
                provider_symbols=(case.provider_symbol,),
            )
        )
    )
    action_types = frozenset(action.action_type for action in actions)
    missing_actions = case.required_action_types - action_types
    checks.append(
        EvaluationCheck(
            check_id="required_corporate_actions",
            state=EvaluationState.PASS if not missing_actions else EvaluationState.FAIL,
            detail=(
                "all required corporate-action families found"
                if not missing_actions
                else "missing: " + ", ".join(sorted(str(item) for item in missing_actions))
            ),
        )
    )

    if case.require_symbol_history:
        if not capabilities.supports_symbol_history:
            checks.append(
                EvaluationCheck(
                    check_id="symbol_history",
                    state=EvaluationState.FAIL,
                    detail="adapter capability declaration does not support symbol history",
                )
            )
        else:
            history = tuple(
                adapter.get_symbol_history(
                    provider_instrument_ids=(case.provider_instrument_id,)
                )
            )
            checks.append(
                EvaluationCheck(
                    check_id="symbol_history",
                    state=EvaluationState.PASS if history else EvaluationState.FAIL,
                    detail=f"retrieved {len(history)} dated symbol-history records",
                )
            )

    return ProviderCaseEvaluation(
        case_id=case.case_id,
        checks=tuple(checks),
        daily_bar_count=len(first_bars),
        corporate_action_count=len(actions),
        normalization_status=normalized.status,
    )


def _identity_check(
    provider_id: str,
    capabilities: ProviderCapabilities,
    health: ProviderHealth,
) -> EvaluationCheck:
    consistent = provider_id == capabilities.provider_id == health.provider_id
    return EvaluationCheck(
        check_id="provider_identity_consistency",
        state=EvaluationState.PASS if consistent else EvaluationState.FAIL,
        detail=(
            f"adapter={provider_id}, capabilities={capabilities.provider_id}, "
            f"health={health.provider_id}"
        ),
    )


def _health_check(health: ProviderHealth) -> EvaluationCheck:
    return EvaluationCheck(
        check_id="provider_health",
        state=(
            EvaluationState.PASS
            if health.status is ProviderHealthStatus.HEALTHY
            else EvaluationState.FAIL
        ),
        detail=f"provider health is {health.status}",
    )


def _capability_check(
    capabilities: ProviderCapabilities,
    family: DataFamily,
) -> EvaluationCheck:
    supported = family in capabilities.data_families
    return EvaluationCheck(
        check_id=f"capability:{family}",
        state=EvaluationState.PASS if supported else EvaluationState.FAIL,
        detail=f"{family} declared supported={supported}",
    )


def _delisting_capability_check(capabilities: ProviderCapabilities) -> EvaluationCheck:
    return EvaluationCheck(
        check_id="delisted_instrument_support",
        state=(
            EvaluationState.PASS if capabilities.supports_delisted else EvaluationState.FAIL
        ),
        detail=f"supports_delisted={capabilities.supports_delisted}",
    )
