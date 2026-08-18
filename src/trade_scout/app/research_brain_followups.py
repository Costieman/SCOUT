"""Governed follow-up proposals derived from Research Brain conditioning.

A follow-up proposal is an immutable research plan, not an experiment execution. It freezes the
brain state, conditioning priority, and source experiment that motivated the suggestion. Approval
is recorded separately and still does not run research. A later executor may consume only an
approved, non-stale proposal through the normal governed experiment/validation machinery.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING, cast

from trade_scout.app.research_brain_conditioning import (
    ResearchBrainConditioning,
    build_research_brain_conditioning,
)
from trade_scout.experiments.contracts import ExperimentStatus
from trade_scout.experiments.serialization import canonical_json, sha256_json

if TYPE_CHECKING:
    from trade_scout.app.experiment_library_service import ExperimentLibraryDetail
    from trade_scout.app.research_brain_service import ResearchBrainView


class ResearchBrainFollowUpError(RuntimeError):
    """Raised when a follow-up proposal or approval cannot be safely used."""


class FollowUpKind(StrEnum):
    """Research challenge represented by one proposal."""

    COMPARATOR = "COMPARATOR"
    UNCERTAINTY = "UNCERTAINTY"
    PARAMETER_STABILITY = "PARAMETER_STABILITY"
    MULTIPLICITY = "MULTIPLICITY"
    OUT_OF_SAMPLE = "OUT_OF_SAMPLE"
    TIME_STABILITY = "TIME_STABILITY"
    FORMAL_VALIDATION_REVIEW = "FORMAL_VALIDATION_REVIEW"


class FollowUpReadiness(StrEnum):
    """Whether the proposal can be executed without another scientific design choice."""

    READY_TO_PLAN = "READY_TO_PLAN"
    OPERATOR_INPUT_REQUIRED = "OPERATOR_INPUT_REQUIRED"
    GOVERNED_REVIEW_REQUIRED = "GOVERNED_REVIEW_REQUIRED"


@dataclass(frozen=True, slots=True)
class FollowUpMembershipFingerprint:
    """Exact brain membership state on which a follow-up was based."""

    experiment_id: str
    membership_checksum: str
    experiment_manifest_checksum: str


@dataclass(frozen=True, slots=True)
class ResearchBrainFollowUpProposal:
    """Immutable proposal for the next evidence challenge in one research brain."""

    proposal_id: str
    brain_id: str
    created_at: str
    created_by: str
    brain_definition_checksum: str
    memberships: tuple[FollowUpMembershipFingerprint, ...]
    conditioning_version: str
    priority_key: str | None
    kind: FollowUpKind
    title: str
    hypothesis: str
    source_experiment_id: str
    source_experiment_manifest_checksum: str
    source_resolved_configuration_checksum: str
    frozen_elements: tuple[str, ...]
    proposed_change: str
    required_operator_inputs: tuple[str, ...]
    readiness: FollowUpReadiness
    rationale: str
    execution_boundary: str = (
        "This proposal does not execute research. Approval records consent to the research plan only; "
        "execution must occur later through a governed experiment or validation workflow."
    )
    version: str = "research-brain-follow-up-proposal-v0.1"

    def __post_init__(self) -> None:
        _safe_identifier(self.proposal_id, "proposal_id")
        _safe_identifier(self.brain_id, "brain_id")
        _safe_identifier(self.source_experiment_id, "source_experiment_id")
        _aware_timestamp(self.created_at, "created_at")
        for field, value in (
            ("created_by", self.created_by),
            ("brain_definition_checksum", self.brain_definition_checksum),
            ("conditioning_version", self.conditioning_version),
            ("title", self.title),
            ("hypothesis", self.hypothesis),
            ("source_experiment_manifest_checksum", self.source_experiment_manifest_checksum),
            ("source_resolved_configuration_checksum", self.source_resolved_configuration_checksum),
            ("proposed_change", self.proposed_change),
            ("rationale", self.rationale),
            ("execution_boundary", self.execution_boundary),
        ):
            if not value.strip():
                raise ValueError(f"{field} must be non-empty")
        ids = tuple(item.experiment_id for item in self.memberships)
        if len(ids) != len(set(ids)):
            raise ValueError("follow-up proposal memberships must be unique")


@dataclass(frozen=True, slots=True)
class ResearchBrainFollowUpApproval:
    """Append-only human approval for one exact immutable follow-up proposal."""

    approval_id: str
    brain_id: str
    proposal_id: str
    proposal_checksum: str
    approved_at: str
    approved_by: str
    note: str = ""
    version: str = "research-brain-follow-up-approval-v0.1"

    def __post_init__(self) -> None:
        _safe_identifier(self.approval_id, "approval_id")
        _safe_identifier(self.brain_id, "brain_id")
        _safe_identifier(self.proposal_id, "proposal_id")
        if not self.proposal_checksum.strip():
            raise ValueError("proposal_checksum must be non-empty")
        if not self.approved_by.strip():
            raise ValueError("approved_by must be non-empty")
        _aware_timestamp(self.approved_at, "approved_at")


@dataclass(frozen=True, slots=True)
class ResearchBrainFollowUpView:
    """One proposal with its approval state and current-staleness check."""

    proposal: ResearchBrainFollowUpProposal
    approval: ResearchBrainFollowUpApproval | None
    stale: bool

    @property
    def status(self) -> str:
        """Return a user-facing lifecycle label without implying execution."""

        if self.stale:
            return "STALE"
        if self.approval is not None:
            return "APPROVED_NOT_RUN"
        return "DRAFT"


class FileResearchBrainFollowUpStore:
    """Append-only checksum-verified proposal and approval store."""

    def __init__(self, brain_root: Path) -> None:
        self._brain_root = brain_root

    def create_proposal(
        self,
        view: ResearchBrainView,
        *,
        created_by: str,
        created_at: datetime | None = None,
    ) -> ResearchBrainFollowUpProposal:
        """Create or reuse the deterministic proposal for the brain's current evidence state."""

        conditioning = build_research_brain_conditioning(view)
        source = _source_experiment(view)
        if source is None:
            raise ResearchBrainFollowUpError(
                "a follow-up experiment proposal requires at least one readable successful experiment"
            )
        plan = _proposal_plan(conditioning, source)
        timestamp = created_at or datetime.now(UTC)
        if timestamp.tzinfo is None or timestamp.utcoffset() is None:
            raise ValueError("created_at must be timezone-aware")
        actor = created_by.strip()
        if not actor:
            raise ValueError("created_by must be non-empty")
        memberships = tuple(_membership_fingerprint(item.membership) for item in view.experiments)
        definition_checksum = sha256_json(view.snapshot.definition)
        source_manifest = source.manifest
        source_manifest_checksum = source_manifest.manifest_checksum
        if source_manifest_checksum is None:
            raise ResearchBrainFollowUpError("source experiment has no verified manifest checksum")
        basis = {
            "brain_id": view.snapshot.definition.brain_id,
            "brain_definition_checksum": definition_checksum,
            "memberships": memberships,
            "conditioning_version": conditioning.version,
            "priority_key": conditioning.priority_key,
            "source_experiment_id": source_manifest.experiment_id,
            "source_experiment_manifest_checksum": source_manifest_checksum,
            "kind": plan.kind.value,
            "proposed_change": plan.proposed_change,
        }
        proposal_id = "brainproposal_" + sha256_json(basis)[:24]
        path = self._proposal_path(view.snapshot.definition.brain_id, proposal_id)
        if path.exists():
            return self.read_proposal(view.snapshot.definition.brain_id, proposal_id)
        proposal = ResearchBrainFollowUpProposal(
            proposal_id=proposal_id,
            brain_id=view.snapshot.definition.brain_id,
            created_at=timestamp.astimezone(UTC).isoformat(),
            created_by=actor,
            brain_definition_checksum=definition_checksum,
            memberships=memberships,
            conditioning_version=conditioning.version,
            priority_key=conditioning.priority_key,
            kind=plan.kind,
            title=plan.title,
            hypothesis=plan.hypothesis,
            source_experiment_id=source_manifest.experiment_id,
            source_experiment_manifest_checksum=source_manifest_checksum,
            source_resolved_configuration_checksum=sha256_json(
                source_manifest.definition.resolved_configuration
            ),
            frozen_elements=plan.frozen_elements,
            proposed_change=plan.proposed_change,
            required_operator_inputs=plan.required_operator_inputs,
            readiness=plan.readiness,
            rationale=plan.rationale,
        )
        path.parent.mkdir(parents=True, exist_ok=True)
        _atomic_json(path, {"proposal": proposal, "checksum": sha256_json(proposal)})
        return proposal

    def approve(
        self,
        view: ResearchBrainView,
        proposal_id: str,
        *,
        approved_by: str,
        note: str = "",
        approved_at: datetime | None = None,
    ) -> ResearchBrainFollowUpApproval:
        """Approve one exact non-stale proposal without executing it."""

        proposal = self.read_proposal(view.snapshot.definition.brain_id, proposal_id)
        if not self.matches_current_state(proposal, view):
            raise ResearchBrainFollowUpError(
                "the proposal is stale because the brain evidence changed; draft a new proposal first"
            )
        path = self._approval_path(proposal.brain_id, proposal.proposal_id)
        if path.exists():
            raise ResearchBrainFollowUpError("this follow-up proposal has already been approved")
        timestamp = approved_at or datetime.now(UTC)
        if timestamp.tzinfo is None or timestamp.utcoffset() is None:
            raise ValueError("approved_at must be timezone-aware")
        actor = approved_by.strip()
        if not actor:
            raise ValueError("approved_by must be non-empty")
        approval = ResearchBrainFollowUpApproval(
            approval_id="brainapproval_" + proposal.proposal_id.removeprefix("brainproposal_"),
            brain_id=proposal.brain_id,
            proposal_id=proposal.proposal_id,
            proposal_checksum=sha256_json(proposal),
            approved_at=timestamp.astimezone(UTC).isoformat(),
            approved_by=actor,
            note=note.strip(),
        )
        path.parent.mkdir(parents=True, exist_ok=True)
        _atomic_json(path, {"approval": approval, "checksum": sha256_json(approval)})
        return approval

    def list(self, view: ResearchBrainView) -> tuple[ResearchBrainFollowUpView, ...]:
        """Return every verified proposal with approval and current-state status."""

        root = self._brain_root / view.snapshot.definition.brain_id / "proposals"
        if not root.exists():
            return ()
        items: list[ResearchBrainFollowUpView] = []
        for path in sorted(root.glob("*.json")):
            proposal = self.read_proposal(view.snapshot.definition.brain_id, path.stem)
            approval = self.read_approval_optional(proposal.brain_id, proposal.proposal_id)
            items.append(
                ResearchBrainFollowUpView(
                    proposal=proposal,
                    approval=approval,
                    stale=not self.matches_current_state(proposal, view),
                )
            )
        return tuple(
            sorted(items, key=lambda item: (item.proposal.created_at, item.proposal.proposal_id))
        )

    def read_proposal(self, brain_id: str, proposal_id: str) -> ResearchBrainFollowUpProposal:
        """Read and verify one immutable proposal."""

        path = self._proposal_path(brain_id, proposal_id)
        try:
            raw = cast(dict[str, object], json.loads(path.read_text(encoding="utf-8")))
            payload = cast(dict[str, object], raw["proposal"])
            expected = str(raw["checksum"])
        except (OSError, KeyError, TypeError, json.JSONDecodeError) as exc:
            raise ResearchBrainFollowUpError(
                f"cannot read research brain follow-up proposal: {brain_id}/{proposal_id}"
            ) from exc
        proposal = _proposal_from_mapping(payload)
        if proposal.brain_id != brain_id or proposal.proposal_id != proposal_id:
            raise ResearchBrainFollowUpError("research brain follow-up proposal identity mismatch")
        if sha256_json(proposal) != expected:
            raise ResearchBrainFollowUpError(
                f"research brain follow-up proposal checksum mismatch: {brain_id}/{proposal_id}"
            )
        return proposal

    def read_approval_optional(
        self,
        brain_id: str,
        proposal_id: str,
    ) -> ResearchBrainFollowUpApproval | None:
        """Return a verified approval when present."""

        path = self._approval_path(brain_id, proposal_id)
        if not path.exists():
            return None
        try:
            raw = cast(dict[str, object], json.loads(path.read_text(encoding="utf-8")))
            payload = cast(dict[str, object], raw["approval"])
            expected = str(raw["checksum"])
        except (OSError, KeyError, TypeError, json.JSONDecodeError) as exc:
            raise ResearchBrainFollowUpError(
                f"cannot read research brain follow-up approval: {brain_id}/{proposal_id}"
            ) from exc
        approval = _approval_from_mapping(payload)
        if approval.brain_id != brain_id or approval.proposal_id != proposal_id:
            raise ResearchBrainFollowUpError("research brain follow-up approval identity mismatch")
        if sha256_json(approval) != expected:
            raise ResearchBrainFollowUpError(
                f"research brain follow-up approval checksum mismatch: {brain_id}/{proposal_id}"
            )
        proposal = self.read_proposal(brain_id, proposal_id)
        if approval.proposal_checksum != sha256_json(proposal):
            raise ResearchBrainFollowUpError(
                "approval does not bind the current immutable proposal"
            )
        return approval

    def matches_current_state(
        self,
        proposal: ResearchBrainFollowUpProposal,
        view: ResearchBrainView,
    ) -> bool:
        """Return whether the proposal still matches the brain definition and membership history."""

        if proposal.brain_id != view.snapshot.definition.brain_id:
            return False
        if proposal.brain_definition_checksum != sha256_json(view.snapshot.definition):
            return False
        current = tuple(_membership_fingerprint(item.membership) for item in view.experiments)
        return current == proposal.memberships

    def _proposal_path(self, brain_id: str, proposal_id: str) -> Path:
        _safe_identifier(brain_id, "brain_id")
        _safe_identifier(proposal_id, "proposal_id")
        return self._brain_root / brain_id / "proposals" / f"{proposal_id}.json"

    def _approval_path(self, brain_id: str, proposal_id: str) -> Path:
        _safe_identifier(brain_id, "brain_id")
        _safe_identifier(proposal_id, "proposal_id")
        return self._brain_root / brain_id / "proposal-approvals" / f"{proposal_id}.json"


