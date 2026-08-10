import json
from pathlib import Path


def test_ab_policy_disables_unsafe_fill_modes() -> None:
    payload = json.loads(Path("configs/alpha_stooq_ab_policy_v0.1.json").read_text())
    assert payload["automatic_promotion_states"] == ["BOTH_AGREE"]
    assert payload["allow_averaging"] is False
    assert payload["allow_interpolation_in_canonical_raw"] is False
    assert payload["allow_majority_vote"] is False
    assert payload["allow_one_sided_fill_without_review"] is False
