"""Concrete market-data provider adapters isolated behind Trade Scout contracts."""

from trade_scout.data.providers.massive import (
    MassiveAdapter,
    MassiveApiError,
    MassiveHttpClient,
    MassiveIdentityError,
    MassiveResponseError,
    RawStoreCapture,
)
from trade_scout.data.providers.tiingo import (
    TiingoAdapter,
    TiingoApiError,
    TiingoHttpClient,
    TiingoIdentityError,
    TiingoInstrumentLink,
    TiingoResponseError,
    TiingoUnsupportedError,
)

__all__ = [
    "MassiveAdapter",
    "MassiveApiError",
    "MassiveHttpClient",
    "MassiveIdentityError",
    "MassiveResponseError",
    "RawStoreCapture",
    "TiingoAdapter",
    "TiingoApiError",
    "TiingoHttpClient",
    "TiingoIdentityError",
    "TiingoInstrumentLink",
    "TiingoResponseError",
    "TiingoUnsupportedError",
]
