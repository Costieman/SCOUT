from __future__ import annotations

from pathlib import Path


def test_phase9_10_documentation_preserves_comparison_and_promotion_rules() -> None:
    text = Path("docs/strategy_suite_phase9_10.md").read_text(encoding="utf-8")
    assert "without forcing heterogeneous evidence into a single winner score" in text
    lifecycle = (
        "idea -> exploratory -> candidate -> validation -> validated -> "
        "production-eligible -> scanner"
    )
    assert lifecycle in text
    assert "Advancement is limited to one stage at a time" in text
    assert "Structural suites that remain PARTIAL or REQUIRES_PATTERN cannot be promoted" in text
