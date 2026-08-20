"""Lazy HTTP adapter for Research-Brain sequence guidance."""

from __future__ import annotations

import json
from http import HTTPStatus
from urllib.parse import parse_qs

from trade_scout.app.research_brain_service import ResearchBrainWorkbenchService
from trade_scout.app.research_sequence_guidance import guide_research_sequence_from_brain
from trade_scout.app.strategy_builder_experiments import StrategyBuilderExperimentRecorder


def build_research_sequence_guidance_json(
    query: str,
    recorder: StrategyBuilderExperimentRecorder,
) -> tuple[HTTPStatus, str]:
    """Resolve guidance only for the requested Brain, never for the full Brain inventory."""

    parameters = parse_qs(query, keep_blank_values=True)
    values = parameters.get("brain", [])
    if len(values) != 1 or not values[0].strip():
        return HTTPStatus.BAD_REQUEST, json.dumps({"error": "brain query parameter is required"})

    brain_id = values[0].strip()
    service = ResearchBrainWorkbenchService(
        experiment_root=recorder.experiment_root,
        brain_root=recorder.experiment_root.parent / "brains",
    )
    try:
        view = service.detail(brain_id)
        recommendation = guide_research_sequence_from_brain(view)
    except (OSError, ValueError, KeyError, RuntimeError) as exc:
        return HTTPStatus.BAD_REQUEST, json.dumps({"error": str(exc)})

    return HTTPStatus.OK, json.dumps(
        {
            "brain_id": brain_id,
            "stage": recommendation.stage,
            "headline": recommendation.headline,
            "rationale": recommendation.rationale,
            "next_dimension": recommendation.next_dimension,
        },
        sort_keys=True,
        separators=(",", ":"),
    )


__all__ = ["build_research_sequence_guidance_json"]
