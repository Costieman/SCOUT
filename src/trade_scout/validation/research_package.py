"""Canonical research evidence package for completed Trade Scout experiments.

The validation layer already stores typed statistical evidence and complete validation-review
bundles. This module assembles those records with immutable experiment provenance and an optional
explicit research decision into one deterministic reporting artifact. It does not calculate missing
statistics, infer promotion, or convert exploratory evidence into confirmatory evidence.
"""

from __future__ import annotations

from dataclasses import dataclass

from trade_scout.experiments.contracts import (
    ExperimentManifest,
    ExperimentStatus,
    ResearchMode,
)
from trade_scout.experiments.decisions import ResearchDecision, ResearchDecisionState
from trade_scout.experiments.serialization import sha256_json
from trade_scout.validation.contracts import SampleAccounting
from trade_scout.validation.evidence import (
    EffectEstimate,
    EvidenceRole,
    EvidenceSnapshot,
    MetricEstimate,
)
from trade_scout.validation.reporting import (
    MultiplicitySummary,
    ValidationReviewBundle,
    ValidationRoleCount,
)

RESEARCH_EVIDENCE_PACKAGE_VERSION = "research-evidence-package-v0.1"


@dataclass(frozen=True, slots=True)
class MetricFamilyRequirement:
    """Minimum reporting coverage for a family of named scalar metrics."""

    prefix: str
    minimum_count: int

    def __post_init__(self) -> None:
        if not self.prefix.strip():
            raise ValueError("metric-family prefix must be non-empty")
        if self.minimum_count < 1:
            raise ValueError("metric-family minimum_count must be positive")


@dataclass(frozen=True, slots=True)
class ResearchEvidenceReportingProfile:
    """Explicit completeness standard applied when an evidence package is assembled."""

    profile_id: str
    required_primary_metrics: tuple[str, ...]
    required_metric_families: tuple[MetricFamilyRequirement, ...]
    metrics_requiring_interval: tuple[str, ...]
    required_roles: tuple[EvidenceRole, ...] = ()
    require_comparator_effect: bool = True
    require_comparator_interval: bool = False

    def __post_init__(self) -> None:
        if not self.profile_id.strip():
            raise ValueError("research evidence reporting profile_id must be non-empty")
        named = (*self.required_primary_metrics, *self.metrics_requiring_interval)
        if any(not name.strip() for name in named):
            raise ValueError("research evidence metric names must be non-empty")
        if len(set(self.required_primary_metrics)) != len(self.required_primary_metrics):
            raise ValueError("required primary metric names must be unique")
        if len(set(self.metrics_requiring_interval)) != len(self.metrics_requiring_interval):
            raise ValueError("interval-required metric names must be unique")
        if len(set(self.required_roles)) != len(self.required_roles):
            raise ValueError("required evidence roles must be unique")
        prefixes = tuple(item.prefix for item in self.required_metric_families)
        if len(set(prefixes)) != len(prefixes):
            raise ValueError("metric-family prefixes must be unique")


def canonical_research_reporting_profile(
    *,
    required_roles: tuple[EvidenceRole, ...] = (),
) -> ResearchEvidenceReportingProfile:
    """Return the Version 0.1 statistical-reporting standard from the research specifications.

    Exact quantile probabilities are intentionally not dictated here. Instead the profile requires
    multiple return, MAE, and MFE quantiles while preserving their explicitly named probabilities in
    the evidence producer. This avoids inventing thresholds that the research specifications do not
    prescribe.
    """

    return ResearchEvidenceReportingProfile(
        profile_id="first-program-statistical-reporting-v0.1",
        required_primary_metrics=(
            "mean_outcome",
            "median_outcome",
            "win_probability",
            "expectancy",
        ),
        required_metric_families=(
            MetricFamilyRequirement("return_quantile_", 3),
            MetricFamilyRequirement("mae_quantile_", 3),
            MetricFamilyRequirement("mfe_quantile_", 3),
        ),
        metrics_requiring_interval=("win_probability",),
        required_roles=required_roles,
        require_comparator_effect=True,
        require_comparator_interval=False,
    )


@dataclass(frozen=True, slots=True)
class StageArtifactEvidence:
    """Stage output checksum retained in the canonical package provenance section."""

    stage_name: str
    output_checksum: str

    def __post_init__(self) -> None:
        if not self.stage_name.strip() or not self.output_checksum.strip():
            raise ValueError("stage artifact evidence fields must be non-empty")


