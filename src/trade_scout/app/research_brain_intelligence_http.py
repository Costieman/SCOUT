"""HTTP adapter for current Research Brain intelligence.

This endpoint is deliberately read-only. It recomputes derived intelligence from the Brain's
current persisted membership each time it is requested so the Research Station does not depend on
a startup/background snapshot.
"""

from __future__ import annotations

import json
from http import HTTPStatus
from urllib.parse import parse_qs

from trade_scout.app.research_brain_intelligence import synthesize_research_brain
from trade_scout.app.research_brain_service import ResearchBrainWorkbenchService
from trade_scout.app.strategy_builder_experiments import StrategyBuilderExperimentRecorder


def build_research_brain_intelligence_json(
    query: str,
    recorder: StrategyBuilderExperimentRecorder,
) -> tuple[HTTPStatus, str]:
    """Return current derived Brain intelligence as a compact JSON document."""

    parameters = parse_qs(query, keep_blank_values=True)
    values = parameters.get("brain", [])
    if len(values) != 1 or not values[0].strip():
        return HTTPStatus.BAD_REQUEST, json.dumps(
            {"error": "query parameter 'brain' is required exactly once"},
            sort_keys=True,
            separators=(",", ":"),
        )
    service = ResearchBrainWorkbenchService(
        experiment_root=recorder.experiment_root,
        brain_root=recorder.experiment_root.parent / "brains",
    )
    intelligence = synthesize_research_brain(service.detail(values[0].strip()))
    payload = {
        "brain_id": intelligence.brain_id,
        "evidence_revision": intelligence.evidence_revision,
        "experiment_count": intelligence.experiment_count,
        "guidance": {
            "stage": intelligence.guidance.stage,
            "headline": intelligence.guidance.headline,
            "rationale": intelligence.guidance.rationale,
            "next_dimension": intelligence.guidance.next_dimension,
            "evidence_source": intelligence.guidance.evidence_source,
        },
        "supported_relationships": list(intelligence.supported_relationships),
        "unresolved_questions": list(intelligence.unresolved_questions),
        "contradictions": list(intelligence.contradictions),
        "rejected_or_failed_threads": list(intelligence.rejected_or_failed_threads),
        "readiness": {
            "label": intelligence.review.readiness_label,
            "explanation": intelligence.review.readiness_explanation,
        },
    }
    return HTTPStatus.OK, json.dumps(payload, sort_keys=True, separators=(",", ":"))


__all__ = ["build_research_brain_intelligence_json"]
