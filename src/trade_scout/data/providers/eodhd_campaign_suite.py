"""Deterministic checkpointing for a multi-case EODHD canonical evidence campaign."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from trade_scout.data.contracts import DatasetVersion


class EodhdCampaignSuiteError(ValueError):
    """Raised when a campaign suite specification or persisted state is invalid."""


class EodhdCampaignSuiteExecutionError(RuntimeError):
    """Raised after a case failure while preserving all prior completed evidence."""

    def __init__(self, case_id: str, message: str) -> None:
        super().__init__(f"EODHD campaign case {case_id} failed: {message}")
        self.case_id = case_id


@dataclass(frozen=True, slots=True)
class EodhdCampaignSuiteCase:
    """One explicit case in a reproducible multi-case provider evidence campaign."""

    case_id: str
    symbol: str
    start: date
    end: date
    expected_active: bool
    dataset_version: DatasetVersion

    def __post_init__(self) -> None:
        for field, value in (
            ("case_id", self.case_id),
            ("symbol", self.symbol),
            ("dataset_version", str(self.dataset_version)),
        ):
            if not value.strip():
                raise EodhdCampaignSuiteError(f"{field} must be non-empty")
        if self.end < self.start:
            raise EodhdCampaignSuiteError("campaign case end must be on or after start")


@dataclass(frozen=True, slots=True)
class EodhdCampaignSuiteResult:
    """Current deterministic completion state for one campaign suite."""

    campaign_id: str
    expected_case_count: int
    completed_case_ids: tuple[str, ...]
    complete: bool
    new_case_count: int
    remaining_case_count: int
    stopped_by_limit: bool


CaseRunner = Callable[[EodhdCampaignSuiteCase], dict[str, object]]


def run_eodhd_campaign_suite(
    cases: Sequence[EodhdCampaignSuiteCase],
    *,
    root: Path,
    case_runner: CaseRunner,
    max_new_cases: int | None = None,
) -> EodhdCampaignSuiteResult:
    """Run pending cases in stable order, checkpointing each completed result before continuing."""

    if max_new_cases is not None and max_new_cases < 1:
        raise EodhdCampaignSuiteError("max_new_cases must be positive when supplied")

    ordered = _validate_cases(cases)
    campaign_id = _campaign_id(ordered)
    campaign_root = root / campaign_id
    campaign_root.mkdir(parents=True, exist_ok=True)
    _persist_campaign_spec(campaign_root, campaign_id, ordered)
    completed = _load_checkpoint(campaign_root, campaign_id, ordered)
    completed_before = len(completed)

    for case in ordered:
        if case.case_id in completed:
            _verify_completed_result(campaign_root, case.case_id)
            continue
        if max_new_cases is not None and len(completed) - completed_before >= max_new_cases:
            break
        try:
            result = case_runner(case)
            _persist_case_result(campaign_root, case.case_id, result)
            completed.add(case.case_id)
            _write_checkpoint(campaign_root, campaign_id, ordered, completed)
        except Exception as exc:
            if isinstance(exc, EodhdCampaignSuiteError):
                raise
            _write_checkpoint(campaign_root, campaign_id, ordered, completed)
            raise EodhdCampaignSuiteExecutionError(case.case_id, str(exc)) from exc

    completed_ids = tuple(case.case_id for case in ordered if case.case_id in completed)
    new_case_count = len(completed) - completed_before
    remaining_case_count = len(ordered) - len(completed_ids)
    complete = remaining_case_count == 0
    return EodhdCampaignSuiteResult(
        campaign_id=campaign_id,
        expected_case_count=len(ordered),
        completed_case_ids=completed_ids,
        complete=complete,
        new_case_count=new_case_count,
        remaining_case_count=remaining_case_count,
        stopped_by_limit=not complete
        and max_new_cases is not None
        and new_case_count >= max_new_cases,
    )


def _validate_cases(cases: Sequence[EodhdCampaignSuiteCase]) -> tuple[EodhdCampaignSuiteCase, ...]:
    ordered = tuple(cases)
    if not ordered:
        raise EodhdCampaignSuiteError("EODHD campaign suite requires at least one case")
    case_ids = [case.case_id for case in ordered]
    if len(case_ids) != len(set(case_ids)):
        raise EodhdCampaignSuiteError("EODHD campaign case IDs must be unique")
    dataset_versions = [str(case.dataset_version) for case in ordered]
    if len(dataset_versions) != len(set(dataset_versions)):
        raise EodhdCampaignSuiteError("EODHD campaign dataset versions must be unique")
    return ordered


def _campaign_id(cases: tuple[EodhdCampaignSuiteCase, ...]) -> str:
    payload = [_case_payload(case) for case in cases]
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return "eodhd-campaign-" + hashlib.sha256(encoded).hexdigest()[:24]


def _persist_campaign_spec(
    root: Path,
    campaign_id: str,
    cases: tuple[EodhdCampaignSuiteCase, ...],
) -> None:
    path = root / "campaign.json"
    payload = {
        "schema_version": "eodhd-campaign-suite-v0.1",
        "campaign_id": campaign_id,
        "cases": [_case_payload(case) for case in cases],
    }
    encoded = _json_bytes(payload)
    if path.exists():
        if path.read_bytes() != encoded:
            raise EodhdCampaignSuiteError("persisted campaign specification conflicts with request")
        return
    path.write_bytes(encoded)


def _load_checkpoint(
    root: Path,
    campaign_id: str,
    cases: tuple[EodhdCampaignSuiteCase, ...],
) -> set[str]:
    path = root / "checkpoint.json"
    if not path.exists():
        _write_checkpoint(root, campaign_id, cases, set())
        return set()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise EodhdCampaignSuiteError("campaign checkpoint is invalid JSON") from exc
    if not isinstance(payload, dict) or payload.get("campaign_id") != campaign_id:
        raise EodhdCampaignSuiteError("campaign checkpoint identity is invalid")
    raw_completed = payload.get("completed_case_ids")
    if not isinstance(raw_completed, list) or not all(
        isinstance(item, str) for item in raw_completed
    ):
        raise EodhdCampaignSuiteError("campaign checkpoint completed_case_ids are invalid")
    allowed = {case.case_id for case in cases}
    completed = set(raw_completed)
    if not completed.issubset(allowed):
        raise EodhdCampaignSuiteError("campaign checkpoint references an unknown case")
    for case_id in completed:
        _verify_completed_result(root, case_id)
    return completed


def _write_checkpoint(
    root: Path,
    campaign_id: str,
    cases: tuple[EodhdCampaignSuiteCase, ...],
    completed: set[str],
) -> None:
    ordered_completed = [case.case_id for case in cases if case.case_id in completed]
    payload = {
        "schema_version": "eodhd-campaign-suite-v0.1",
        "campaign_id": campaign_id,
        "completed_case_ids": ordered_completed,
    }
    _write_atomic(root / "checkpoint.json", _json_bytes(payload))


def _persist_case_result(root: Path, case_id: str, result: dict[str, object]) -> None:
    path = root / "cases" / case_id / "result.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = _json_bytes(result)
    if path.exists():
        if path.read_bytes() != encoded:
            raise EodhdCampaignSuiteError(f"case {case_id} already has conflicting evidence")
        return
    path.write_bytes(encoded)


def _verify_completed_result(root: Path, case_id: str) -> None:
    path = root / "cases" / case_id / "result.json"
    if not path.is_file():
        raise EodhdCampaignSuiteError(
            f"campaign checkpoint marks {case_id} complete but its result is missing"
        )
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise EodhdCampaignSuiteError(f"campaign result for {case_id} is invalid JSON") from exc
    if not isinstance(payload, dict):
        raise EodhdCampaignSuiteError(f"campaign result for {case_id} must be an object")


def _case_payload(case: EodhdCampaignSuiteCase) -> dict[str, object]:
    return {
        "case_id": case.case_id,
        "symbol": case.symbol,
        "start": case.start.isoformat(),
        "end": case.end.isoformat(),
        "expected_active": case.expected_active,
        "dataset_version": str(case.dataset_version),
    }


def _json_bytes(payload: object) -> bytes:
    return (json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n").encode()


def _write_atomic(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_bytes(payload)
    temporary.replace(path)