@dataclass(frozen=True, slots=True)
class _ProposalPlan:
    kind: FollowUpKind
    title: str
    hypothesis: str
    frozen_elements: tuple[str, ...]
    proposed_change: str
    required_operator_inputs: tuple[str, ...]
    readiness: FollowUpReadiness
    rationale: str


def _proposal_plan(
    conditioning: ResearchBrainConditioning,
    source: ExperimentLibraryDetail,
) -> _ProposalPlan:
    frozen = (
        "Keep the source experiment's dataset version fixed.",
        "Keep the source experiment's entry definition and execution convention fixed.",
        "Keep the source experiment's primary holding/outcome definition fixed unless the challenge "
        "explicitly requires a validation-period change.",
        "Do not add unrelated indicators or tune a second parameter family in the same follow-up.",
    )
    key = conditioning.priority_key
    if key == "comparator":
        return _ProposalPlan(
            kind=FollowUpKind.COMPARATOR,
            title="Add a predeclared comparator before tuning further",
            hypothesis=(
                "The frozen source configuration adds information beyond an appropriate predeclared "
                "comparison population under the same outcome convention."
            ),
            frozen_elements=frozen,
            proposed_change=(
                "Add one explicit comparator/control to the frozen source research question and measure "
                "the paired or otherwise appropriate effect versus that comparator."
            ),
            required_operator_inputs=(
                "Choose the comparator definition before execution; SCOUT must not select the most "
                "favorable control after seeing the result.",
            ),
            readiness=FollowUpReadiness.OPERATOR_INPUT_REQUIRED,
            rationale=conditioning.priority_action,
        )
    if key == "uncertainty":
        return _ProposalPlan(
            kind=FollowUpKind.UNCERTAINTY,
            title="Add uncertainty to the frozen source result",
            hypothesis=(
                "The apparent effect remains economically interpretable once uncertainty and dependence "
                "are reported for the frozen source definition."
            ),
            frozen_elements=frozen,
            proposed_change=(
                "Estimate uncertainty for the frozen source result without changing the entry rule, "
                "holding definition, or parameter search."
            ),
            required_operator_inputs=(
                "Choose the approved uncertainty/dependence method if the research family does not "
                "already prescribe one.",
            ),
            readiness=FollowUpReadiness.OPERATOR_INPUT_REQUIRED,
            rationale=conditioning.priority_action,
        )
    if key == "parameter_stability":
        neighborhood = _existing_peak_neighborhood(source)
        return _ProposalPlan(
            kind=FollowUpKind.PARAMETER_STABILITY,
            title="Challenge the existing parameter neighborhood",
            hypothesis=(
                "The apparent effect is supported by neighboring already-declared parameter values rather "
                "than a single isolated historical maximum."
            ),
            frozen_elements=frozen,
            proposed_change=(
                "Use the existing declared sweep neighborhood as the stability challenge; do not add a "
                "new wider search merely to find a better peak."
                + (f" Existing peak neighborhood: {neighborhood}." if neighborhood else "")
            ),
            required_operator_inputs=(),
            readiness=FollowUpReadiness.READY_TO_PLAN,
            rationale=conditioning.priority_action,
        )
    if key == "search_burden":
        return _ProposalPlan(
            kind=FollowUpKind.MULTIPLICITY,
            title="Register the searched family before making a formal claim",
            hypothesis=(
                "Any apparent effect remains interpretable after the complete tested hypothesis family is "
                "accounted for rather than treating the historical peak as an isolated test."
            ),
            frozen_elements=frozen,
            proposed_change=(
                "Register the complete tested family and apply an appropriate multiplicity/search "
                "adjustment to the already-preserved cells."
            ),
            required_operator_inputs=(
                "Declare the hypothesis family and correction method before formal inference.",
            ),
            readiness=FollowUpReadiness.OPERATOR_INPUT_REQUIRED,
            rationale=conditioning.priority_action,
        )
    if key == "out_of_sample":
        return _ProposalPlan(
            kind=FollowUpKind.OUT_OF_SAMPLE,
            title="Freeze the definition for unseen-data testing",
            hypothesis=(
                "The frozen source relationship retains useful direction and magnitude on data that was "
                "not used to choose the configuration."
            ),
            frozen_elements=frozen,
            proposed_change=(
                "Freeze the source definition and evaluate it on a genuinely unseen time interval without "
                "retuning from the holdout result."
            ),
            required_operator_inputs=(
                "Define and freeze the unseen validation interval before execution.",
            ),
            readiness=FollowUpReadiness.OPERATOR_INPUT_REQUIRED,
            rationale=conditioning.priority_action,
        )
    if key == "time_stability":
        return _ProposalPlan(
            kind=FollowUpKind.TIME_STABILITY,
            title="Test the frozen relationship through time",
            hypothesis=(
                "The frozen relationship is not concentrated in one historical period and behaves "
                "consistently enough across predeclared time-ordered folds to merit further study."
            ),
            frozen_elements=frozen,
            proposed_change=(
                "Run a predeclared time-ordered/walk-forward stability challenge using the frozen source "
                "definition."
            ),
            required_operator_inputs=("Define the walk-forward/fold schedule before execution.",),
            readiness=FollowUpReadiness.OPERATOR_INPUT_REQUIRED,
            rationale=conditioning.priority_action,
        )
    return _ProposalPlan(
        kind=FollowUpKind.FORMAL_VALIDATION_REVIEW,
        title="Review whether the compact hypothesis is ready for governed validation",
        hypothesis=(
            "The accumulated evidence is sufficiently specified to justify freezing a compact candidate "
            "for the formal validation workflow without further exploratory tuning."
        ),
        frozen_elements=frozen,
        proposed_change=(
            "Do not add another exploratory variable by default. Review the current evidence package and "
            "decide whether to freeze a candidate, retain for study, or reject."
        ),
        required_operator_inputs=(
            "Make an explicit research-governance decision; conditioning does not infer candidate status.",
        ),
        readiness=FollowUpReadiness.GOVERNED_REVIEW_REQUIRED,
        rationale=conditioning.priority_action,
    )


