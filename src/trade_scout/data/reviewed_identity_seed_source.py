"""Compose immutable reviewed-identity seed sets without duplicating prior reviewed evidence."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from trade_scout.data.reviewed_identity_snapshot import (
    ReviewedIdentitySeed,
    ReviewedIdentitySeedSet,
    ReviewedIdentitySnapshotError,
    load_reviewed_identity_seed_set,
)

_COMPOSITION_SCHEMA = "reviewed-identity-seed-composition-v0.1"


def load_reviewed_identity_seed_source(path: Path) -> ReviewedIdentitySeedSet:
    """Load a full seed set or a composition of an immutable base plus reviewed additions.

    Composition exists to preserve previously reviewed seed files byte-for-byte while allowing a later
    snapshot to add newly reviewed identities. Both the base and additions are independently strict
    ``reviewed-identity-seeds-v0.1`` files. The resolved source checksum commits to both inputs and the
    small composition manifest.
    """

    raw = _read_bytes(path)
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ReviewedIdentitySnapshotError(
            "reviewed identity seed source is invalid JSON"
        ) from exc
    if not isinstance(payload, dict):
        raise ReviewedIdentitySnapshotError("reviewed identity seed source root must be an object")

    if payload.get("schema_version") != _COMPOSITION_SCHEMA:
        return load_reviewed_identity_seed_set(path)

    expected_fields = {"schema_version", "snapshot_version", "base", "additions"}
    if set(payload) != expected_fields:
        raise ReviewedIdentitySnapshotError(
            "reviewed identity seed composition has missing or unknown fields"
        )

    base_path = _resolved_sibling(path, _required_text(payload.get("base"), "base"))
    additions_path = _resolved_sibling(
        path,
        _required_text(payload.get("additions"), "additions"),
    )
    base = load_reviewed_identity_seed_set(base_path)
    additions = load_reviewed_identity_seed_set(additions_path)
    if base.primary_provider_id != additions.primary_provider_id:
        raise ReviewedIdentitySnapshotError("composed seed sources use different primary providers")
    if base.identity_definition_version != additions.identity_definition_version:
        raise ReviewedIdentitySnapshotError(
            "composed seed sources use different identity definitions"
        )
    if base.symbol_history_definition_version != additions.symbol_history_definition_version:
        raise ReviewedIdentitySnapshotError(
            "composed seed sources use different symbol-history definitions"
        )

    seeds = tuple(sorted((*base.seeds, *additions.seeds), key=lambda item: item.review_id))
    _validate_composed_uniqueness(seeds)
    snapshot_version = _required_text(payload.get("snapshot_version"), "snapshot_version")
    digest = hashlib.sha256(
        b"reviewed-identity-seed-composition-v0.1\n"
        + base.source_sha256.encode("ascii")
        + b"\n"
        + additions.source_sha256.encode("ascii")
        + b"\n"
        + raw
    ).hexdigest()
    return ReviewedIdentitySeedSet(
        snapshot_version=snapshot_version,
        primary_provider_id=base.primary_provider_id,
        identity_definition_version=base.identity_definition_version,
        symbol_history_definition_version=base.symbol_history_definition_version,
        seeds=seeds,
        source_sha256=digest,
    )


def _validate_composed_uniqueness(seeds: tuple[ReviewedIdentitySeed, ...]) -> None:
    review_ids: set[str] = set()
    provider_owners: dict[tuple[str, str], str] = {}
    query_owners: dict[tuple[str, str], str] = {}
    for seed in seeds:
        if seed.review_id in review_ids:
            raise ReviewedIdentitySnapshotError(f"duplicate review_id {seed.review_id}")
        review_ids.add(seed.review_id)
        for provider_id, series_id in seed.provider_links.items():
            key = (provider_id, series_id)
            prior = provider_owners.get(key)
            if prior is not None and prior != seed.review_id:
                raise ReviewedIdentitySnapshotError(
                    f"provider series {provider_id}:{series_id} has multiple owners"
                )
            provider_owners[key] = seed.review_id
        for provider_id, query_symbol in seed.provider_query_symbols.items():
            key = (provider_id, query_symbol)
            prior = query_owners.get(key)
            if prior is not None and prior != seed.review_id:
                raise ReviewedIdentitySnapshotError(
                    f"provider query {provider_id}:{query_symbol} has multiple owners"
                )
            query_owners[key] = seed.review_id


def _resolved_sibling(source: Path, name: str) -> Path:
    candidate = (source.parent / name).resolve()
    parent = source.parent.resolve()
    if candidate.parent != parent:
        raise ReviewedIdentitySnapshotError(
            "seed composition may reference sibling config files only"
        )
    if candidate == source.resolve():
        raise ReviewedIdentitySnapshotError("seed composition cannot reference itself")
    return candidate


def _read_bytes(path: Path) -> bytes:
    try:
        return path.read_bytes()
    except OSError as exc:
        raise ReviewedIdentitySnapshotError(
            f"cannot read reviewed identity seed source: {path}"
        ) from exc


def _required_text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ReviewedIdentitySnapshotError(f"{field} must be non-empty text")
    return value.strip()


__all__ = ["load_reviewed_identity_seed_source"]
