from scripts.promote_tiingo_reviewed_prices import _OPERATOR_DATASET_VERSION_BY_IDENTITY


def test_reviewed_identity_v06_maps_to_new_immutable_canonical_version() -> None:
    assert str(
        _OPERATOR_DATASET_VERSION_BY_IDENTITY["tiingo-reviewed-identity-candidate-v0.6"]
    ) == "tiingo-reviewed-split-only-v0.5"
