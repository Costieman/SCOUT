from __future__ import annotations

from trade_scout.app.research_brain_http import _inject_brain_discovery_selector
from trade_scout.app.research_brain_service import ResearchBrainListItem
from trade_scout.experiments.research_brains import ResearchBrainDefinition


def test_injected_brain_discovery_selector_exposes_existing_brains() -> None:
    definition = ResearchBrainDefinition(
        brain_id="brain_alpha",
        name="Alpha & Beta",
        research_question="Does the edge persist?",
        created_by="tester",
        created_at="2026-08-19T00:00:00+00:00",
    )
    item = ResearchBrainListItem(
        definition=definition,
        membership_count=2,
        succeeded_count=2,
        failed_count=0,
        drift_warning_count=0,
        unassessed_count=0,
        conditioning_readiness="READY",
    )

    html = _inject_brain_discovery_selector("<html><body>Brains</body></html>", (item,))

    assert 'name="brain_id"' in html
    assert 'value="brain_alpha"' in html
    assert "Alpha &amp; Beta" in html
    assert 'style="display:none"' in html