def _source_experiment(view: ResearchBrainView) -> ExperimentLibraryDetail | None:
    for item in reversed(view.experiments):
        if item.integrity_error is not None or item.experiment is None:
            continue
        if item.experiment.manifest.status is ExperimentStatus.SUCCEEDED:
            return item.experiment
    return None


def _existing_peak_neighborhood(detail: ExperimentLibraryDetail) -> str:
    payload = dict(detail.stage_outputs).get("strategy_builder_entry_sweep")
    if not isinstance(payload, dict):
        return ""
    raw_points = payload.get("points")
    if not isinstance(raw_points, list):
        return ""
    points: list[tuple[float, float]] = []
    for item in raw_points:
        if not isinstance(item, dict):
            continue
        raw_value = item.get("parameter_value") if "parameter_value" in item else item.get("value")
        expectancy = item.get("expectancy_return")
        if (
            isinstance(raw_value, int | float)
            and not isinstance(raw_value, bool)
            and isinstance(expectancy, int | float)
            and not isinstance(expectancy, bool)
        ):
            points.append((float(raw_value), float(expectancy)))
    if not points:
        return ""
    points.sort(key=lambda item: item[0])
    index = max(range(len(points)), key=lambda item: points[item][1])
    selected = points[max(0, index - 1) : min(len(points), index + 2)]
    return ", ".join(f"{value:g} ({expectancy * 100:+.2f}%)" for value, expectancy in selected)


