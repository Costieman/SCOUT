"""Application service joining research-brain membership with experiment-library evidence."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from trade_scout.app.experiment_library_service import (
    ExperimentLibraryDetail,
    ExperimentLibraryService,
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
    """One preserved membership paired with its current checksum-verified experiment evidence."""

    membership: BrainExperimentMembership
    experiment: ExperimentLibraryDetail | None
    integrity_error: str | None


@dataclass(frozen=True, slots=True)
class ResearchBrainView:
    """Presentation-ready brain definition, inventory, and referenced experiments."""

    snapshot: ResearchBrainSnapshot
    experiments: tuple[ResearchBrainExperimentView, ...]


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

    def __init__(self, *, experiment_root: Path, brain_root: Path) -> None:
        self._experiment_root = experiment_root
        self._brain_store = FileResearchBrainStore(brain_root)
        self._experiment_store = FileManifestStore(experiment_root)
        self._experiment_library = ExperimentLibraryService(experiment_root)

    @property
    def brain_root(self) -> Path:
        return self._brain_store._root  # type: ignore[attr-defined]

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
        return tuple(sorted(rows, key=lambda item: (item.definition.name, item.definition.brain_id)))

    def detail(self, brain_id: str) -> ResearchBrainView:
        """Return one brain and verify every referenced experiment against its membership binding."""

        snapshot = self._brain_store.snapshot(brain_id)
        experiments: list[ResearchBrainExperimentView] = []
        for membership in snapshot.memberships:
            try:
                manifest = self._experiment_store.read_manifest(membership.experiment_id)
                self._brain_store.verify_membership_experiment(brain_id, manifest)
                experiment = self._experiment_library.detail(membership.experiment_id)
            except (OSError, ValueError, KeyError, RuntimeError) as exc:
                experiments.append(
                    ResearchBrainExperimentView(
                        membership=membership,
                        experiment=None,
                        integrity_error=f"{type(exc).__name__}: {exc}",
                    )
                )
                continue
            experiments.append(
                ResearchBrainExperimentView(
                    membership=membership,
                    experiment=experiment,
                    integrity_error=None,
                )
            )
        return ResearchBrainView(snapshot=snapshot, experiments=tuple(experiments))

    def create_brain(
        self,
        *,
        brain_id: str,
        name: str,
        research_question: str,
        created_by: str,
        focus_rules: tuple[BrainFocusRule, ...] = (),
        notes: str = "",
        created_at: datetime | None = None,
    ) -> ResearchBrainDefinition:
        """Create an immutable brain definition; GET views never perform this mutation."""

        timestamp = created_at or datetime.now(UTC)
        if timestamp.tzinfo is None or timestamp.utcoffset() is None:
            raise ValueError("created_at must be timezone-aware")
        definition = ResearchBrainDefinition(
            brain_id=brain_id,
            name=name,
            research_question=research_question,
            created_by=created_by,
            created_at=timestamp.astimezone(UTC).isoformat(),
            focus_rules=focus_rules,
            notes=notes,
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
            added_by=added_by,
            note=note,
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
            raise ValueError("focus rules must use one PATH=VALUE expression per line")
        path, raw_value = line.split("=", 1)
        resolved_path = path.strip()
        resolved_value = _scalar(raw_value.strip())
        rules.append(
            BrainFocusRule(
                configuration_path=resolved_path,
                allowed_values=(resolved_value,),
                rationale=f"Declared workbench focus boundary for {resolved_path}.",
            )
        )
    return tuple(rules)


def _scalar(value: str) -> JSONScalar:
    if not value:
        raise ValueError("focus-rule value must be non-empty")
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
