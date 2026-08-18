"""Application service joining research-brain membership with experiment-library evidence."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from trade_scout.app.experiment_library_service import (
    ExperimentLibraryDetail,
    ExperimentLibraryService,
)
from trade_scout.app.research_brain_evidence import (
    BrainExperimentEvidenceCoverage,
    ResearchBrainEvidenceService,
    ResearchBrainEvidenceSummary,
)
from trade_scout.experiments.contracts import ExperimentStatus, JSONScalar
from trade_scout.experiments.research_brains import (
    BrainExperimentMembership,
    BrainFocusRule,
    FileResearchBrainStore,
    ResearchBrainDefinition,
    ResearchBrainSnapshot,
)
from trade_scout.experiments.store import FileManifestStore


@dataclass(frozen=True, slots=True)
class ResearchBrainExperimentView:
    """One preserved membership paired with experiment and governed evidence metadata."""

    membership: BrainExperimentMembership
    experiment: ExperimentLibraryDetail | None
    evidence: BrainExperimentEvidenceCoverage
    integrity_error: str | None


@dataclass(frozen=True, slots=True)
class ResearchBrainView:
    """Presentation-ready brain definition, inventory, evidence coverage, and experiments."""

    snapshot: ResearchBrainSnapshot
    experiments: tuple[ResearchBrainExperimentView, ...]
    evidence_summary: ResearchBrainEvidenceSummary


@dataclass(frozen=True, slots=True)
class ResearchBrainListItem:
    """Compact user-facing brain inventory row."""

    definition: ResearchBrainDefinition
    membership_count: int
    succeeded_count: int
    failed_count: int
    drift_warning_count: int
    unassessed_count: int
    conditioning_readiness: str


class ResearchBrainWorkbenchService:
    """Expose explicit brain mutations while retaining experiment evidence as authority."""

    def __init__(
        self,
        *,
        experiment_root: Path,
        brain_root: Path,
        validation_review_root: Path | None = None,
    ) -> None:
        self._brain_root = brain_root
        self._validation_review_root = validation_review_root or brain_root.parent / "validation-reviews"
        self._brain_store = FileResearchBrainStore(brain_root)
        self._experiment_store = FileManifestStore(experiment_root)
        self._experiment_library = ExperimentLibraryService(experiment_root)
        self._evidence = ResearchBrainEvidenceService(self._validation_review_root)

    @property
    def brain_root(self) -> Path:
        """Return the private brain-store root without reaching into another module's internals."""

        return self._brain_root

    @property
    def validation_review_root(self) -> Path:
        """Return the configured governed validation-review root."""

        return self._validation_review_root

    def list_brains(self) -> tuple[ResearchBrainListItem, ...]:
        """Return all brain definitions with non-scientific inventory counts."""

        rows: list[ResearchBrainListItem] = []
        for definition in self._brain_store.list_brains():
            snapshot = self._brain_store.snapshot(definition.brain_id)
            rows.append(
                ResearchBrainListItem(
                    definition=definition,
                    membership_count=len(snapshot.memberships),
                    succeeded_count=snapshot.succeeded_count,
                    failed_count=snapshot.failed_count,
                    drift_warning_count=snapshot.drift_warning_count,
                    unassessed_count=snapshot.unassessed_count,
                    conditioning_readiness=snapshot.conditioning_readiness,
                )
            )
        return tuple(
            sorted(rows, key=lambda item: (item.definition.name, item.definition.brain_id))
        )

    def detail(self, brain_id: str) -> ResearchBrainView:
        """Return one brain and verify experiment bindings plus governed evidence coverage."""

        snapshot = self._brain_store.snapshot(brain_id)
        experiment_ids = tuple(item.experiment_id for item in snapshot.memberships)
        coverage_by_id = {
            item.experiment_id: item for item in self._evidence.brain_summary(experiment_ids).experiments
        }
        experiments: list[ResearchBrainExperimentView] = []
        for membership in snapshot.memberships:
            coverage = coverage_by_id[membership.experiment_id]
            try:
                manifest = self._experiment_store.read_manifest(membership.experiment_id)
                self._brain_store.verify_membership_experiment(brain_id, manifest)
                experiment = self._experiment_library.detail(membership.experiment_id)
            except (OSError, ValueError, KeyError, RuntimeError) as exc:
                experiments.append(
                    ResearchBrainExperimentView(
                        membership=membership,
                        experiment=None,
                        evidence=coverage,
                        integrity_error=f"{type(exc).__name__}: {exc}",
                    )
                )
                continue
            experiments.append(
                ResearchBrainExperimentView(
                    membership=membership,
                    experiment=experiment,
                    evidence=coverage,
                    integrity_error=None,
                )
            )
        return ResearchBrainView(
            snapshot=snapshot,
            experiments=tuple(experiments),
            evidence_summary=self._evidence.brain_summary(experiment_ids),
        )

    def create_brain(
        self,
        *,
        name: str,
        research_question: str,
        created_by: str,
        brain_id: str | None = None,
        focus_rules: tuple[BrainFocusRule, ...] = (),
        notes: str = "",
        created_at: datetime | None = None,
    ) -> ResearchBrainDefinition:
        """Create an immutable brain definition; GET views never perform this mutation."""

        timestamp = created_at or datetime.now(UTC)
        if timestamp.tzinfo is None or timestamp.utcoffset() is None:
            raise ValueError("created_at must be timezone-aware")
        resolved_name = name.strip()
        if not resolved_name:
            raise ValueError("research brain name must be non-empty")
        resolved_id = brain_id.strip() if brain_id is not None else ""
        if not resolved_id:
            resolved_id = _generated_brain_id(resolved_name)
        definition = ResearchBrainDefinition(
            brain_id=resolved_id,
            name=resolved_name,
            research_question=research_question.strip(),
            created_by=created_by.strip(),
            created_at=timestamp.astimezone(UTC).isoformat(),
            focus_rules=focus_rules,
            notes=notes.strip(),
        )
        self._brain_store.create(definition)
        return definition

    def add_experiment(
        self,
        *,
        brain_id: str,
        experiment_id: str,
        added_by: str,
        note: str = "",
        added_at: datetime | None = None,
    ) -> BrainExperimentMembership:
        """Append one verified terminal experiment to one brain and retain drift warnings."""

        manifest = self._experiment_store.read_manifest(experiment_id)
        if manifest.status not in {ExperimentStatus.SUCCEEDED, ExperimentStatus.FAILED}:
            raise ValueError("only terminal experiments may be assigned to a research brain")
        return self._brain_store.add_experiment(
            brain_id,
            manifest,
            added_by=added_by.strip(),
            note=note.strip(),
            added_at=added_at,
        )