def _membership_fingerprint(membership: object) -> FollowUpMembershipFingerprint:
    from trade_scout.experiments.research_brains import BrainExperimentMembership

    if not isinstance(membership, BrainExperimentMembership):
        raise TypeError("unexpected research-brain membership")
    return FollowUpMembershipFingerprint(
        experiment_id=membership.experiment_id,
        membership_checksum=sha256_json(membership),
        experiment_manifest_checksum=membership.experiment_manifest_checksum,
    )


def _proposal_from_mapping(raw: dict[str, object]) -> ResearchBrainFollowUpProposal:
    memberships = tuple(
        FollowUpMembershipFingerprint(
            experiment_id=str(item["experiment_id"]),
            membership_checksum=str(item["membership_checksum"]),
            experiment_manifest_checksum=str(item["experiment_manifest_checksum"]),
        )
        for item in cast(list[dict[str, object]], raw.get("memberships", []))
    )
    return ResearchBrainFollowUpProposal(
        proposal_id=str(raw["proposal_id"]),
        brain_id=str(raw["brain_id"]),
        created_at=str(raw["created_at"]),
        created_by=str(raw["created_by"]),
        brain_definition_checksum=str(raw["brain_definition_checksum"]),
        memberships=memberships,
        conditioning_version=str(raw["conditioning_version"]),
        priority_key=_optional_text(raw.get("priority_key")),
        kind=FollowUpKind(str(raw["kind"])),
        title=str(raw["title"]),
        hypothesis=str(raw["hypothesis"]),
        source_experiment_id=str(raw["source_experiment_id"]),
        source_experiment_manifest_checksum=str(raw["source_experiment_manifest_checksum"]),
        source_resolved_configuration_checksum=str(raw["source_resolved_configuration_checksum"]),
        frozen_elements=tuple(
            str(item) for item in cast(list[object], raw.get("frozen_elements", []))
        ),
        proposed_change=str(raw["proposed_change"]),
        required_operator_inputs=tuple(
            str(item) for item in cast(list[object], raw.get("required_operator_inputs", []))
        ),
        readiness=FollowUpReadiness(str(raw["readiness"])),
        rationale=str(raw["rationale"]),
        execution_boundary=str(
            raw.get(
                "execution_boundary",
                "This proposal does not execute research. Approval records consent only.",
            )
        ),
        version=str(raw.get("version", "research-brain-follow-up-proposal-v0.1")),
    )


