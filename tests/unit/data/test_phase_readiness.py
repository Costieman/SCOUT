from __future__ import annotations

from pathlib import Path

import pytest

from trade_scout.data.phase_readiness import PhaseReadinessError, load_phase1_readiness


def test_checked_in_phase1_readiness_remains_blocked() -> None:
    report = load_phase1_readiness(
        data_ledger_path=Path("configs/data_foundation_acceptance_v0.1.json"),
        provider_ledger_path=Path("configs/provider_acceptance_eodhd_v0.1.json"),
    )

    assert report.phase_complete is False
    assert any(item.startswith("data:stable_instrument_master") for item in report.blockers)
    assert any(item.startswith("provider:license_and_retention_rights") for item in report.blockers)

    with pytest.raises(PhaseReadinessError, match="Phase 1 is not ready for Phase 2"):
        report.require_complete()
