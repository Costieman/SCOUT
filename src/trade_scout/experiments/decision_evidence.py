"""Fail-closed verification of experiment evidence cited by research decisions.

This module checks persistence integrity and experiment completion only. It does not infer whether the
cited evidence is scientifically sufficient, statistically significant, or economically useful.
"""

from __future__ import annotations

from dataclasses import dataclass

from trade_scout.experiments.contracts import ExperimentStatus, ManifestStore
from trade_scout.experiments.decision_ledger import FileResearchDecisionLedger
from trade_scout.experiments.decisions import ResearchDecision, ResearchDecisionError
from trade_scout.experiments.integrity import audit_experiment


@dataclass(frozen=True, slots=True)
class DecisionExperimentEvidence:
    """Verification state for one experiment cited by a research decision."""

    experiment_id: str
    status: ExperimentStatus | None
    integrity_verified: bool
    detail: str

    @property
    def admissible(self) -> bool:
        """Return true only for intact experiments that completed successfully."""

        return self.integrity_verified and self.status is ExperimentStatus.SUCCEEDED


@dataclass(frozen=True, slots=True)
class DecisionEvidenceReport:
    """Complete persisted-experiment evidence assessment for one research decision."""

    decision_id: str
    experiments: tuple[DecisionExperimentEvidence, ...]

    @property
    def verified(self) -> bool:
        """Return true only when every cited experiment is admissible."""

        return bool(self.experiments) and all(item.admissible for item in self.experiments)

    def require_verified(self) -> None:
        """Raise before a decision is recorded when cited experiment evidence is not intact."""

        if self.verified:
            return
        failures = ", ".join(
            f"{item.experiment_id}:{item.detail}"
            for item in self.experiments
            if not item.admissible
        )
        raise ResearchDecisionError(
            f"research decision evidence verification failed for {self.decision_id}: {failures}"
        )


def audit_decision_evidence(
    store: ManifestStore,
    decision: ResearchDecision,
) -> DecisionEvidenceReport:
    """Verify every experiment cited by a research decision and expose failures explicitly."""

    records: list[DecisionExperimentEvidence] = []
    for experiment_id in decision.experiment_ids:
        integrity = audit_experiment(store, experiment_id)
        if not integrity.verified:
            records.append(
                DecisionExperimentEvidence(
                    experiment_id=experiment_id,
                    status=None,
                    integrity_verified=False,
                    detail=integrity.manifest_detail,
                )
            )
            continue

        manifest = store.read_manifest(experiment_id)
        if manifest.status is ExperimentStatus.SUCCEEDED:
            detail = "verified SUCCEEDED experiment"
        else:
            detail = f"experiment status is {manifest.status.value}"
        records.append(
            DecisionExperimentEvidence(
                experiment_id=experiment_id,
                status=manifest.status,
                integrity_verified=True,
                detail=detail,
            )
        )

    return DecisionEvidenceReport(decision_id=decision.decision_id, experiments=tuple(records))


class VerifiedResearchDecisionLedger:
    """Decision-ledger decorator that admits only intact, successful experiment evidence."""

    def __init__(
        self,
        ledger: FileResearchDecisionLedger,
        experiment_store: ManifestStore,
    ) -> None:
        self._ledger = ledger
        self._experiment_store = experiment_store

    def append(self, decision: ResearchDecision) -> str:
        """Verify cited experiment evidence before delegating the append-only ledger write."""

        audit_decision_evidence(self._experiment_store, decision).require_verified()
        return self._ledger.append(decision)

    def read(self, decision_id: str) -> ResearchDecision:
        """Delegate checksum-verified decision reads to the authoritative ledger."""

        return self._ledger.read(decision_id)

    def history(self, subject_id: str) -> tuple[ResearchDecision, ...]:
        """Delegate subject history reconstruction to the authoritative ledger."""

        return self._ledger.history(subject_id)

    def current(self, subject_id: str) -> ResearchDecision | None:
        """Delegate current-decision lookup to the authoritative ledger."""

        return self._ledger.current(subject_id)