def _approval_from_mapping(raw: dict[str, object]) -> ResearchBrainFollowUpApproval:
    return ResearchBrainFollowUpApproval(
        approval_id=str(raw["approval_id"]),
        brain_id=str(raw["brain_id"]),
        proposal_id=str(raw["proposal_id"]),
        proposal_checksum=str(raw["proposal_checksum"]),
        approved_at=str(raw["approved_at"]),
        approved_by=str(raw["approved_by"]),
        note=str(raw.get("note", "")),
        version=str(raw.get("version", "research-brain-follow-up-approval-v0.1")),
    )


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    resolved = str(value).strip()
    return resolved or None


def _safe_identifier(value: str, field: str) -> str:
    resolved = value.strip()
    if not resolved or any(character in resolved for character in "/\\"):
        raise ValueError(f"{field} must be a non-empty path-safe identifier")
    return resolved


def _aware_timestamp(value: str, field: str) -> datetime:
    try:
        resolved = datetime.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{field} must be an ISO timestamp") from exc
    if resolved.tzinfo is None or resolved.utcoffset() is None:
        raise ValueError(f"{field} must be timezone-aware")
    return resolved


def _atomic_json(path: Path, payload: object) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(canonical_json(payload) + "\n", encoding="utf-8")
    temporary.replace(path)


__all__ = [
    "FileResearchBrainFollowUpStore",
    "FollowUpKind",
    "FollowUpReadiness",
    "ResearchBrainFollowUpApproval",
    "ResearchBrainFollowUpError",
    "ResearchBrainFollowUpProposal",
    "ResearchBrainFollowUpView",
]
