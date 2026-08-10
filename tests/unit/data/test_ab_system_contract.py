from trade_scout.data.composite_evidence import CompositeCoverageState


def test_only_agreement_state_is_intended_for_unreviewed_promotion() -> None:
    assert CompositeCoverageState.BOTH_AGREE.value == "BOTH_AGREE"
    assert CompositeCoverageState.A_ONLY.value == "A_ONLY"
    assert CompositeCoverageState.B_ONLY.value == "B_ONLY"
    assert CompositeCoverageState.BOTH_DISAGREE.value == "BOTH_DISAGREE"
