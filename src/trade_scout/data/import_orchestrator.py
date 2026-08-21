"""Provider-neutral per-asset import orchestration for canonical data promotion.

The orchestrator does not perform provider I/O or analytical calculations. It classifies
observed durable state, determines the next admissible stage for each asset, and keeps
exceptional assets from blocking unrelated clean assets.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from enum import StrEnum
from typing import Iterable


class ImportStage(StrEnum):
    """Ordered stages in the historical equity import path."""

    ACQUIRE = "ACQUIRE"
    STRUCTURAL_VALIDATE = "STRUCTURAL_VALIDATE"
    IDENTITY_VERIFY = "IDENTITY_VERIFY"
    IDENTITY_REGISTER = "IDENTITY_REGISTER"
    RECONCILE = "RECONCILE"
    COMPLETENESS = "COMPLETENESS"
    PROMOTE = "PROMOTE"


class ImportTerminalState(StrEnum):
    """Explicit terminal outcomes for one requested asset."""

    PROMOTED = "PROMOTED"
    DEFERRED = "DEFERRED"
    QUARANTINED = "QUARANTINED"


@dataclass(frozen=True, slots=True)
class AssetImportEvidence:
    """Durable evidence already present for one requested symbol.

    Boolean fields describe completed stages only. They must be derived from persisted
    receipts/artifacts by an inventory adapter; the orchestrator never guesses them.
    """

    symbol: str
    acquired: bool = False
    structurally_validated: bool = False
    identity_verified: bool = False
    identity_registered: bool = False
    reconciled: bool = False
    complete: bool = False
    promoted: bool = False
    deferred_reason: str | None = None
    quarantine_reason: str | None = None

    def __post_init__(self) -> None:
        if not self.symbol.strip():
            raise ValueError("symbol must be non-empty")
        if self.deferred_reason and self.quarantine_reason:
            raise ValueError("asset cannot be both deferred and quarantined")
        if self.promoted and not self.complete:
            raise ValueError("promoted asset must have passed completeness")
        if self.complete and not self.reconciled:
            raise ValueError("complete asset must have passed reconciliation")
        if self.reconciled and not self.identity_registered:
            raise ValueError("reconciled asset must have registered identity")
        if self.identity_registered and not self.identity_verified:
            raise ValueError("registered identity must have been verified")
        if self.identity_verified and not self.structurally_validated:
            raise ValueError("identity verification requires structural validation")
        if self.structurally_validated and not self.acquired:
            raise ValueError("structural validation requires acquisition")

    @property
    def terminal_state(self) -> ImportTerminalState | None:
        """Return explicit terminal state, if one exists."""

        if self.promoted:
            return ImportTerminalState.PROMOTED
        if self.deferred_reason:
            return ImportTerminalState.DEFERRED
        if self.quarantine_reason:
            return ImportTerminalState.QUARANTINED
        return None


@dataclass(frozen=True, slots=True)
class AssetImportPlan:
    """The next safe action for one asset."""

    symbol: str
    next_stage: ImportStage | None
    terminal_state: ImportTerminalState | None
    reason: str

    @property
    def needs_work(self) -> bool:
        return self.next_stage is not None


@dataclass(frozen=True, slots=True)
class ImportInventorySummary:
    """Deterministic accounting summary across the requested universe."""

    total_assets: int
    terminal_counts: dict[ImportTerminalState, int]
    next_stage_counts: dict[ImportStage, int]

    @property
    def terminally_accounted_for(self) -> int:
        return sum(self.terminal_counts.values())

    @property
    def remaining(self) -> int:
        return self.total_assets - self.terminally_accounted_for


class ImportOrchestrator:
    """Classify durable state and choose the next admissible stage per asset."""

    def plan(self, evidence: AssetImportEvidence) -> AssetImportPlan:
        """Return the next stage without repeating already completed work."""

        terminal = evidence.terminal_state
        if terminal is not None:
            reason = {
                ImportTerminalState.PROMOTED: "already canonical",
                ImportTerminalState.DEFERRED: evidence.deferred_reason or "deferred",
                ImportTerminalState.QUARANTINED: evidence.quarantine_reason or "quarantined",
            }[terminal]
            return AssetImportPlan(
                symbol=evidence.symbol,
                next_stage=None,
                terminal_state=terminal,
                reason=reason,
            )

        if not evidence.acquired:
            return self._stage(evidence, ImportStage.ACQUIRE, "price history not acquired")
        if not evidence.structurally_validated:
            return self._stage(
                evidence,
                ImportStage.STRUCTURAL_VALIDATE,
                "acquired data awaits structural validation",
            )
        if not evidence.identity_verified:
            return self._stage(
                evidence,
                ImportStage.IDENTITY_VERIFY,
                "structurally valid data awaits identity verification",
            )
        if not evidence.identity_registered:
            return self._stage(
                evidence,
                ImportStage.IDENTITY_REGISTER,
                "verified identity awaits registration",
            )
        if not evidence.reconciled:
            return self._stage(
                evidence,
                ImportStage.RECONCILE,
                "registered identity awaits reconciliation",
            )
        if not evidence.complete:
            return self._stage(
                evidence,
                ImportStage.COMPLETENESS,
                "reconciled asset awaits completeness checks",
            )
        return self._stage(evidence, ImportStage.PROMOTE, "complete asset awaits promotion")

    def plan_many(self, evidence: Iterable[AssetImportEvidence]) -> tuple[AssetImportPlan, ...]:
        """Plan assets independently in stable symbol order."""

        items = tuple(evidence)
        symbols = [item.symbol for item in items]
        if len(set(symbols)) != len(symbols):
            raise ValueError("inventory contains duplicate symbols")
        return tuple(self.plan(item) for item in sorted(items, key=lambda item: item.symbol))

    def summarize(self, evidence: Iterable[AssetImportEvidence]) -> ImportInventorySummary:
        """Summarize terminal accounting and remaining work by next stage."""

        plans = self.plan_many(evidence)
        terminal_counter: Counter[ImportTerminalState] = Counter()
        stage_counter: Counter[ImportStage] = Counter()
        for plan in plans:
            if plan.terminal_state is not None:
                terminal_counter[plan.terminal_state] += 1
            elif plan.next_stage is not None:
                stage_counter[plan.next_stage] += 1

        return ImportInventorySummary(
            total_assets=len(plans),
            terminal_counts={state: terminal_counter[state] for state in ImportTerminalState},
            next_stage_counts={stage: stage_counter[stage] for stage in ImportStage},
        )

    @staticmethod
    def _stage(
        evidence: AssetImportEvidence,
        stage: ImportStage,
        reason: str,
    ) -> AssetImportPlan:
        return AssetImportPlan(
            symbol=evidence.symbol,
            next_stage=stage,
            terminal_state=None,
            reason=reason,
        )
