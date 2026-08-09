"""Semantic review of bounded EODHD campaign evidence for provider acceptance."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from trade_scout.data.provider_acceptance import (
    ProviderAcceptanceCriterion,
    ProviderAcceptanceEvidence,
    ProviderEvidenceStatus,
)


class EodhdCampaignReviewError(ValueError):
    """Raised when persisted campaign evidence is malformed or internally inconsistent."""


@dataclass(frozen=True, slots=True)
class EodhdCampaignReview:
    """Conservative semantic assessment of one completed or partial EODHD campaign."""

    campaign_id: str
    complete: bool
    expected_case_count: int
    completed_case_count: int
    evidence: tuple[ProviderAcceptanceEvidence, ...]


def review_eodhd_campaign(output_root: Path) -> EodhdCampaignReview:
    """Review persisted EODHD campaign evidence without promoting provider acceptance.

    The reviewer only assesses criteria directly exercised by the bounded campaign. It does not
    infer licensing rights, secondary-provider agreement, daily-update determinism, or
    representative-universe coverage from a small live sample.
    """

    summaries = tuple((output_root / "report").glob("*/campaign-summary.json"))
    if len(summaries) != 1:
        report_root = output_root / "report"
        message = f"expected one campaign summary in {report_root}; found {len(summaries)}"
        raise EodhdCampaignReviewError(message)
    summary_path = summaries[0]
    summary = _read_object(summary_path)
    if summary.get("evaluation_id") != "eodhd-provider-evidence-campaign-v0.1":
        raise EodhdCampaignReviewError("unsupported EODHD campaign summary evaluation_id")
    if summary.get("provider_id") != "eodhd":
        raise EodhdCampaignReviewError("campaign summary provider_id must be eodhd")

    campaign_id = _required_text(summary, "campaign_id")
    expected_case_count = _required_int(summary, "expected_case_count")
    completed_ids = _required_text_list(summary, "completed_case_ids")
    complete = summary.get("complete") is True
    if len(completed_ids) > expected_case_count:
        raise EodhdCampaignReviewError("completed case count exceeds expected case count")
    if complete != (len(completed_ids) == expected_case_count):
        raise EodhdCampaignReviewError(
            "campaign completion flag conflicts with completed case count"
        )

    campaign_root = output_root / "campaign-state" / campaign_id
    spec = _read_object(campaign_root / "campaign.json")
    if spec.get("campaign_id") != campaign_id:
        raise EodhdCampaignReviewError("campaign specification identity does not match summary")
    raw_cases = spec.get("cases")
    if not isinstance(raw_cases, list) or len(raw_cases) != expected_case_count:
        raise EodhdCampaignReviewError("campaign specification case count does not match summary")

    expected_by_id: dict[str, dict[str, object]] = {}
    for raw_case in raw_cases:
        if not isinstance(raw_case, dict):
            raise EodhdCampaignReviewError("campaign case specification must be an object")
        case_id = _required_text(raw_case, "case_id")
        if case_id in expected_by_id:
            raise EodhdCampaignReviewError(f"duplicate campaign case_id: {case_id}")
        expected_by_id[case_id] = raw_case

    completed_results: list[dict[str, object]] = []
    for case_id in completed_ids:
        expected = expected_by_id.get(case_id)
        if expected is None:
            raise EodhdCampaignReviewError(f"summary references unknown campaign case: {case_id}")
        result = _read_object(campaign_root / "cases" / case_id / "result.json")
        _validate_case_result(case_id, expected, result)
        completed_results.append(result)

    evidence = _derive_evidence(
        output_root=output_root,
        complete=complete,
        expected_case_count=expected_case_count,
        completed_results=tuple(completed_results),
    )
    return EodhdCampaignReview(
        campaign_id=campaign_id,
        complete=complete,
        expected_case_count=expected_case_count,
        completed_case_count=len(completed_results),
        evidence=evidence,
    )


def _derive_evidence(
    *,
    output_root: Path,
    complete: bool,
    expected_case_count: int,
    completed_results: tuple[dict[str, object], ...],
) -> tuple[ProviderAcceptanceEvidence, ...]:
    reference = str(output_root)
    all_have_raw = bool(completed_results) and all(
        isinstance(item.get("raw_batch_ids"), list) and bool(item["raw_batch_ids"])
        for item in completed_results
    )
    all_have_canonical = bool(completed_results) and all(
        _positive_int(item.get("bar_count"))
        and item.get("bar_count") == item.get("canonical_record_count")
        and _nonempty_text(item.get("canonical_content_checksum_sha256"))
        and _nonempty_text(item.get("canonical_parquet_checksum_sha256"))
        for item in completed_results
    )
    all_have_identity = bool(completed_results) and all(
        _nonempty_text(item.get("provider_instrument_id")) for item in completed_results
    )
    has_delisted = any(item.get("expected_state") == "delisted" for item in completed_results)
    has_actions = any(_positive_int(item.get("action_count")) for item in completed_results)

    return (
        ProviderAcceptanceEvidence(
            criterion=ProviderAcceptanceCriterion.REPRODUCIBLE_HISTORICAL_BACKFILL,
            status=(
                ProviderEvidenceStatus.DEMONSTRATED
                if complete and all_have_canonical
                else ProviderEvidenceStatus.PARTIAL
            ),
            evidence=(reference,),
            note=(
                f"Bounded campaign completed {len(completed_results)}/{expected_case_count} cases "
                "through the canonical historical path. This demonstrates only the configured "
                "cases, not representative-universe completeness."
            ),
        ),
        ProviderAcceptanceEvidence(
            criterion=ProviderAcceptanceCriterion.RAW_PRESERVATION,
            status=(
                ProviderEvidenceStatus.DEMONSTRATED
                if complete and all_have_raw
                else ProviderEvidenceStatus.PARTIAL
            ),
            evidence=(reference,),
            note="Completed cases retain raw batch identities before canonical promotion.",
        ),
        ProviderAcceptanceEvidence(
            criterion=ProviderAcceptanceCriterion.IDENTIFIER_AND_SYMBOL_MAPPING,
            status=(
                ProviderEvidenceStatus.PARTIAL
                if all_have_identity
                else ProviderEvidenceStatus.NOT_DEMONSTRATED
            ),
            evidence=(reference,) if all_have_identity else (),
            note=(
                "Campaign cases resolved provider instrument identities, but the bounded "
                "campaign cannot demonstrate broad historical symbol/identifier coverage."
            ),
        ),
        ProviderAcceptanceEvidence(
            criterion=ProviderAcceptanceCriterion.CORPORATE_ACTION_HANDLING,
            status=(
                ProviderEvidenceStatus.PARTIAL
                if has_actions
                else ProviderEvidenceStatus.NOT_DEMONSTRATED
            ),
            evidence=(reference,) if has_actions else (),
            note=(
                "At least one completed case exercised non-empty split/dividend handling "
                "through canonical promotion."
                if has_actions
                else "No completed campaign case contains a corporate action yet."
            ),
        ),
        ProviderAcceptanceEvidence(
            criterion=ProviderAcceptanceCriterion.DELISTING_COVERAGE,
            status=(
                ProviderEvidenceStatus.PARTIAL
                if has_delisted
                else ProviderEvidenceStatus.NOT_DEMONSTRATED
            ),
            evidence=(reference,) if has_delisted else (),
            note=(
                "A delisted security is included in the completed bounded evidence. Broader "
                "delisting coverage remains uncharacterized."
                if has_delisted
                else "No delisted campaign case has completed."
            ),
        ),
        ProviderAcceptanceEvidence(
            criterion=ProviderAcceptanceCriterion.CANONICAL_NORMALIZATION_QUALITY,
            status=(
                ProviderEvidenceStatus.DEMONSTRATED
                if complete and all_have_canonical
                else ProviderEvidenceStatus.PARTIAL
            ),
            evidence=(reference,),
            note=(
                "Configured cases completed normalization, quality gating, immutable canonical "
                "promotion, record-count reconciliation, and checksum generation."
            ),
        ),
    )


def _validate_case_result(
    case_id: str,
    expected: dict[str, object],
    result: dict[str, object],
) -> None:
    if result.get("case_id") != case_id:
        raise EodhdCampaignReviewError(f"result identity mismatch for case {case_id}")
    expected_state = "active" if expected.get("expected_active") is True else "delisted"
    checks = {
        "symbol": expected.get("symbol"),
        "requested_start": expected.get("start"),
        "requested_end": expected.get("end"),
        "expected_state": expected_state,
        "dataset_version": expected.get("dataset_version"),
    }
    for field, expected_value in checks.items():
        if result.get(field) != expected_value:
            raise EodhdCampaignReviewError(f"case {case_id} result conflicts on {field}")
    if not _positive_int(result.get("bar_count")):
        raise EodhdCampaignReviewError(f"case {case_id} must contain historical bars")
    if result.get("canonical_record_count") != result.get("bar_count"):
        raise EodhdCampaignReviewError(
            f"case {case_id} canonical record count does not match bar count"
        )


def _read_object(path: Path) -> dict[str, object]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise EodhdCampaignReviewError(f"cannot read campaign evidence: {path}") from exc
    except json.JSONDecodeError as exc:
        raise EodhdCampaignReviewError(f"campaign evidence is invalid JSON: {path}") from exc
    if not isinstance(payload, dict):
        raise EodhdCampaignReviewError(f"campaign evidence root must be an object: {path}")
    return payload


def _required_text(payload: dict[str, object], field: str) -> str:
    value = payload.get(field)
    if not _nonempty_text(value):
        raise EodhdCampaignReviewError(f"campaign evidence field {field} must be non-empty text")
    return str(value)


def _required_int(payload: dict[str, object], field: str) -> int:
    value = payload.get(field)
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise EodhdCampaignReviewError(
            f"campaign evidence field {field} must be a non-negative integer"
        )
    return value


def _required_text_list(payload: dict[str, object], field: str) -> tuple[str, ...]:
    value = payload.get(field)
    if not isinstance(value, list) or not all(_nonempty_text(item) for item in value):
        raise EodhdCampaignReviewError(f"campaign evidence field {field} must be a text array")
    items = tuple(str(item) for item in value)
    if len(set(items)) != len(items):
        raise EodhdCampaignReviewError(f"campaign evidence field {field} contains duplicates")
    return items


def _positive_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _nonempty_text(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())
