from __future__ import annotations

import runpy
from pathlib import Path

_REPOSITORY_ROOT = Path(__file__).resolve().parents[3]


def test_reviewed_identity_v06_maps_to_new_immutable_canonical_version() -> None:
    module = runpy.run_path(
        str(_REPOSITORY_ROOT / "scripts" / "promote_tiingo_reviewed_prices.py"),
        run_name="trade_scout_promote_mapping_test",
    )
    mapping = module["_OPERATOR_DATASET_VERSION_BY_IDENTITY"]
    assert str(mapping["tiingo-reviewed-identity-candidate-v0.6"]) == (
        "tiingo-reviewed-split-only-v0.5"
    )
