from __future__ import annotations

import json
from pathlib import Path

from trade_scout.data.acceptance import AcceptanceEvidenceStatus, DataFoundationCriterion
from trade_scout.data.evidence_bridge import assess_runtime_evidence


def test_eodhd_tiingo_report_is_cross_provider_evidence(tmp_path: Path) -> None:
    path = tmp_path / "cross-provider.json"
    path.write_text(
        json.dumps(
            {
                "evaluation_id": "eodhd-tiingo-cross-validation-v0.1",
                "expected_case_count": 4,
                "completed_case_count": 4,
                "complete": True,
                "unresolved_discrepancy_count": 0,
                "representative_sample_accepted": False,
                "cases": [{}, {}, {}, {}],
            }
        ),
        encoding="utf-8",
    )

    result = assess_runtime_evidence(path)

    assert result.evidence.criterion is DataFoundationCriterion.CROSS_PROVIDER_VALIDATION
    assert result.evidence.status is AcceptanceEvidenceStatus.PARTIAL
