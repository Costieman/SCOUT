"""Immutable row-provenance sidecar for composite canonical datasets."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from hashlib import sha256
from pathlib import Path

from trade_scout.data.composite_adjudication import CompositeAdjudicationState
from trade_scout.data.composite_evidence import CompositeCoverageState
from trade_scout.data.composite_promotion import CompositeRowProvenance
from trade_scout.data.contracts import DatasetVersion


class CompositeProvenanceConflictError(RuntimeError):
    """Raised when an immutable dataset version is reused with different provenance."""


class CompositeProvenanceIntegrityError(RuntimeError):
    """Raised when stored provenance no longer matches its manifest checksum."""


@dataclass(frozen=True, slots=True)
class CompositeProvenanceManifest:
    dataset_version: DatasetVersion
    record_count: int
    included_count: int
    rejected_or_unmaterialized_count: int
    checksum_sha256: str
    relative_path: str


class CompositeProvenanceStore:
    """Persist deterministic row provenance independently from provider-neutral canonical bars."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.provenance_root = root / "metadata" / "composite_row_provenance"

    def write(
        self,
        dataset_version: DatasetVersion,
        records: tuple[CompositeRowProvenance, ...],
    ) -> CompositeProvenanceManifest:
        """Write one immutable JSONL provenance sidecar for a canonical dataset version."""

        if not records:
            raise ValueError("composite provenance requires at least one reviewed decision")
        ordered = tuple(sorted(records, key=lambda item: (item.instrument_id, item.trade_date)))
        _validate_unique_records(ordered)
        payload = _serialize(ordered)
        checksum = sha256(payload).hexdigest()
        path = self._path(dataset_version)
        relative = str(path.relative_to(self.root))
        manifest = CompositeProvenanceManifest(
            dataset_version=dataset_version,
            record_count=len(ordered),
            included_count=sum(item.included for item in ordered),
            rejected_or_unmaterialized_count=sum(not item.included for item in ordered),
            checksum_sha256=checksum,
            relative_path=relative,
        )

        if path.exists():
            existing = path.read_bytes()
            if sha256(existing).hexdigest() != checksum or existing != payload:
                raise CompositeProvenanceConflictError(
                    f"composite provenance already exists for {dataset_version} with different content"
                )
            return manifest

        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)
        return manifest

    def load(
        self,
        manifest: CompositeProvenanceManifest,
    ) -> tuple[CompositeRowProvenance, ...]:
        """Verify checksum before returning stored provenance records."""

        path = self.root / manifest.relative_path
        if not path.is_file():
            raise CompositeProvenanceIntegrityError(
                f"composite provenance is missing for {manifest.dataset_version}"
            )
        payload = path.read_bytes()
        if sha256(payload).hexdigest() != manifest.checksum_sha256:
            raise CompositeProvenanceIntegrityError(
                f"composite provenance checksum mismatch for {manifest.dataset_version}"
            )
        records = tuple(_deserialize_line(line) for line in payload.decode("utf-8").splitlines())
        if len(records) != manifest.record_count:
            raise CompositeProvenanceIntegrityError(
                f"composite provenance record count mismatch for {manifest.dataset_version}"
            )
        return records

    def _path(self, dataset_version: DatasetVersion) -> Path:
        version = str(dataset_version)
        if not version or "/" in version or "\\" in version or version in {".", ".."}:
            raise ValueError("invalid composite provenance dataset version")
        return self.provenance_root / f"{version}.jsonl"


def _serialize(records: tuple[CompositeRowProvenance, ...]) -> bytes:
    lines = []
    for record in records:
        payload = asdict(record)
        payload["evidence_state"] = record.evidence_state.value
        payload["adjudication_state"] = record.adjudication_state.value
        payload["corroborating_provider_ids"] = list(record.corroborating_provider_ids)
        lines.append(json.dumps(payload, sort_keys=True, separators=(",", ":")))
    return ("\n".join(lines) + "\n").encode("utf-8")


def _deserialize_line(line: str) -> CompositeRowProvenance:
    payload = json.loads(line)
    return CompositeRowProvenance(
        instrument_id=str(payload["instrument_id"]),
        trade_date=str(payload["trade_date"]),
        included=bool(payload["included"]),
        canonical_provider_id=str(payload["canonical_provider_id"]),
        selected_source_provider_id=_optional_str(payload.get("selected_source_provider_id")),
        selected_source_provider_instrument_id=_optional_str(
            payload.get("selected_source_provider_instrument_id")
        ),
        evidence_state=CompositeCoverageState(str(payload["evidence_state"])),
        adjudication_state=CompositeAdjudicationState(str(payload["adjudication_state"])),
        review_note=_optional_str(payload.get("review_note")),
        corroborating_provider_ids=tuple(
            str(item) for item in payload["corroborating_provider_ids"]
        ),
    )


def _optional_str(value: object) -> str | None:
    return None if value is None else str(value)


def _validate_unique_records(records: tuple[CompositeRowProvenance, ...]) -> None:
    seen: set[tuple[str, str]] = set()
    for record in records:
        key = (record.instrument_id, record.trade_date)
        if key in seen:
            raise ValueError(f"duplicate composite provenance row for {key[0]} {key[1]}")
        seen.add(key)