@dataclass(frozen=True, slots=True)
class ResearchEvidencePackage:
    """One deterministic, reviewable evidence package for a completed experiment.

    The package deliberately preserves evidence records instead of collapsing them into a composite
    score. ``primary_evidence_id`` is selected explicitly by the caller so the reporting layer never
    guesses which validation role or fold should carry the headline sample and metrics.
    """

    package_id: str
    package_checksum: str
    package_version: str
    reporting_profile_id: str
    experiment_id: str
    experiment_name: str
    research_mode: ResearchMode
    hypothesis: str
    hypothesis_family_id: str | None
    parent_experiment_id: str | None
    dataset_version: str
    universe_version: str
    code_version: str
    config_schema_version: str
    configuration_checksum: str
    manifest_checksum: str
    stage_artifacts: tuple[StageArtifactEvidence, ...]
    validation_report_id: str
    validation_plan_id: str
    primary_outcome: str
    primary_evidence_id: str
    primary_sample: SampleAccounting
    primary_metrics: tuple[MetricEstimate, ...]
    primary_effects: tuple[EffectEstimate, ...]
    evidence_snapshots: tuple[EvidenceSnapshot, ...]
    role_counts: tuple[ValidationRoleCount, ...]
    parameter_surface_ids: tuple[str, ...]
    multiplicity: tuple[MultiplicitySummary, ...]
    robustness_plan_id: str | None
    decision: ResearchDecision | None
    notes: tuple[str, ...]
    warnings: tuple[str, ...]

    def __post_init__(self) -> None:
        required = (
            self.package_id,
            self.package_checksum,
            self.package_version,
            self.reporting_profile_id,
            self.experiment_id,
            self.experiment_name,
            self.hypothesis,
            self.dataset_version,
            self.universe_version,
            self.code_version,
            self.config_schema_version,
            self.configuration_checksum,
            self.manifest_checksum,
            self.validation_report_id,
            self.validation_plan_id,
            self.primary_outcome,
            self.primary_evidence_id,
        )
        if any(not value.strip() for value in required):
            raise ValueError("research evidence package required string fields must be non-empty")
        expected_id = f"research_evidence_{self.package_checksum[:20]}"
        if self.package_id != expected_id:
            raise ValueError("research evidence package ID does not match its checksum")
        if not self.primary_metrics:
            raise ValueError("research evidence package requires primary metrics")
        metric_names = tuple(item.metric for item in self.primary_metrics)
        if len(metric_names) != len(set(metric_names)):
            raise ValueError("research evidence primary metric names must be unique")
        if not self.evidence_snapshots:
            raise ValueError("research evidence package requires validation evidence snapshots")
        evidence_ids = tuple(item.evidence_id for item in self.evidence_snapshots)
        if len(evidence_ids) != len(set(evidence_ids)):
            raise ValueError("research evidence snapshot IDs must be unique")
        if self.primary_evidence_id not in set(evidence_ids):
            raise ValueError("primary_evidence_id must reference a packaged evidence snapshot")
        if any(not note.strip() for note in self.notes):
            raise ValueError("research evidence notes must be non-empty")
        if any(not warning.strip() for warning in self.warnings):
            raise ValueError("research evidence warnings must be non-empty")

    @property
    def decision_state(self) -> ResearchDecisionState | None:
        """Return the explicitly recorded decision state, if one exists."""

        return self.decision.state if self.decision is not None else None

    @property
    def walk_forward_snapshots(self) -> tuple[EvidenceSnapshot, ...]:
        """Return time-ordered fold evidence without pooling it implicitly."""

        return tuple(
            item for item in self.evidence_snapshots if item.role is EvidenceRole.WALK_FORWARD
        )

    @property
    def robustness_snapshots(self) -> tuple[EvidenceSnapshot, ...]:
        """Return robustness challenges as separate evidence records."""

        return tuple(item for item in self.evidence_snapshots if item.role is EvidenceRole.ROBUSTNESS)

    @property
    def final_holdout_snapshots(self) -> tuple[EvidenceSnapshot, ...]:
        """Return reserved final-holdout evidence without merging it into development results."""

        return tuple(
            item for item in self.evidence_snapshots if item.role is EvidenceRole.FINAL_HOLDOUT
        )

    def primary_metric(self, metric_name: str) -> MetricEstimate:
        """Return one explicitly named primary metric or fail instead of substituting a proxy."""

        for metric in self.primary_metrics:
            if metric.metric == metric_name:
                return metric
        raise KeyError(f"primary metric not present in evidence package: {metric_name}")


@dataclass(frozen=True, slots=True)
class ResearchEvidenceSummary:
    """Compact evidence inventory suitable for experiment-library and results-overview surfaces."""

    package_id: str
    experiment_id: str
    experiment_name: str
    research_mode: ResearchMode
    dataset_version: str
    universe_version: str
    primary_outcome: str
    primary_evidence_id: str
    raw_event_count: int
    unique_instrument_count: int
    effective_sample_size: float | None
    cluster_count: int | None
    primary_metric_names: tuple[str, ...]
    comparator_effect_count: int
    validation_snapshot_count: int
    walk_forward_fold_count: int
    robustness_challenge_count: int
    final_holdout_count: int
    multiplicity_family_count: int
    parameter_surface_count: int
    decision_state: ResearchDecisionState | None
    warning_count: int


