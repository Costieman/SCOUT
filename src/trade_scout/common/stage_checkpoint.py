"""Durable per-stage/per-asset checkpoints for restart-safe SCOUT operations."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from tempfile import NamedTemporaryFile


@dataclass(frozen=True, slots=True)
class StageCheckpoint:
    operation_id: str
    stage: str
    asset: str
    fingerprint: str
    completed_at: str
    status: str = "COMPLETED"
    contract_version: str = "stage-checkpoint-v1"

    def __post_init__(self) -> None:
        for field_name, value in (
            ("operation_id", self.operation_id),
            ("stage", self.stage),
            ("asset", self.asset),
            ("fingerprint", self.fingerprint),
        ):
            if not value.strip():
                raise ValueError(f"{field_name} must be non-empty")
        if self.status != "COMPLETED":
            raise ValueError("stage checkpoints currently persist completed work only")


class FileStageCheckpointStore:
    """Atomic JSON checkpoint store keyed by operation/stage/asset."""

    def __init__(self, root: Path) -> None:
        self.root = root

    def checkpoint_path(self, operation_id: str, stage: str, asset: str) -> Path:
        return self.root / _safe(operation_id) / _safe(stage) / f"{_safe(asset)}.json"

    def mark_completed(
        self,
        *,
        operation_id: str,
        stage: str,
        asset: str,
        fingerprint: str,
    ) -> StageCheckpoint:
        checkpoint = StageCheckpoint(
            operation_id=operation_id,
            stage=stage,
            asset=asset,
            fingerprint=fingerprint,
            completed_at=datetime.now(UTC).isoformat(),
        )
        path = self.checkpoint_path(operation_id, stage, asset)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(asdict(checkpoint), sort_keys=True, separators=(",", ":"))
        with NamedTemporaryFile(
            "w", encoding="utf-8", dir=path.parent, delete=False, prefix=f".{path.name}."
        ) as handle:
            handle.write(payload)
            handle.flush()
            temporary = Path(handle.name)
        temporary.replace(path)
        return checkpoint

    def completed(
        self,
        *,
        operation_id: str,
        stage: str,
        asset: str,
        fingerprint: str,
    ) -> bool:
        checkpoint = self.read(operation_id=operation_id, stage=stage, asset=asset)
        return checkpoint is not None and checkpoint.fingerprint == fingerprint

    def read(self, *, operation_id: str, stage: str, asset: str) -> StageCheckpoint | None:
        path = self.checkpoint_path(operation_id, stage, asset)
        if not path.exists():
            return None
        payload = json.loads(path.read_text(encoding="utf-8"))
        return StageCheckpoint(**payload)

    def incomplete_assets(
        self,
        *,
        operation_id: str,
        stage: str,
        assets: tuple[str, ...],
        fingerprint_by_asset: dict[str, str],
    ) -> tuple[str, ...]:
        """Return only assets whose exact stage work still needs execution."""

        missing: list[str] = []
        for asset in assets:
            fingerprint = fingerprint_by_asset[asset]
            if not self.completed(
                operation_id=operation_id,
                stage=stage,
                asset=asset,
                fingerprint=fingerprint,
            ):
                missing.append(asset)
        return tuple(missing)


def _safe(value: str) -> str:
    cleaned = value.strip().replace("\\", "_").replace("/", "_").replace(":", "_")
    if not cleaned or cleaned in {".", ".."}:
        raise ValueError("checkpoint path component must be non-empty and safe")
    return cleaned


__all__ = ["FileStageCheckpointStore", "StageCheckpoint"]
