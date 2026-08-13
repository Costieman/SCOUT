"""Versioned quantitative measurements of market state."""

from trade_scout.features.contracts import (
    FeatureAvailabilityStatus,
    FeatureDefinition,
    FeatureSetDefinition,
    FeatureValue,
)
from trade_scout.features.initial import (
    ATR_FEATURE_NAME,
    ATR_FEATURE_VERSION,
    ATR_PERIOD,
    INITIAL_FEATURE_SET,
    INITIAL_FEATURE_SET_VERSION,
    FeatureInputError,
    compute_incremental_initial_feature_frame,
    compute_initial_feature_frame,
    initial_feature_definition_sha256,
)
from trade_scout.features.storage import (
    FeatureSnapshotConflictError,
    FeatureSnapshotIntegrityError,
    FeatureSnapshotManifest,
    FeatureSnapshotNotFoundError,
    FeatureSnapshotPromotionRequest,
    FeatureSnapshotStore,
)
from trade_scout.features.trend_context import (
    TrendContext,
    TrendContextConfig,
    qualifying_trend_indices,
)

__all__ = [
    "ATR_FEATURE_NAME",
    "ATR_FEATURE_VERSION",
    "ATR_PERIOD",
    "INITIAL_FEATURE_SET",
    "INITIAL_FEATURE_SET_VERSION",
    "FeatureAvailabilityStatus",
    "FeatureDefinition",
    "FeatureInputError",
    "FeatureSetDefinition",
    "FeatureSnapshotConflictError",
    "FeatureSnapshotIntegrityError",
    "FeatureSnapshotManifest",
    "FeatureSnapshotNotFoundError",
    "FeatureSnapshotPromotionRequest",
    "FeatureSnapshotStore",
    "FeatureValue",
    "TrendContext",
    "TrendContextConfig",
    "compute_incremental_initial_feature_frame",
    "compute_initial_feature_frame",
    "initial_feature_definition_sha256",
    "qualifying_trend_indices",
]
