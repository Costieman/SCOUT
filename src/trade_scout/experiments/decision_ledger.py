"""Append-only filesystem ledger for explicit research decisions."""

from __future__ import annotations

import json
from pathlib import Path
from typing import cast

from trade_scout.experiments.decisions import (
    ProductionEligibilityAttestation,
    ResearchDecision,
    ResearchDecisionError,
    ResearchDecisionState,
    validate_decision_supersession,
)
from trade_scout.experiments.serialization import canonical_json, sha256_json


class FileResearchDecisionLedger:
    """Persist immutable research decisions without silently rewriting earlier conclusions."""

    def __init__(self, root: Path) -> None:
        self._root = root

    def append(self, decision: ResearchDecision) -> str:
        """Validate decision lineage, persist once, and return its deterministic checksum."""

        self._root.mkdir(parents=True, exist_ok=True)
        path = self._path(decision.decision_id)
        if path.exists():
            raise ResearchDecisionError(f"decision already exists: {decision.decision_id}")

        prior = self.current(decision.subject_id)
        validate_decision_supersession(decision, prior)
        checksum = sha256_json(decision)
        envelope = {"decision": decision, "checksum": checksum}
        temporary = path.with_suffix(".json.tmp")
        temporary.write_text(canonical_json(envelope) + "\n", encoding="utf-8")
        temporary.replace(path)
        return checksum

    def read(self, decision_id: str) -> ResearchDecision:
        """Read one immutable decision and verify its checksum."""

        raw = cast(
            dict[str, object], json.loads(self._path(decision_id).read_text(encoding="utf-8"))
        )
        decision_raw = cast(dict[str, object], raw["decision"])
        decision = _decision_from_mapping(decision_raw)
        expected = str(raw["checksum"])
        actual = sha256_json(decision)
        if actual != expected:
            raise ResearchDecisionError(f"decision checksum mismatch: {decision_id}")
        if decision.decision_id != decision_id:
            raise ResearchDecisionError(
                f"decision file identity mismatch: expected {decision_id}, got {decision.decision_id}"
            )
        return decision

    def history(self, subject_id: str) -> tuple[ResearchDecision, ...]:
        """Return the complete supersession chain for one analytical subject."""

        if not subject_id.strip():
            raise ValueError("subject_id must be non-empty")
        decisions = tuple(
            decision for decision in self._all_verified() if decision.subject_id == subject_id
        )
        if not decisions:
            return ()

        by_id = {decision.decision_id: decision for decision in decisions}
        superseded_ids = {
            decision.supersedes_decision_id
            for decision in decisions
            if decision.supersedes_decision_id is not None
        }
        roots = [decision for decision in decisions if decision.supersedes_decision_id is None]
        currents = [
            decision for decision in decisions if decision.decision_id not in superseded_ids
        ]
        if len(roots) != 1 or len(currents) != 1:
            raise ResearchDecisionError(f"invalid decision lineage for subject {subject_id}")

        ordered: list[ResearchDecision] = [roots[0]]
        while ordered[-1].decision_id != currents[0].decision_id:
            children = [
                decision
                for decision in decisions
                if decision.supersedes_decision_id == ordered[-1].decision_id
            ]
            if len(children) != 1:
                raise ResearchDecisionError(f"invalid decision lineage for subject {subject_id}")
            ordered.append(children[0])
        if len(ordered) != len(by_id):
            raise ResearchDecisionError(f"disconnected decision lineage for subject {subject_id}")
        return tuple(ordered)

    def current(self, subject_id: str) -> ResearchDecision | None:
        """Return the current explicit decision for a subject, if any."""

        history = self.history(subject_id)
        return history[-1] if history else None

    def _all_verified(self) -> tuple[ResearchDecision, ...]:
        if not self._root.exists():
            return ()
        return tuple(self.read(path.stem) for path in sorted(self._root.glob("*.json")))

    def _path(self, decision_id: str) -> Path:
        if not decision_id or any(character in decision_id for character in "/\\"):
            raise ValueError("decision_id must be a non-empty path-safe identifier")
        return self._root / f"{decision_id}.json"


def _decision_from_mapping(raw: dict[str, object]) -> ResearchDecision:
    attestation_raw = raw.get("production_attestation")
    attestation = None
    if attestation_raw is not None:
        values = cast(dict[str, object], attestation_raw)
        attestation = ProductionEligibilityAttestation(
            implementation_compatible=bool(values["implementation_compatible"]),
            cost_assumptions_acceptable=bool(values["cost_assumptions_acceptable"]),
            liquidity_assumptions_acceptable=bool(values["liquidity_assumptions_acceptable"]),
            risk_policy_validated=bool(values["risk_policy_validated"]),
            operational_dependencies_available=bool(values["operational_dependencies_available"]),
        )
    return ResearchDecision(
        decision_id=str(raw["decision_id"]),
        subject_id=str(raw["subject_id"]),
        state=ResearchDecisionState(str(raw["state"])),
        experiment_ids=tuple(str(item) for item in cast(list[object], raw["experiment_ids"])),
        evidence_references=tuple(
            str(item) for item in cast(list[object], raw["evidence_references"])
        ),
        rationale=str(raw["rationale"]),
        decided_by=str(raw["decided_by"]),
        decided_at=str(raw["decided_at"]),
        supersedes_decision_id=_optional_string(raw.get("supersedes_decision_id")),
        production_attestation=attestation,
    )


def _optional_string(value: object) -> str | None:
    return None if value is None else str(value)
