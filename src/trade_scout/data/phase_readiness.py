"""Combined Phase 1 readiness gate tying data-foundation and provider acceptance together."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from trade_scout.data.acceptance import DataFoundationAcceptanceReport
from trade_scout.data.acceptance_ledger import AcceptanceLedger, load_acceptance_ledger
from trade_scout.data.provider_acceptance import ProviderAcceptanceReport, load_provider_acceptance


class PhaseReadinessError(RuntimeError):
    """Raised when Phase 2 is requested before every Phase 1 prerequisite is accepted."""


@dataclass(frozen=True, slots=True)
class Phase1ReadinessReport:
    """Explicit combined gate for crossing from Data Foundation into Feature Foundation."""

    data_assessment_version: str
    data_report: DataFoundationAcceptanceReport
    provider_report: ProviderAcceptanceReport

    @property
    def phase_complete(self) -> bool:
        """Phase 1 closes only when both the data gate and canonical provider gate close."""

        return self.data_report.phase_complete and self.provider_report.accepted

    @property
    def blockers(self) -> tuple[str, ...]:
        """Return stable human-readable blocker identifiers without hiding either gate."""

        items = [
            f"data:{item.criterion.value}:{item.status.value}" for item in self.data_report.unresolved
        ]
        items.extend(
            f"provider:{item.criterion.value}:{item.status.value}"
            for item in self.provider_report.unresolved
        )
        return tuple(items)

    def require_complete(self) -> None:
        """Fail visibly if downstream phase work attempts to cross an incomplete gate."""

        if self.phase_complete:
            return
        details = ", ".join(self.blockers)
        raise PhaseReadinessError(f"Phase 1 is not ready for Phase 2: {details}")


def evaluate_phase1_readiness(
    data_ledger: AcceptanceLedger,
    provider_report: ProviderAcceptanceReport,
) -> Phase1ReadinessReport:
    """Combine already validated ledgers without weakening either underlying assessment."""

    return Phase1ReadinessReport(
        data_assessment_version=data_ledger.assessment_version,
        data_report=data_ledger.report,
        provider_report=provider_report,
    )


def load_phase1_readiness(
    *,
    data_ledger_path: Path,
    provider_ledger_path: Path,
) -> Phase1ReadinessReport:
    """Load both checked-in acceptance ledgers and return their combined Phase 1 gate."""

    return evaluate_phase1_readiness(
        load_acceptance_ledger(data_ledger_path),
        load_provider_acceptance(provider_ledger_path),
    )
