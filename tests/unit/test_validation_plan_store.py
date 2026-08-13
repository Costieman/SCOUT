"""Tests for immutable checksum-verified validation design persistence."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from trade_scout.validation import (
    DateInterval,
    FileRobustnessPlanStore,
    FileValidationPlanStore,
    FrozenValidationPlanStoreError,
    RobustnessChallenge,
    RobustnessKind,
    RobustnessPlan,
    ValidationPlan,
    ValidationRole,
    ValidationSegment,
    WalkForwardFold,
)


def _validation_plan() -> ValidationPlan:
    return ValidationPlan(
        plan_id="validation-plan-001",
        segments=(
            ValidationSegment(
                "development",
                ValidationRole.DEVELOPMENT,
                DateInterval(date(2015, 1, 1), date(2019, 12, 31)),
            ),
            ValidationSegment(
                "validation",
                ValidationRole.VALIDATION,
                DateInterval(date(2020, 1, 1), date(2022, 12, 31)),
            ),
            ValidationSegment(
                "holdout",
                ValidationRole.HOLDOUT,
                DateInterval(date(2023, 1, 1), date(2025, 12, 31)),
            ),
        ),
        walk_forward_folds=(
            WalkForwardFold(
                "fold-001",
                DateInterval(date(2015, 1, 1), date(2018, 12, 31)),
                DateInterval(date(2019, 1, 1), date(2019, 12, 31)),
            ),
            WalkForwardFold(
                "fold-002",
                DateInterval(date(2015, 1, 1), date(2019, 12, 31)),
                DateInterval(date(2020, 1, 1), date(2020, 12, 31)),
            ),
        ),
        primary_outcome="forward_return_60",
        comparator_id="matched-random-events-v1",
        robustness_checks=("entry-shift", "cost-stress"),
        notes=("Frozen before confirmatory outcomes are inspected.",),
    )


def _robustness_plan() -> RobustnessPlan:
    return RobustnessPlan(
        plan_id="robustness-plan-001",
        challenges=(
            RobustnessChallenge(
                "entry-plus-one",
                RobustnessKind.ENTRY_SHIFT,
                "Shift executable entry by one session.",
                ("entry_convention",),
            ),
            RobustnessChallenge(
                "higher-costs",
                RobustnessKind.COST_STRESS,
                "Increase transaction cost assumptions.",
                ("costs",),
            ),
        ),
    )


def test_validation_plan_round_trip_preserves_full_frozen_design(tmp_path: Path) -> None:
    store = FileValidationPlanStore(tmp_path)
    plan = _validation_plan()

    checksum = store.write(plan)

    assert len(checksum) == 64
    assert store.read_validation_plan(plan.plan_id) == plan
    assert store.checksum(plan.plan_id) == checksum
    assert store.list_plan_ids() == (plan.plan_id,)


def test_validation_plan_store_is_append_only(tmp_path: Path) -> None:
    store = FileValidationPlanStore(tmp_path)
    plan = _validation_plan()
    store.write(plan)

    with pytest.raises(FrozenValidationPlanStoreError, match="already exists"):
        store.write(plan)


def test_validation_plan_store_detects_payload_tampering(tmp_path: Path) -> None:
    store = FileValidationPlanStore(tmp_path)
    plan = _validation_plan()
    store.write(plan)
    path = tmp_path / "validation_plan" / f"{plan.plan_id}.json"
    raw = json.loads(path.read_text(encoding="utf-8"))
    raw["payload"]["primary_outcome"] = "tampered"
    path.write_text(json.dumps(raw), encoding="utf-8")

    with pytest.raises(FrozenValidationPlanStoreError, match="checksum mismatch"):
        store.read_validation_plan(plan.plan_id)


def test_validation_plan_store_detects_file_identity_tampering(tmp_path: Path) -> None:
    store = FileValidationPlanStore(tmp_path)
    plan = _validation_plan()
    store.write(plan)
    path = tmp_path / "validation_plan" / f"{plan.plan_id}.json"
    raw = json.loads(path.read_text(encoding="utf-8"))
    raw["identity"] = "different-plan"
    path.write_text(json.dumps(raw), encoding="utf-8")

    with pytest.raises(FrozenValidationPlanStoreError, match="file identity mismatch"):
        store.read_validation_plan(plan.plan_id)


def test_validation_plan_store_rejects_unsupported_schema(tmp_path: Path) -> None:
    store = FileValidationPlanStore(tmp_path)
    plan = _validation_plan()
    store.write(plan)
    path = tmp_path / "validation_plan" / f"{plan.plan_id}.json"
    raw = json.loads(path.read_text(encoding="utf-8"))
    raw["schema_version"] = 999
    path.write_text(json.dumps(raw), encoding="utf-8")

    with pytest.raises(FrozenValidationPlanStoreError, match="unsupported"):
        store.read_validation_plan(plan.plan_id)


def test_robustness_plan_round_trip_preserves_all_challenges(tmp_path: Path) -> None:
    store = FileRobustnessPlanStore(tmp_path)
    plan = _robustness_plan()

    checksum = store.write(plan)

    assert len(checksum) == 64
    assert store.read_robustness_plan(plan.plan_id) == plan
    assert store.checksum(plan.plan_id) == checksum
    assert store.list_plan_ids() == (plan.plan_id,)


def test_robustness_plan_store_is_append_only(tmp_path: Path) -> None:
    store = FileRobustnessPlanStore(tmp_path)
    plan = _robustness_plan()
    store.write(plan)

    with pytest.raises(FrozenValidationPlanStoreError, match="already exists"):
        store.write(plan)


def test_robustness_plan_store_detects_payload_tampering(tmp_path: Path) -> None:
    store = FileRobustnessPlanStore(tmp_path)
    plan = _robustness_plan()
    store.write(plan)
    path = tmp_path / "robustness_plan" / f"{plan.plan_id}.json"
    raw = json.loads(path.read_text(encoding="utf-8"))
    raw["payload"]["challenges"][0]["description"] = "post hoc rewrite"
    path.write_text(json.dumps(raw), encoding="utf-8")

    with pytest.raises(FrozenValidationPlanStoreError, match="checksum mismatch"):
        store.read_robustness_plan(plan.plan_id)


def test_plan_identity_must_be_path_safe(tmp_path: Path) -> None:
    store = FileValidationPlanStore(tmp_path)

    with pytest.raises(ValueError, match="path-safe"):
        store.read_validation_plan("../escape")