def parse_focus_rules(source: str) -> tuple[BrainFocusRule, ...]:
    """Parse newline-delimited PATH=VALUE focus rules from the local workbench form."""

    rules: list[BrainFocusRule] = []
    for raw_line in source.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if "=" not in line:
            raise ValueError("focus boundaries must use one PATH=VALUE expression per line")
        path, raw_value = line.split("=", 1)
        resolved_path = path.strip()
        if not resolved_path:
            raise ValueError("focus-boundary path must be non-empty")
        resolved_value = _scalar(raw_value.strip())
        rules.append(
            BrainFocusRule(
                configuration_path=resolved_path,
                allowed_values=(resolved_value,),
                rationale=f"Declared workbench focus boundary for {resolved_path}.",
            )
        )
    return tuple(rules)


def _generated_brain_id(name: str) -> str:
    slug = "".join(character.lower() if character.isalnum() else "_" for character in name)
    slug = "_".join(part for part in slug.split("_") if part)[:36] or "research"
    return f"brain_{slug}_{uuid4().hex[:10]}"


def _scalar(value: str) -> JSONScalar:
    if not value:
        raise ValueError("focus-boundary value must be non-empty")
    normalized = value.casefold()
    if normalized == "true":
        return True
    if normalized == "false":
        return False
    if normalized in {"null", "none"}:
        return None
    try:
        return int(value)
    except ValueError:
        pass
    try:
        return float(value)
    except ValueError:
        return value


__all__ = [
    "ResearchBrainExperimentView",
    "ResearchBrainListItem",
    "ResearchBrainView",
    "ResearchBrainWorkbenchService",
    "parse_focus_rules",
]
