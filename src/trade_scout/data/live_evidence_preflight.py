"""Fail-closed preflight assessment for the Phase 1 live provider-evidence workflow."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Mapping


@dataclass(frozen=True, slots=True)
class LiveEvidencePreflight:
    """Local prerequisites required before provider calls are attempted."""

    eodhd_configured: bool
    tiingo_configured: bool
    representative_policy_present: bool
    provider_ledger_present: bool
    data_ledger_present: bool
    plan_present: bool

    @property
    def primary_ready(self) -> bool:
        return (
            self.eodhd_configured
            and self.representative_policy_present
            and self.provider_ledger_present
            and self.data_ledger_present
        )

    @property
    def secondary_ready(self) -> bool:
        return self.primary_ready and self.tiingo_configured

    @property
    def blockers(self) -> tuple[str, ...]:
        blockers: list[str] = []
        if not self.eodhd_configured:
            blockers.append("EODHD_API_TOKEN or EODHD_API_KEY is not configured")
        if not self.representative_policy_present:
            blockers.append("representative storage policy is missing")
        if not self.provider_ledger_present:
            blockers.append("EODHD provider-acceptance ledger is missing")
        if not self.data_ledger_present:
            blockers.append("data-foundation acceptance ledger is missing")
        return tuple(blockers)

    @property
    def notes(self) -> tuple[str, ...]:
        notes: list[str] = []
        if not self.plan_present:
            notes.append(
                "representative plan is absent and will be created from live EODHD inventory"
            )
        if not self.tiingo_configured:
            notes.append("TIINGO_API_KEY is absent; secondary validation will remain outstanding")
        return tuple(notes)


def assess_live_evidence_preflight(
    *,
    environment: Mapping[str, str],
    representative_policy: Path,
    provider_ledger: Path,
    data_ledger: Path,
    representative_plan: Path,
) -> LiveEvidencePreflight:
    """Assess only local prerequisites; no network or provider call is performed."""

    eodhd_configured = bool(
        environment.get("EODHD_API_TOKEN", "").strip()
        or environment.get("EODHD_API_KEY", "").strip()
    )
    tiingo_configured = bool(environment.get("TIINGO_API_KEY", "").strip())
    return LiveEvidencePreflight(
        eodhd_configured=eodhd_configured,
        tiingo_configured=tiingo_configured,
        representative_policy_present=representative_policy.is_file(),
        provider_ledger_present=provider_ledger.is_file(),
        data_ledger_present=data_ledger.is_file(),
        plan_present=representative_plan.is_file(),
    )
