"""Private local operator workspace for Phase 1 data-foundation work.

The workspace ties durable provider evidence, safe campaign state, reconciliation reports,
canonical storage, and the read-only console to one explicit root directory. The manifest stores
control metadata only: no API keys, provider payload values, or credentials.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime
from pathlib import Path

from trade_scout.app.data_health_service import DataHealthSourcePaths
from trade_scout.data.durable_raw_receipt import (
    DurableRawReceiptError,
    load_durable_raw_receipt,
    verify_durable_raw_receipt,
)
from trade_scout.data.providers.tiingo_campaign_state import (
    TiingoCampaignStateError,
    TiingoSafeCampaignState,
    load_tiingo_safe_campaign_state,
)

_WORKSPACE_SCHEMA = "trade-scout-operator-workspace-v0.1"


class OperatorWorkspaceError(RuntimeError):
    """Raised when a workspace is unsafe, malformed, or internally inconsistent."""


@dataclass(frozen=True, slots=True)
class OperatorWorkspaceManifest:
    """Portable control metadata for one private operator workspace."""

    schema_version: str
    workspace_id: str
    storage_namespace: str
    created_at: datetime
    canonical_dataset_version: str | None = None
    scanner_required_session: date | None = None


@dataclass(frozen=True, slots=True)
class OperatorWorkspace:
    """Resolved directory layout for one local Trade Scout workspace."""

    root: Path
    manifest: OperatorWorkspaceManifest

    @property
    def manifest_path(self) -> Path:
        return self.root / "workspace.json"

    @property
    def tiingo_root(self) -> Path:
        return self.root / "providers" / "tiingo"

    @property
    def tiingo_raw_root(self) -> Path:
        return self.tiingo_root / "raw"

    @property
    def tiingo_receipts_root(self) -> Path:
        return self.tiingo_root / "receipts"

    @property
    def tiingo_safe_state_path(self) -> Path:
        return self.tiingo_root / "safe-state.json"

    @property
    def composite_evidence_root(self) -> Path:
        return self.root / "evidence" / "composite"

    @property
    def corporate_action_evidence_root(self) -> Path:
        return self.root / "evidence" / "corporate-actions"

    @property
    def failed_ingestion_root(self) -> Path:
        return self.root / "evidence" / "failed-ingestion"

    @property
    def canonical_root(self) -> Path:
        return self.root / "canonical-store"

    def data_health_sources(self, *, repository_root: Path) -> DataHealthSourcePaths:
        """Resolve all evidence inputs for the local Data Health console."""

        repository = repository_root.resolve()
        composite = tuple(sorted(self.composite_evidence_root.glob("*.json")))
        corporate_actions = tuple(sorted(self.corporate_action_evidence_root.glob("*.json")))
        failed_markers = tuple(
            sorted(path for path in self.failed_ingestion_root.iterdir() if path.is_file())
        )
        selected = self.manifest.canonical_dataset_version
        return DataHealthSourcePaths(
            tiingo_acceptance_path=repository
            / "configs"
            / "provider_acceptance_tiingo_v0.1.json",
            free_stack_acceptance_path=(
                repository / "configs" / "provider_acceptance_free_stack_v0.1.json"
            ),
            tiingo_safe_state_path=(
                self.tiingo_safe_state_path if self.tiingo_safe_state_path.exists() else None
            ),
            composite_evidence_paths=composite,
            canonical_root=self.canonical_root if selected is not None else None,
            canonical_dataset_version=selected,
            scanner_required_session=self.manifest.scanner_required_session,
            failed_ingestion_markers=failed_markers,
            corporate_action_anomaly_reports=corporate_actions,
        )


@dataclass(frozen=True, slots=True)
class WorkspaceVerification:
    """Evidence-consistency report for the durable Tiingo area of a workspace."""

    workspace_id: str
    state_present: bool
    durable_completed_symbol_count: int
    receipt_file_count: int
    verified_receipt_count: int
    missing_receipt_symbols: tuple[str, ...]
    receipt_subjects_not_in_state: tuple[str, ...]
    invalid_receipt_paths: tuple[str, ...]

    @property
    def is_consistent(self) -> bool:
        return not (
            self.missing_receipt_symbols
            or self.receipt_subjects_not_in_state
            or self.invalid_receipt_paths
        )


def validate_workspace_location(root: Path, *, repository_root: Path) -> None:
    """Refuse to place licensed/private runtime state inside the Git repository tree."""

    resolved = root.expanduser().resolve()
    repository = repository_root.resolve()
    if resolved == repository or repository in resolved.parents:
        raise OperatorWorkspaceError(
            "private operator workspace must live outside the Git repository tree"
        )


def initialize_operator_workspace(
    root: Path,
    *,
    storage_namespace: str,
    workspace_id: str = "trade-scout-phase1-local",
    created_at: datetime | None = None,
) -> OperatorWorkspace:
    """Create a new private workspace without overwriting unrelated existing contents."""

    resolved = root.expanduser().resolve()
    namespace = _required_text(storage_namespace, "storage_namespace")
    identifier = _required_text(workspace_id, "workspace_id")
    now = created_at or datetime.now(UTC)
    _validate_aware_datetime(now)

    manifest_path = resolved / "workspace.json"
    if manifest_path.exists():
        existing = load_operator_workspace(resolved)
        if existing.manifest.storage_namespace != namespace:
            raise OperatorWorkspaceError("workspace already exists with another storage namespace")
        if existing.manifest.workspace_id != identifier:
            raise OperatorWorkspaceError("workspace already exists with another workspace ID")
        _ensure_workspace_directories(existing)
        return existing

    if resolved.exists() and any(resolved.iterdir()):
        raise OperatorWorkspaceError(
            "refusing to initialize over a non-empty directory without a workspace manifest"
        )

    manifest = OperatorWorkspaceManifest(
        schema_version=_WORKSPACE_SCHEMA,
        workspace_id=identifier,
        storage_namespace=namespace,
        created_at=now.astimezone(UTC),
    )
    workspace = OperatorWorkspace(root=resolved, manifest=manifest)
    _ensure_workspace_directories(workspace)
    persist_operator_workspace_manifest(workspace)
    return workspace


def load_operator_workspace(root: Path) -> OperatorWorkspace:
    """Load and strictly validate one workspace manifest."""

    resolved = root.expanduser().resolve()
    path = resolved / "workspace.json"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise OperatorWorkspaceError(f"cannot read operator workspace manifest: {path}") from exc
    except json.JSONDecodeError as exc:
        raise OperatorWorkspaceError("operator workspace manifest is invalid JSON") from exc
    expected = {
        "schema_version",
        "workspace_id",
        "storage_namespace",
        "created_at",
        "canonical_dataset_version",
        "scanner_required_session",
    }
    if not isinstance(payload, dict) or set(payload) != expected:
        raise OperatorWorkspaceError("operator workspace manifest has missing or unknown fields")
    if payload["schema_version"] != _WORKSPACE_SCHEMA:
        raise OperatorWorkspaceError("unsupported operator workspace schema")
    try:
        created_at = datetime.fromisoformat(_required_text(payload["created_at"], "created_at"))
        scanner_session = (
            date.fromisoformat(payload["scanner_required_session"])
            if payload["scanner_required_session"] is not None
            else None
        )
    except ValueError as exc:
        raise OperatorWorkspaceError(
            "operator workspace contains invalid date/time fields"
        ) from exc
    _validate_aware_datetime(created_at)
    canonical = _optional_text(payload["canonical_dataset_version"], "canonical_dataset_version")
    manifest = OperatorWorkspaceManifest(
        schema_version=_WORKSPACE_SCHEMA,
        workspace_id=_required_text(payload["workspace_id"], "workspace_id"),
        storage_namespace=_required_text(payload["storage_namespace"], "storage_namespace"),
        created_at=created_at.astimezone(UTC),
        canonical_dataset_version=canonical,
        scanner_required_session=scanner_session,
    )
    workspace = OperatorWorkspace(root=resolved, manifest=manifest)
    _ensure_workspace_directories(workspace)
    return workspace


def configure_operator_workspace(
    workspace: OperatorWorkspace,
    *,
    canonical_dataset_version: str | None,
    scanner_required_session: date | None,
) -> OperatorWorkspace:
    """Persist explicit canonical/freshness selections without changing storage identity."""

    canonical = (
        _required_text(canonical_dataset_version, "canonical_dataset_version")
        if canonical_dataset_version is not None
        else None
    )
    updated = OperatorWorkspace(
        root=workspace.root,
        manifest=OperatorWorkspaceManifest(
            schema_version=workspace.manifest.schema_version,
            workspace_id=workspace.manifest.workspace_id,
            storage_namespace=workspace.manifest.storage_namespace,
            created_at=workspace.manifest.created_at,
            canonical_dataset_version=canonical,
            scanner_required_session=scanner_required_session,
        ),
    )
    persist_operator_workspace_manifest(updated)
    return updated


def persist_operator_workspace_manifest(workspace: OperatorWorkspace) -> None:
    """Atomically persist the metadata-only workspace manifest."""

    payload = asdict(workspace.manifest)
    payload["created_at"] = workspace.manifest.created_at.isoformat()
    payload["scanner_required_session"] = (
        workspace.manifest.scanner_required_session.isoformat()
        if workspace.manifest.scanner_required_session is not None
        else None
    )
    workspace.root.mkdir(parents=True, exist_ok=True)
    temporary = workspace.manifest_path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(workspace.manifest_path)


def verify_operator_workspace(workspace: OperatorWorkspace) -> WorkspaceVerification:
    """Verify all durable Tiingo receipts and their relationship to safe campaign state."""

    state = _load_safe_state_if_present(workspace.tiingo_safe_state_path)
    completed = set(state.durable_completed_symbols) if state is not None else set()
    receipt_files = tuple(sorted(workspace.tiingo_receipts_root.rglob("*.json")))
    verified_subjects: set[str] = set()
    invalid_paths: list[str] = []

    for path in receipt_files:
        try:
            receipt = load_durable_raw_receipt(path)
            verify_durable_raw_receipt(
                receipt,
                durable_root=workspace.tiingo_raw_root,
                storage_namespace=workspace.manifest.storage_namespace,
            )
        except (DurableRawReceiptError, OSError):
            invalid_paths.append(str(path.relative_to(workspace.root)))
            continue
        verified_subjects.add(receipt.subject_key)

    return WorkspaceVerification(
        workspace_id=workspace.manifest.workspace_id,
        state_present=state is not None,
        durable_completed_symbol_count=len(completed),
        receipt_file_count=len(receipt_files),
        verified_receipt_count=len(receipt_files) - len(invalid_paths),
        missing_receipt_symbols=tuple(sorted(completed - verified_subjects)),
        receipt_subjects_not_in_state=tuple(sorted(verified_subjects - completed)),
        invalid_receipt_paths=tuple(sorted(invalid_paths)),
    )


def workspace_status_payload(workspace: OperatorWorkspace) -> dict[str, object]:
    """Return safe operator-facing status without reading provider payload values."""

    state = _load_safe_state_if_present(workspace.tiingo_safe_state_path)
    verification = verify_operator_workspace(workspace)
    return {
        "schema_version": workspace.manifest.schema_version,
        "workspace_id": workspace.manifest.workspace_id,
        "root": str(workspace.root),
        "storage_namespace": workspace.manifest.storage_namespace,
        "canonical_dataset_version": workspace.manifest.canonical_dataset_version,
        "scanner_required_session": (
            workspace.manifest.scanner_required_session.isoformat()
            if workspace.manifest.scanner_required_session is not None
            else None
        ),
        "tiingo": {
            "state_present": state is not None,
            "status": state.last_status if state is not None else "NOT_STARTED",
            "durable_completed_symbol_count": (
                state.durable_completed_symbol_count if state is not None else 0
            ),
            "total_symbol_count": state.total_symbol_count if state is not None else None,
            "durable_row_count_total": state.durable_row_count_total if state is not None else 0,
            "quota_pause_count": state.quota_pause_count if state is not None else 0,
            "failure_count": state.failure_count if state is not None else 0,
            "last_run_at": state.last_run_at.isoformat() if state and state.last_run_at else None,
        },
        "verification": {
            "consistent": verification.is_consistent,
            "receipt_file_count": verification.receipt_file_count,
            "verified_receipt_count": verification.verified_receipt_count,
            "missing_receipt_symbols": list(verification.missing_receipt_symbols),
            "receipt_subjects_not_in_state": list(verification.receipt_subjects_not_in_state),
            "invalid_receipt_paths": list(verification.invalid_receipt_paths),
        },
        "evidence": {
            "composite_report_count": sum(
                1 for _ in workspace.composite_evidence_root.glob("*.json")
            ),
            "corporate_action_report_count": sum(
                1 for _ in workspace.corporate_action_evidence_root.glob("*.json")
            ),
            "failed_ingestion_marker_count": sum(
                1 for path in workspace.failed_ingestion_root.iterdir() if path.is_file()
            ),
        },
    }


def _ensure_workspace_directories(workspace: OperatorWorkspace) -> None:
    for path in (
        workspace.tiingo_raw_root,
        workspace.tiingo_receipts_root,
        workspace.composite_evidence_root,
        workspace.corporate_action_evidence_root,
        workspace.failed_ingestion_root,
        workspace.canonical_root,
    ):
        path.mkdir(parents=True, exist_ok=True)


def _load_safe_state_if_present(path: Path) -> TiingoSafeCampaignState | None:
    if not path.exists():
        return None
    try:
        return load_tiingo_safe_campaign_state(path)
    except TiingoCampaignStateError as exc:
        raise OperatorWorkspaceError("Tiingo safe campaign state is invalid") from exc


def _validate_aware_datetime(value: datetime) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise OperatorWorkspaceError("workspace timestamps must be timezone-aware")


def _required_text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise OperatorWorkspaceError(f"{field} must be non-empty text")
    return value.strip()


def _optional_text(value: object, field: str) -> str | None:
    if value is None:
        return None
    return _required_text(value, field)