def build_research_evidence_package(
    *,
    manifest: ExperimentManifest,
    review: ValidationReviewBundle,
    primary_evidence_id: str,
    profile: ResearchEvidenceReportingProfile | None = None,
    decision: ResearchDecision | None = None,
) -> ResearchEvidencePackage:
    """Assemble one canonical package from persisted experiment and validation evidence.

    The builder is fail-closed. It requires a successful checksummed experiment manifest, a complete
    validation-review bundle for that same experiment, explicit primary evidence, and the reporting
    metrics demanded by the selected profile. No metric, comparator, validation role, or research
    decision is inferred from performance.
    """

    if manifest.status is not ExperimentStatus.SUCCEEDED:
        raise ValueError("research evidence package requires a SUCCEEDED experiment manifest")
    if manifest.manifest_checksum is None or not manifest.manifest_checksum.strip():
        raise ValueError("research evidence package requires a checksummed experiment manifest")
    if review.report.experiment_id != manifest.experiment_id:
        raise ValueError("validation report and experiment manifest reference different experiments")

    primary = _primary_snapshot(review, primary_evidence_id)
    resolved_profile = profile or canonical_research_reporting_profile()
    _validate_profile_coverage(review, primary, resolved_profile)
    _validate_decision(decision, manifest.experiment_id)

    stage_artifacts = tuple(
        StageArtifactEvidence(stage.stage_name, stage.output_checksum) for stage in manifest.stages
    )
    parameter_surface_ids = tuple(
        sorted(surface.surface_id for surface in review.parameter_surfaces)
    )
    notes = tuple(review.report.notes)
    warnings = tuple(
        warning for snapshot in review.report.snapshots for warning in snapshot.warnings
    )
    configuration_checksum = sha256_json(manifest.definition.resolved_configuration)

    payload = {
        "package_version": RESEARCH_EVIDENCE_PACKAGE_VERSION,
        "reporting_profile_id": resolved_profile.profile_id,
        "experiment_id": manifest.experiment_id,
        "experiment_name": manifest.definition.name,
        "research_mode": manifest.definition.mode,
        "hypothesis": manifest.definition.hypothesis,
        "hypothesis_family_id": manifest.definition.hypothesis_family_id,
        "parent_experiment_id": manifest.definition.parent_experiment_id,
        "dataset_version": manifest.definition.dataset_version,
        "universe_version": manifest.definition.universe_version,
        "code_version": manifest.definition.code_version,
        "config_schema_version": manifest.definition.config_schema_version,
        "configuration_checksum": configuration_checksum,
        "manifest_checksum": manifest.manifest_checksum,
        "stage_artifacts": stage_artifacts,
        "validation_report_id": review.report.report_id,
        "validation_plan_id": review.report.validation_plan_id,
        "primary_outcome": review.report.primary_outcome,
        "primary_evidence_id": primary.evidence_id,
        "primary_sample": primary.sample,
        "primary_metrics": primary.metrics,
        "primary_effects": primary.effects,
        "evidence_snapshots": review.report.snapshots,
        "role_counts": review.role_counts,
        "parameter_surface_ids": parameter_surface_ids,
        "multiplicity": review.multiplicity,
        "robustness_plan_id": review.robustness_plan_id,
        "decision": decision,
        "notes": notes,
        "warnings": warnings,
    }
    checksum = sha256_json(payload)
    return ResearchEvidencePackage(
        package_id=f"research_evidence_{checksum[:20]}",
        package_checksum=checksum,
        package_version=RESEARCH_EVIDENCE_PACKAGE_VERSION,
        reporting_profile_id=resolved_profile.profile_id,
        experiment_id=manifest.experiment_id,
        experiment_name=manifest.definition.name,
        research_mode=manifest.definition.mode,
        hypothesis=manifest.definition.hypothesis,
        hypothesis_family_id=manifest.definition.hypothesis_family_id,
        parent_experiment_id=manifest.definition.parent_experiment_id,
        dataset_version=manifest.definition.dataset_version,
        universe_version=manifest.definition.universe_version,
        code_version=manifest.definition.code_version,
        config_schema_version=manifest.definition.config_schema_version,
        configuration_checksum=configuration_checksum,
        manifest_checksum=manifest.manifest_checksum,
        stage_artifacts=stage_artifacts,
        validation_report_id=review.report.report_id,
        validation_plan_id=review.report.validation_plan_id,
        primary_outcome=review.report.primary_outcome,
        primary_evidence_id=primary.evidence_id,
        primary_sample=primary.sample,
        primary_metrics=primary.metrics,
        primary_effects=primary.effects,
        evidence_snapshots=review.report.snapshots,
        role_counts=review.role_counts,
        parameter_surface_ids=parameter_surface_ids,
        multiplicity=review.multiplicity,
        robustness_plan_id=review.robustness_plan_id,
        decision=decision,
        notes=notes,
        warnings=warnings,
    )


