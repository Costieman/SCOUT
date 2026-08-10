from trade_scout.data.composite_evidence import CompositeCoverageState


def test_composite_states_are_exhaustive_for_two_provider_presence() -> None:
    assert set(CompositeCoverageState) == {
        CompositeCoverageState.BOTH_AGREE,
        CompositeCoverageState.BOTH_DISAGREE,
        CompositeCoverageState.A_ONLY,
        CompositeCoverageState.B_ONLY,
    }
