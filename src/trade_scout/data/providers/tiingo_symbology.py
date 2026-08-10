"""Audited Tiingo query-symbol translation for provider transport boundaries.

Trade Scout preserves source/canonical symbol identity separately from provider query symbols.
Only explicitly reviewed exceptions are translated. Unknown dotted symbols fail closed rather than
being transformed heuristically.
"""

from __future__ import annotations

from dataclasses import dataclass


class TiingoSymbologyError(ValueError):
    """Raised when provider symbology is ambiguous, unsupported, or colliding."""


_AUDITED_QUERY_SYMBOL_OVERRIDES: dict[str, str] = {
    "BF.B": "BF-B",
    "BRK.B": "BRK-B",
}


@dataclass(frozen=True, slots=True)
class TiingoQuerySymbolLink:
    """One source-universe symbol and its provider-specific Tiingo query symbol."""

    source_symbol: str
    query_symbol: str
    translated: bool


def tiingo_query_symbol(source_symbol: str) -> str:
    """Return the audited Tiingo query symbol without changing source identity."""

    symbol = source_symbol.strip().upper()
    if not symbol:
        raise TiingoSymbologyError("source symbol must be non-empty")
    override = _AUDITED_QUERY_SYMBOL_OVERRIDES.get(symbol)
    if override is not None:
        return override
    if "." in symbol:
        raise TiingoSymbologyError(
            f"Tiingo query symbol requires an explicit audited mapping for {symbol}"
        )
    return symbol


def build_tiingo_query_symbol_links(
    source_symbols: tuple[str, ...],
) -> tuple[TiingoQuerySymbolLink, ...]:
    """Translate a universe and reject provider-symbol collisions before any requests."""

    seen_source: set[str] = set()
    query_to_source: dict[str, str] = {}
    links: list[TiingoQuerySymbolLink] = []
    for raw_symbol in source_symbols:
        source = raw_symbol.strip().upper()
        if not source:
            raise TiingoSymbologyError("source symbol must be non-empty")
        if source in seen_source:
            raise TiingoSymbologyError(f"duplicate source symbol {source}")
        seen_source.add(source)
        query = tiingo_query_symbol(source)
        existing = query_to_source.get(query)
        if existing is not None and existing != source:
            raise TiingoSymbologyError(
                f"Tiingo query-symbol collision: {existing} and {source} both map to {query}"
            )
        query_to_source[query] = source
        links.append(
            TiingoQuerySymbolLink(
                source_symbol=source,
                query_symbol=query,
                translated=query != source,
            )
        )
    return tuple(links)
