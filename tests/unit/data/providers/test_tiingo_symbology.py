from __future__ import annotations

import pytest

from trade_scout.data.providers.tiingo_symbology import (
    TiingoSymbologyError,
    build_tiingo_query_symbol_links,
    tiingo_query_symbol,
)


def test_audited_share_class_overrides_are_transport_only() -> None:
    assert tiingo_query_symbol("BRK.B") == "BRK-B"
    assert tiingo_query_symbol("BF.B") == "BF-B"
    assert tiingo_query_symbol("aapl") == "AAPL"


def test_unknown_dotted_symbol_fails_closed() -> None:
    with pytest.raises(TiingoSymbologyError, match="explicit audited mapping"):
        tiingo_query_symbol("TEST.X")


def test_universe_translation_detects_provider_symbol_collision() -> None:
    with pytest.raises(TiingoSymbologyError, match="collision"):
        build_tiingo_query_symbol_links(("BRK.B", "BRK-B"))


def test_links_preserve_source_symbol_separately_from_query_symbol() -> None:
    links = build_tiingo_query_symbol_links(("AAPL", "BRK.B", "BF.B"))
    assert [(item.source_symbol, item.query_symbol, item.translated) for item in links] == [
        ("AAPL", "AAPL", False),
        ("BRK.B", "BRK-B", True),
        ("BF.B", "BF-B", True),
    ]
