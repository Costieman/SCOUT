"""Trade Scout canonical data contracts, provider boundary, and quality controls.

The data layer owns provider isolation, canonical meaning, provenance, and validation. It does not
calculate research features, detect patterns, or repair suspicious upstream observations silently.
"""

from trade_scout.data.contracts import (
    CorporateActionRecord,
    CorporateActionType,
    DailyBar,
    DatasetVersion,
    IngestionJobState,
    InstrumentId,
    InstrumentRecord,
    PriceRepresentation,
    QualityStatus,
    ResearchBar,
    SymbolHistoryRecord,
    to_research_bar,
)
from trade_scout.data.provider import ProviderAdapter
from trade_scout.data.quality import QualityIssue, QualityReport, QualityRule, validate_daily_bars

__all__ = [
    "CorporateActionRecord",
    "CorporateActionType",
    "DailyBar",
    "DatasetVersion",
    "IngestionJobState",
    "InstrumentId",
    "InstrumentRecord",
    "PriceRepresentation",
    "ProviderAdapter",
    "QualityIssue",
    "QualityReport",
    "QualityRule",
    "QualityStatus",
    "ResearchBar",
    "SymbolHistoryRecord",
    "to_research_bar",
    "validate_daily_bars",
]