def summarize_research_evidence_package(
    package: ResearchEvidencePackage,
) -> ResearchEvidenceSummary:
    """Return a deterministic overview without selecting a best metric or strategy."""

    return ResearchEvidenceSummary(
        package_id=package.package_id,
        experiment_id=package.experiment_id,
        experiment_name=package.experiment_name,
        research_mode=package.research_mode,
        dataset_version=package.dataset_version,
        universe_version=package.universe_version,
        primary_outcome=package.primary_outcome,
        primary_evidence_id=package.primary_evidence_id,
        raw_event_count=package.primary_sample.raw_event_count,
        unique_instrument_count=package.primary_sample.unique_instrument_count,
        effective_sample_size=package.primary_sample.effective_sample_size,
        cluster_count=package.primary_sample.cluster_count,
        primary_metric_names=tuple(item.metric for item in package.primary_metrics),
        comparator_effect_count=len(package.primary_effects),
        validation_snapshot_count=sum(
            item.role is EvidenceRole.VALIDATION for item in package.evidence_snapshots
        ),
        walk_forward_fold_count=len(package.walk_forward_snapshots),
        robustness_challenge_count=len(package.robustness_snapshots),
        final_holdout_count=len(package.final_holdout_snapshots),
        multiplicity_family_count=len(package.multiplicity),
        parameter_surface_count=len(package.parameter_surface_ids),
        decision_state=package.decision_state,
        warning_count=len(package.warnings),
    )


def _primary_snapshot(review: ValidationReviewBundle, evidence_id: str) -> EvidenceSnapshot:
    if not evidence_id.strip():
        raise ValueError("primary_evidence_id must be non-empty")
    matches = tuple(item for item in review.report.snapshots if item.evidence_id == evidence_id)
    if len(matches) != 1:
        raise ValueError(
            "primary_evidence_id must reference exactly one snapshot in the validation report"
        )
    return matches[0]


def _validate_profile_coverage(
    review: ValidationReviewBundle,
    primary: EvidenceSnapshot,
    profile: ResearchEvidenceReportingProfile,
) -> None:
    metrics = {item.metric: item for item in primary.metrics}
    missing_metrics = tuple(
        name for name in profile.required_primary_metrics if name not in metrics
    )
    if missing_metrics:
        raise ValueError(
            "primary evidence is missing required reporting metrics: "
            + ", ".join(missing_metrics)
        )

    for family in profile.required_metric_families:
        observed = sum(name.startswith(family.prefix) for name in metrics)
        if observed < family.minimum_count:
            raise ValueError(
                f"primary evidence requires at least {family.minimum_count} metrics with prefix "
                f"{family.prefix!r}; observed {observed}"
            )

    missing_intervals = tuple(
        name
        for name in profile.metrics_requiring_interval
        if name not in metrics or metrics[name].interval is None
    )
    if missing_intervals:
        raise ValueError(
            "primary evidence is missing required uncertainty intervals: "
            + ", ".join(missing_intervals)
        )

    if profile.require_comparator_effect and not primary.effects:
        raise ValueError("primary evidence requires at least one predeclared comparator effect")
    if profile.require_comparator_interval and any(
        effect.interval is None for effect in primary.effects
    ):
        raise ValueError("primary comparator effects require uncertainty intervals")

    role_counts = {item.role: item.count for item in review.role_counts}
    missing_roles = tuple(role for role in profile.required_roles if role_counts.get(role, 0) < 1)
    if missing_roles:
        names = ", ".join(role.value for role in missing_roles)
        raise ValueError(f"research evidence package is missing required evidence roles: {names}")


def _validate_decision(decision: ResearchDecision | None, experiment_id: str) -> None:
    if decision is None:
        return
    if experiment_id not in set(decision.experiment_ids):
        raise ValueError("research decision does not cite the packaged experiment")


__all__ = [
    "RESEARCH_EVIDENCE_PACKAGE_VERSION",
    "MetricFamilyRequirement",
    "ResearchEvidencePackage",
    "ResearchEvidenceReportingProfile",
    "ResearchEvidenceSummary",
    "StageArtifactEvidence",
    "build_research_evidence_package",
    "canonical_research_reporting_profile",
    "summarize_research_evidence_package",
]
