"""Read-only Experiment Library over the governed experiment registry and manifests.

The DuckDB registry remains an index. Checksum-verified experiment manifests and stage artifacts
remain authoritative. This service synchronizes any existing manifest directories into the index,
then exposes search, filtering, lineage, detail, and comparison inputs to the application layer.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import cast

from trade_scout.experiments.contracts import (
    ExperimentManifest,
    ExperimentStatus,
    JSONValue,
    ResearchMode,
)
from trade_scout.experiments.registry import (
    DuckDBExperimentRegistry,
    ExperimentIndexRecord,
)
from trade_scout.experiments.store import FileManifestStore


@dataclass(frozen=True, slots=True)
class ExperimentLibraryFilters:
    """Display-only filters applied to the experiment registry."""

    text: str = ""
    status: ExperimentStatus | None = None
    mode: ResearchMode | None = None
    strategy_family: str | None = None
    dataset_version: str | None = None
    code_version: str | None = None
    hypothesis_family_id: str | None = None

    def __post_init__(self) -> None:
        for value in (
            self.strategy_family,
            self.dataset_version,
            self.code_version,
            self.hypothesis_family_id,
        ):
            if value is not None and not value.strip():
                raise ValueError("experiment-library filter text must be non-empty when supplied")


@dataclass(frozen=True, slots=True)
class ExperimentResultSummary:
    """Small result summary extracted from an authoritative stage artifact when available."""

    kind: str
    entry_event_count: int | None = None
    complete_event_count: int | None = None
    hold_expectancy: float | None = None
    sweep_point_count: int | None = None
    sweep_expectancy_low: float | None = None
    sweep_expectancy_high: float | None = None


@dataclass(frozen=True, slots=True)
class ExperimentLibraryItem:
    """One registry row enriched with manifest-backed display metadata."""

    record: ExperimentIndexRecord
    strategy_family: str | None
    stage_count: int
    warning_count: int
    failure_type: str | None
    integrity_error: str | None
    result: ExperimentResultSummary | None


@dataclass(frozen=True, slots=True)
class ExperimentLibraryDetail:
    """Authoritative manifest, outputs, lineage, and children for one experiment."""

    manifest: ExperimentManifest
    stage_outputs: tuple[tuple[str, dict[str, JSONValue]], ...]
    lineage: tuple[ExperimentIndexRecord, ...]
    children: tuple[ExperimentIndexRecord, ...]
    strategy_family: str | None
    result: ExperimentResultSummary | None


@dataclass(frozen=True, slots=True)
class ExperimentLibrarySnapshot:
    """One filtered library view with synchronization warnings retained."""

    items: tuple[ExperimentLibraryItem, ...]
    filters: ExperimentLibraryFilters
    synchronization_warnings: tuple[str, ...]
    indexed_manifest_count: int


class ExperimentLibraryService:
    """Expose the experiment registry without making the UI a system of record."""

    def __init__(self, experiment_root: Path) -> None:
        self._root = experiment_root
        self._store = FileManifestStore(experiment_root)
        self._registry = DuckDBExperimentRegistry(experiment_root / "registry.duckdb")

    @property
    def registry_path(self) -> Path:
        return self._root / "registry.duckdb"

    def snapshot(
        self,
        filters: ExperimentLibraryFilters | None = None,
        *,
        limit: int = 250,
    ) -> ExperimentLibrarySnapshot:
        """Return a newest-first filtered view after indexing verified existing manifests."""

        if not 1 <= limit <= 5000:
            raise ValueError("experiment-library limit must be between 1 and 5000")
        selected = filters or ExperimentLibraryFilters()
        indexed_count, warnings = self._synchronize_registry()
        records = self._registry.query(
            status=selected.status,
            mode=selected.mode,
            hypothesis_family_id=selected.hypothesis_family_id,
            dataset_version=selected.dataset_version,
        )
        items: list[ExperimentLibraryItem] = []
        for record in reversed(records):
            if selected.code_version is not None and record.code_version != selected.code_version:
                continue
            item = self._item(record)
            if (
                selected.strategy_family is not None
                and item.strategy_family != selected.strategy_family
            ):
                continue
            if selected.text.strip() and not _matches_text(item, selected.text):
                continue
            items.append(item)
            if len(items) >= limit:
                break
        return ExperimentLibrarySnapshot(
            items=tuple(items),
            filters=selected,
            synchronization_warnings=warnings,
            indexed_manifest_count=indexed_count,
        )

    def detail(self, experiment_id: str) -> ExperimentLibraryDetail:
        """Load one checksum-verified experiment and every recorded stage artifact."""

        self._synchronize_registry()
        manifest = self._store.read_manifest(_required_id(experiment_id))
        stage_outputs = tuple(
            (stage.stage_name, self._store.read_stage_output(experiment_id, stage.stage_name))
            for stage in manifest.stages
        )
        self._registry.get(experiment_id)
        lineage = self._registry.lineage(experiment_id)
        children = tuple(
            item
            for item in self._registry.query()
            if item.parent_experiment_id == experiment_id or item.reproduction_of == experiment_id
        )
        return ExperimentLibraryDetail(
            manifest=manifest,
            stage_outputs=stage_outputs,
            lineage=lineage,
            children=children,
            strategy_family=_strategy_family(manifest),
            result=_result_summary(stage_outputs),
        )

    def comparison(self, experiment_ids: tuple[str, ...]) -> tuple[ExperimentLibraryDetail, ...]:
        """Load two to four explicitly selected experiments for side-by-side comparison."""

        if not 2 <= len(experiment_ids) <= 4:
            raise ValueError("experiment comparison requires between 2 and 4 experiment IDs")
        if len(set(experiment_ids)) != len(experiment_ids):
            raise ValueError("experiment comparison IDs must be unique")
        return tuple(self.detail(experiment_id) for experiment_id in experiment_ids)

    def strategy_families(self) -> tuple[str, ...]:
        """Return strategy families currently recoverable from verified manifests."""

        self._synchronize_registry()
        families: set[str] = set()
        for record in self._registry.query():
            try:
                family = _strategy_family(self._store.read_manifest(record.experiment_id))
            except (OSError, ValueError, KeyError):
                continue
            if family is not None:
                families.add(family)
        return tuple(sorted(families))

    def _synchronize_registry(self) -> tuple[int, tuple[str, ...]]:
        self._root.mkdir(parents=True, exist_ok=True)
        count = 0
        warnings: list[str] = []
        for path in sorted(self._root.glob("*/manifest.json")):
            experiment_id = path.parent.name
            try:
                manifest = self._store.read_manifest(experiment_id)
                self._registry.register(manifest)
            except (OSError, ValueError, KeyError) as exc:
                warnings.append(f"Could not index {experiment_id}: {type(exc).__name__}: {exc}")
                continue
            count += 1
        return count, tuple(warnings)

    def _item(self, record: ExperimentIndexRecord) -> ExperimentLibraryItem:
        try:
            manifest = self._store.read_manifest(record.experiment_id)
            outputs = tuple(
                (
                    stage.stage_name,
                    self._store.read_stage_output(record.experiment_id, stage.stage_name),
                )
                for stage in manifest.stages
            )
        except (OSError, ValueError, KeyError) as exc:
            return ExperimentLibraryItem(
                record=record,
                strategy_family=None,
                stage_count=0,
                warning_count=0,
                failure_type=None,
                integrity_error=f"{type(exc).__name__}: {exc}",
                result=None,
            )
        return ExperimentLibraryItem(
            record=record,
            strategy_family=_strategy_family(manifest),
            stage_count=len(manifest.stages),
            warning_count=len(manifest.warnings),
            failure_type=manifest.failure_type,
            integrity_error=None,
            result=_result_summary(outputs),
        )


def _strategy_family(manifest: ExperimentManifest) -> str | None:
    configuration = manifest.definition.resolved_configuration
    entry = configuration.get("entry")
    if not isinstance(entry, dict):
        return None
    family = entry.get("family")
    return family.strip() if isinstance(family, str) and family.strip() else None


def _result_summary(
    outputs: tuple[tuple[str, dict[str, JSONValue]], ...],
) -> ExperimentResultSummary | None:
    if not outputs:
        return None
    by_stage = dict(outputs)
    standard = by_stage.get("strategy_builder")
    if standard is not None:
        policies = standard.get("policies")
        return ExperimentResultSummary(
            kind="strategy_builder",
            entry_event_count=_optional_int(standard.get("entry_event_count")),
            complete_event_count=_optional_int(standard.get("complete_event_count")),
            hold_expectancy=_hold_expectancy(policies),
        )
    sweep = by_stage.get("strategy_builder_entry_sweep")
    if sweep is not None:
        points = sweep.get("points")
        resolved_points = cast(list[JSONValue], points) if isinstance(points, list) else []
        expectancies: list[float] = []
        for point in resolved_points:
            if not isinstance(point, dict):
                continue
            value = point.get("expectancy_return")
            if isinstance(value, int | float) and not isinstance(value, bool):
                expectancies.append(float(value))
        return ExperimentResultSummary(
            kind="strategy_builder_entry_sweep",
            sweep_point_count=len(resolved_points),
            sweep_expectancy_low=min(expectancies) if expectancies else None,
            sweep_expectancy_high=max(expectancies) if expectancies else None,
        )
    return ExperimentResultSummary(kind="multi_stage" if len(outputs) > 1 else outputs[0][0])


def _hold_expectancy(value: JSONValue | None) -> float | None:
    if not isinstance(value, list):
        return None
    for item in value:
        if not isinstance(item, dict) or item.get("family") != "hold_to_horizon":
            continue
        expectancy = item.get("expectancy_return")
        if isinstance(expectancy, int | float) and not isinstance(expectancy, bool):
            return float(expectancy)
    return None


def _optional_int(value: JSONValue | None) -> int | None:
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    return None


def _matches_text(item: ExperimentLibraryItem, query: str) -> bool:
    needle = query.casefold().strip()
    record = item.record
    haystack = "\n".join(
        value
        for value in (
            record.experiment_id,
            record.name,
            record.hypothesis,
            item.strategy_family or "",
            record.dataset_version,
            record.code_version,
            record.hypothesis_family_id or "",
        )
        if value
    ).casefold()
    return needle in haystack


def _required_id(value: str) -> str:
    resolved = value.strip()
    if not resolved or any(character in resolved for character in "/\\"):
        raise ValueError("experiment_id must be a non-empty path-safe identifier")
    return resolved


__all__ = [
    "ExperimentLibraryDetail",
    "ExperimentLibraryFilters",
    "ExperimentLibraryItem",
    "ExperimentLibraryService",
    "ExperimentLibrarySnapshot",
    "ExperimentResultSummary",
]
