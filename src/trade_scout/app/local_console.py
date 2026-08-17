"""Small local HTTP shell for the evidence-backed Trade Scout application.

The server is deliberately presentation-only. Normal console requests rebuild the application
snapshot from persisted application-service evidence. Research routes delegate analytics to
injected application services backed by canonical data; the HTTP layer never calls market-data
providers or calculates research results itself. The default bind is loopback-only.
"""

from __future__ import annotations

import ipaddress
import json
from dataclasses import asdict, dataclass, is_dataclass
from datetime import UTC, date, datetime
from enum import Enum
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, cast
from urllib.parse import parse_qs, urlsplit

from trade_scout.app.application_snapshot_service import build_phase1_application_snapshot
from trade_scout.app.data_health_service import DataHealthSourcePaths, build_data_health_summary
from trade_scout.app.edge_explorer_service import (
    EdgeExplorerError,
    EdgeExplorerRequest,
    EdgeExplorerService,
    EdgeExplorerSource,
)
from trade_scout.app.edge_explorer_surface import render_edge_explorer_html
from trade_scout.app.entry_strategy_registry import EntryFamily, available_entry_strategies
from trade_scout.app.exit_policy_lab_service import (
    ExitPolicyLabError,
    ExitPolicyLabRequest,
    ExitPolicyLabService,
    parse_multiple_grid,
    parse_percentage_grid,
)
from trade_scout.app.exit_policy_lab_surface import render_exit_policy_lab_html
from trade_scout.app.operational_surface import render_operational_application_html
from trade_scout.app.risk_research_service import (
    RiskResearchError,
    RiskResearchRequest,
    RiskResearchService,
)
from trade_scout.app.risk_research_surface import render_risk_research_html
from trade_scout.app.strategy_builder_service import (
    StrategyBuilderError,
    StrategyBuilderRequest,
    StrategyBuilderService,
    StrategyBuilderSource,
)
from trade_scout.app.strategy_builder_surface import render_strategy_builder_html
from trade_scout.app.universe_research_service import (
    UniverseResearchError,
    UniverseResearchRequest,
    UniverseResearchService,
    UniverseResearchSource,
)
from trade_scout.app.universe_research_surface import render_universe_research_html
from trade_scout.patterns.consolidation_breakout import TrendFilter
from trade_scout.statistics.strategy_research import available_strategy_features


class LocalConsoleConfigurationError(ValueError):
    """Raised when the local console is configured unsafely or inconsistently."""


@dataclass(frozen=True, slots=True)
class LocalConsoleConfig:
    """Read-only sources and presentation settings for the local console."""

    sources: DataHealthSourcePaths
    build_label: str = "local-console-v0.1"
    refresh_seconds: int = 15
    edge_explorer_source: EdgeExplorerSource | None = None
    universe_research_source: UniverseResearchSource | None = None
    strategy_builder_source: StrategyBuilderSource | None = None

    def __post_init__(self) -> None:
        if not self.build_label.strip():
            raise LocalConsoleConfigurationError("build_label must be non-empty")
        if not 2 <= self.refresh_seconds <= 3600:
            raise LocalConsoleConfigurationError("refresh_seconds must be between 2 and 3600")


@dataclass(frozen=True, slots=True)
class ConsoleResponse:
    """Framework-independent response used by both HTTP serving and unit tests."""

    status_code: int
    content_type: str
    body: bytes
    headers: tuple[tuple[str, str], ...] = ()


def build_console_response(
    request_target: str,
    config: LocalConsoleConfig,
    *,
    generated_at: datetime | None = None,
) -> ConsoleResponse:
    """Build one safe response from persisted application evidence."""

    now = generated_at or datetime.now(UTC)
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("generated_at must be timezone-aware")
    parsed_target = urlsplit(request_target)
    path = parsed_target.path

    if path == "/favicon.ico":
        return ConsoleResponse(
            status_code=HTTPStatus.NO_CONTENT,
            content_type="image/x-icon",
            body=b"",
            headers=_security_headers(),
        )

    allowed = {
        "/",
        "/index.html",
        "/research/edge",
        "/research/universe",
        "/research/risk",
        "/research/exits",
        "/research/strategy",
        "/api/snapshot.json",
        "/api/data-health.json",
        "/healthz",
    }
    if path not in allowed:
        return _json_response(
            HTTPStatus.NOT_FOUND,
            {"error": "not_found", "path": path},
        )

    if path == "/research/edge":
        return _edge_explorer_response(parsed_target.query, config)
    if path == "/research/universe":
        return _universe_research_response(parsed_target.query, config)
    if path == "/research/risk":
        return _risk_research_response(parsed_target.query, config)
    if path == "/research/exits":
        return _exit_policy_lab_response(parsed_target.query, config)
    if path == "/research/strategy":
        return _strategy_builder_response(parsed_target.query, config)

    health = build_data_health_summary(config.sources)
    snapshot = build_phase1_application_snapshot(
        health,
        generated_at=now,
        build_label=config.build_label,
    )

    if path in {"/", "/index.html"}:
        html = render_operational_application_html(snapshot)
        html = _with_edge_explorer_link(html, enabled=config.edge_explorer_source is not None)
        html = _with_universe_research_link(
            html,
            enabled=config.universe_research_source is not None,
        )
        html = _with_risk_research_link(
            html,
            enabled=config.universe_research_source is not None,
        )
        html = _with_exit_policy_lab_link(
            html,
            enabled=config.universe_research_source is not None,
        )
        html = _with_strategy_builder_link(
            html,
            enabled=config.strategy_builder_source is not None,
        )
        html = _with_local_console_metadata(html, refresh_seconds=config.refresh_seconds)
        return ConsoleResponse(
            status_code=HTTPStatus.OK,
            content_type="text/html; charset=utf-8",
            body=html.encode("utf-8"),
            headers=_security_headers(),
        )
    if path == "/api/snapshot.json":
        return _json_response(HTTPStatus.OK, _json_ready(snapshot))
    if path == "/api/data-health.json":
        return _json_response(HTTPStatus.OK, _json_ready(health))
    return _json_response(
        HTTPStatus.OK,
        {
            "service": "trade-scout-local-console",
            "status": "ok",
            "generated_at": now.isoformat(),
            "data_health_state": health.state.value,
            "dataset_version": health.dataset_version,
            "scanner_freshness_gate": health.scanner_freshness_gate.value,
            "phase_blocker_count": len(health.phase_blockers),
            "review_work_item_count": health.review_work_item_count,
        },
    )


def validate_bind_host(host: str, *, allow_remote: bool) -> None:
    """Reject accidental network exposure unless the caller opts in explicitly."""

    normalized = host.strip().lower()
    if not normalized:
        raise LocalConsoleConfigurationError("host must be non-empty")
    if allow_remote or normalized == "localhost":
        return
    try:
        address = ipaddress.ip_address(normalized)
    except ValueError as exc:
        raise LocalConsoleConfigurationError(
            "non-IP host names require --allow-remote; use 127.0.0.1 for local access"
        ) from exc
    if not address.is_loopback:
        raise LocalConsoleConfigurationError(
            "refusing non-loopback bind without explicit --allow-remote"
        )


def serve_local_console(
    config: LocalConsoleConfig,
    *,
    host: str = "127.0.0.1",
    port: int = 8765,
    allow_remote: bool = False,
) -> None:
    """Serve the local console until interrupted by the operator."""

    validate_bind_host(host, allow_remote=allow_remote)
    if not 1 <= port <= 65535:
        raise LocalConsoleConfigurationError("port must be between 1 and 65535")
    handler_type = _handler_for(config)
    server = ThreadingHTTPServer((host, port), handler_type)
    try:
        server.serve_forever(poll_interval=0.25)
    finally:
        server.server_close()


def _handler_for(config: LocalConsoleConfig) -> type[BaseHTTPRequestHandler]:
    class LocalConsoleHandler(BaseHTTPRequestHandler):
        server_version = "TradeScoutLocalConsole/0.1"

        def do_GET(self) -> None:
            self._respond(head_only=False)

        def do_HEAD(self) -> None:
            self._respond(head_only=True)

        def do_POST(self) -> None:
            response = _json_response(
                HTTPStatus.METHOD_NOT_ALLOWED,
                {"error": "method_not_allowed", "allowed": ["GET", "HEAD"]},
                extra_headers=(("Allow", "GET, HEAD"),),
            )
            self._send(response, head_only=False)

        def _respond(self, *, head_only: bool) -> None:
            try:
                response = build_console_response(self.path, config)
            except Exception as exc:
                response = _json_response(
                    HTTPStatus.INTERNAL_SERVER_ERROR,
                    {
                        "error": "application_unavailable",
                        "error_type": type(exc).__name__,
                        "message": str(exc),
                    },
                )
            self._send(response, head_only=head_only)

        def _send(self, response: ConsoleResponse, *, head_only: bool) -> None:
            self.send_response(response.status_code)
            self.send_header("Content-Type", response.content_type)
            self.send_header("Content-Length", str(len(response.body)))
            for name, value in response.headers:
                self.send_header(name, value)
            self.end_headers()
            if not head_only and response.body:
                self.wfile.write(response.body)

    return LocalConsoleHandler


def _edge_explorer_response(query: str, config: LocalConsoleConfig) -> ConsoleResponse:
    source = config.edge_explorer_source
    if source is None:
        html = render_edge_explorer_html(
            symbols=(),
            error=(
                "Edge Explorer is not configured for this console. Use an operator workspace "
                "with a selected canonical dataset and reviewed identity candidate."
            ),
        )
        return _html_response(HTTPStatus.SERVICE_UNAVAILABLE, html)
    try:
        symbols = source.available_symbols()
    except Exception as exc:
        html = render_edge_explorer_html(
            symbols=(),
            error=f"Cannot load reviewed symbol scope: {type(exc).__name__}: {exc}",
        )
        return _html_response(HTTPStatus.SERVICE_UNAVAILABLE, html)
    parameters = parse_qs(query, keep_blank_values=False)
    if "symbol" not in parameters:
        return _html_response(HTTPStatus.OK, render_edge_explorer_html(symbols=symbols))
    request: EdgeExplorerRequest | None = None
    try:
        request = EdgeExplorerRequest(
            symbol=_one(parameters, "symbol"),
            strategy_id=_one(parameters, "strategy", default="consolidation_breakout"),
            horizon=int(_one(parameters, "horizon", default="20")),
            duration=int(_one(parameters, "duration", default="20")),
            max_range_pct=float(_one(parameters, "max_range_pct", default="12")) / 100.0,
            trend_filter=TrendFilter(
                _one(parameters, "trend_filter", default=TrendFilter.ABOVE_RISING_SMA_200.value)
            ),
        )
        report = EdgeExplorerService(source).run(request)
        html = render_edge_explorer_html(symbols=symbols, request=request, report=report)
        return _html_response(HTTPStatus.OK, html)
    except (ValueError, EdgeExplorerError) as exc:
        html = render_edge_explorer_html(symbols=symbols, request=request, error=str(exc))
        return _html_response(HTTPStatus.BAD_REQUEST, html)


def _universe_research_response(query: str, config: LocalConsoleConfig) -> ConsoleResponse:
    source = config.universe_research_source
    if source is None:
        html = render_universe_research_html(
            universes=(),
            error=(
                "Universe Research Analyzer is not configured for this console. Use an operator "
                "workspace with a selected canonical dataset and reviewed identity candidate."
            ),
        )
        return _html_response(HTTPStatus.SERVICE_UNAVAILABLE, html)
    try:
        universes = source.available_universes()
    except Exception as exc:
        html = render_universe_research_html(
            universes=(),
            error=f"Cannot load research-universe scope: {type(exc).__name__}: {exc}",
        )
        return _html_response(HTTPStatus.SERVICE_UNAVAILABLE, html)
    parameters = parse_qs(query, keep_blank_values=False)
    if "universe" not in parameters:
        return _html_response(HTTPStatus.OK, render_universe_research_html(universes=universes))
    request: UniverseResearchRequest | None = None
    try:
        request = UniverseResearchRequest(
            universe_id=_one(parameters, "universe", default="reviewed_canonical"),
            strategy_id=_one(parameters, "strategy", default="consolidation_breakout"),
            lookback_years=int(_one(parameters, "lookback_years", default="2")),
            horizon=int(_one(parameters, "horizon", default="20")),
            duration=int(_one(parameters, "duration", default="20")),
            max_range_pct=float(_one(parameters, "max_range_pct", default="12")) / 100.0,
            trend_filter=TrendFilter(
                _one(parameters, "trend_filter", default=TrendFilter.ABOVE_SMA_50_100_200.value)
            ),
            min_breakout_volume_ratio=_optional_volume_ratio(
                _one(parameters, "volume_ratio", default="none")
            ),
        )
        report = UniverseResearchService(source).run(request)
        html = render_universe_research_html(
            universes=universes,
            request=request,
            report=report,
        )
        return _html_response(HTTPStatus.OK, html)
    except (ValueError, UniverseResearchError) as exc:
        html = render_universe_research_html(
            universes=universes,
            request=request,
            error=str(exc),
        )
        return _html_response(HTTPStatus.BAD_REQUEST, html)


def _risk_research_response(query: str, config: LocalConsoleConfig) -> ConsoleResponse:
    source = config.universe_research_source
    if source is None:
        html = render_risk_research_html(
            universes=(),
            error=(
                "Risk Research is not configured for this console. Use an operator workspace "
                "with a selected canonical dataset and reviewed identity candidate."
            ),
        )
        return _html_response(HTTPStatus.SERVICE_UNAVAILABLE, html)
    try:
        universes = source.available_universes()
    except Exception as exc:
        html = render_risk_research_html(
            universes=(),
            error=f"Cannot load research-universe scope: {type(exc).__name__}: {exc}",
        )
        return _html_response(HTTPStatus.SERVICE_UNAVAILABLE, html)
    parameters = parse_qs(query, keep_blank_values=False)
    if "universe" not in parameters:
        return _html_response(HTTPStatus.OK, render_risk_research_html(universes=universes))
    request: RiskResearchRequest | None = None
    try:
        request = RiskResearchRequest(
            universe_id=_one(parameters, "universe", default="reviewed_canonical"),
            lookback_years=int(_one(parameters, "lookback_years", default="2")),
            horizon=int(_one(parameters, "horizon", default="20")),
            duration=int(_one(parameters, "duration", default="20")),
            max_range_pct=float(_one(parameters, "max_range_pct", default="12")) / 100.0,
            trend_filter=TrendFilter(
                _one(parameters, "trend_filter", default=TrendFilter.ABOVE_SMA_50_100_200.value)
            ),
            min_breakout_volume_ratio=_optional_volume_ratio(
                _one(parameters, "volume_ratio", default="none")
            ),
            cost_bps_per_side=float(_one(parameters, "cost_bps", default="0")),
        )
        report = RiskResearchService(source).run(request)
        html = render_risk_research_html(
            universes=universes,
            request=request,
            report=report,
        )
        return _html_response(HTTPStatus.OK, html)
    except (ValueError, RiskResearchError) as exc:
        html = render_risk_research_html(
            universes=universes,
            request=request,
            error=str(exc),
        )
        return _html_response(HTTPStatus.BAD_REQUEST, html)


def _exit_policy_lab_response(query: str, config: LocalConsoleConfig) -> ConsoleResponse:
    source = config.universe_research_source
    if source is None:
        html = render_exit_policy_lab_html(
            universes=(),
            error=(
                "Exit Policy Lab is not configured for this console. Use an operator workspace "
                "with a selected canonical dataset and reviewed identity candidate."
            ),
        )
        return _html_response(HTTPStatus.SERVICE_UNAVAILABLE, html)
    try:
        universes = source.available_universes()
    except Exception as exc:
        html = render_exit_policy_lab_html(
            universes=(),
            error=f"Cannot load research-universe scope: {type(exc).__name__}: {exc}",
        )
        return _html_response(HTTPStatus.SERVICE_UNAVAILABLE, html)
    parameters = parse_qs(query, keep_blank_values=True)
    if "universe" not in parameters:
        return _html_response(HTTPStatus.OK, render_exit_policy_lab_html(universes=universes))
    request: ExitPolicyLabRequest | None = None
    try:
        request = ExitPolicyLabRequest(
            universe_id=_one(parameters, "universe", default="reviewed_canonical"),
            lookback_years=int(_one(parameters, "lookback_years", default="2")),
            horizon=int(_one(parameters, "horizon", default="20")),
            duration=int(_one(parameters, "duration", default="20")),
            max_range_pct=float(_one(parameters, "max_range_pct", default="12")) / 100.0,
            trend_filter=TrendFilter(
                _one(parameters, "trend_filter", default=TrendFilter.ABOVE_SMA_50_100_200.value)
            ),
            min_breakout_volume_ratio=_optional_volume_ratio(
                _one(parameters, "volume_ratio", default="none")
            ),
            fixed_percentages=parse_percentage_grid(
                _one(parameters, "fixed_stops", default="2,3,4,5,7,10")
            ),
            trailing_percentages=parse_percentage_grid(
                _one(parameters, "trailing_stops", default="2,3,5,7,10")
            ),
            atr_multiples=parse_multiple_grid(
                _one(parameters, "atr_stops", default="1,1.5,2,2.5,3")
            ),
            trailing_atr_multiples=parse_multiple_grid(
                _one(parameters, "trailing_atr", default="1,1.5,2,2.5,3")
            ),
            entry_slippage_bps=float(_one(parameters, "entry_slip", default="0")),
            exit_slippage_bps=float(_one(parameters, "exit_slip", default="0")),
            stop_slippage_bps=float(_one(parameters, "stop_slip", default="0")),
            commission_bps_per_side=float(_one(parameters, "commission", default="0")),
        )
        report = ExitPolicyLabService(source).run(request)
        html = render_exit_policy_lab_html(
            universes=universes,
            request=request,
            report=report,
        )
        return _html_response(HTTPStatus.OK, html)
    except (ValueError, ExitPolicyLabError) as exc:
        html = render_exit_policy_lab_html(
            universes=universes,
            request=request,
            error=str(exc),
        )
        return _html_response(HTTPStatus.BAD_REQUEST, html)


def _strategy_builder_response(query: str, config: LocalConsoleConfig) -> ConsoleResponse:
    source = config.strategy_builder_source
    entries = available_entry_strategies()
    features = available_strategy_features()
    if source is None:
        html = render_strategy_builder_html(
            universes=(),
            entries=entries,
            features=features,
            error=(
                "Strategy Builder is not configured for this console. Use an operator workspace "
                "with a selected canonical dataset and reviewed identity candidate."
            ),
        )
        return _html_response(HTTPStatus.SERVICE_UNAVAILABLE, html)
    try:
        universes = source.available_universes()
    except Exception as exc:
        html = render_strategy_builder_html(
            universes=(),
            entries=entries,
            features=features,
            error=f"Cannot load research-universe scope: {type(exc).__name__}: {exc}",
        )
        return _html_response(HTTPStatus.SERVICE_UNAVAILABLE, html)
    parameters = parse_qs(query, keep_blank_values=True)
    if "universe" not in parameters:
        return _html_response(
            HTTPStatus.OK,
            render_strategy_builder_html(
                universes=universes,
                entries=entries,
                features=features,
            ),
        )
    request: StrategyBuilderRequest | None = None
    try:
        request = StrategyBuilderRequest(
            universe_id=_one(parameters, "universe", default="reviewed_canonical"),
            entry_family=EntryFamily(
                _one(parameters, "entry_family", default=EntryFamily.FEATURE_EXPRESSION.value)
            ),
            lookback_years=int(_one(parameters, "lookback_years", default="2")),
            horizon=int(_one(parameters, "horizon", default="20")),
            expression=_one(
                parameters,
                "expression",
                default=(
                    "return_20 >= 0.05 and relative_volume_20 >= 1.5 "
                    "and distance_sma_200_pct > 0"
                ),
            ),
            rank_feature=_one(parameters, "rank_feature", default="return_20"),
            descending=_one(parameters, "rank_direction", default="desc") == "desc",
            per_session_limit=int(_one(parameters, "per_session_limit", default="25")),
            duration=int(_one(parameters, "duration", default="20")),
            max_range_pct=float(_one(parameters, "max_range_pct", default="12")) / 100.0,
            trend_filter=TrendFilter(
                _one(parameters, "trend_filter", default=TrendFilter.ABOVE_SMA_50_100_200.value)
            ),
            min_breakout_volume_ratio=_optional_volume_ratio(
                _one(parameters, "volume_ratio", default="none")
            ),
            fixed_percentages=parse_percentage_grid(
                _one(parameters, "fixed_stops", default="2,3,4,5,7,10")
            ),
            trailing_percentages=parse_percentage_grid(
                _one(parameters, "trailing_stops", default="2,3,5,7,10")
            ),
            atr_multiples=parse_multiple_grid(
                _one(parameters, "atr_stops", default="1,1.5,2,2.5,3")
            ),
            trailing_atr_multiples=parse_multiple_grid(
                _one(parameters, "trailing_atr", default="1,1.5,2,2.5,3")
            ),
            entry_slippage_bps=float(_one(parameters, "entry_slip", default="0")),
            exit_slippage_bps=float(_one(parameters, "exit_slip", default="0")),
            stop_slippage_bps=float(_one(parameters, "stop_slip", default="0")),
            commission_bps_per_side=float(_one(parameters, "commission", default="0")),
        )
        report = StrategyBuilderService(source).run(request)
        html = render_strategy_builder_html(
            universes=universes,
            entries=entries,
            features=features,
            request=request,
            report=report,
        )
        return _html_response(HTTPStatus.OK, html)
    except (ValueError, StrategyBuilderError) as exc:
        html = render_strategy_builder_html(
            universes=universes,
            entries=entries,
            features=features,
            request=request,
            error=str(exc),
        )
        return _html_response(HTTPStatus.BAD_REQUEST, html)


def _optional_volume_ratio(value: str) -> float | None:
    if value.strip().lower() == "none":
        return None
    result = float(value)
    if result <= 0:
        raise ValueError("volume_ratio must be positive or 'none'")
    return result


def _one(parameters: dict[str, list[str]], name: str, *, default: str | None = None) -> str:
    values = parameters.get(name)
    if not values:
        if default is None:
            raise ValueError(f"missing query parameter {name}")
        return default
    if len(values) != 1:
        raise ValueError(f"query parameter {name} must appear once")
    return values[0]


def _html_response(status: HTTPStatus, html: str) -> ConsoleResponse:
    return ConsoleResponse(
        status_code=status,
        content_type="text/html; charset=utf-8",
        body=html.encode("utf-8"),
        headers=_security_headers(),
    )


def _json_response(
    status: HTTPStatus,
    payload: object,
    *,
    extra_headers: tuple[tuple[str, str], ...] = (),
) -> ConsoleResponse:
    body = (json.dumps(payload, sort_keys=True, indent=2) + "\n").encode("utf-8")
    return ConsoleResponse(
        status_code=status,
        content_type="application/json; charset=utf-8",
        body=body,
        headers=_security_headers() + extra_headers,
    )


def _security_headers() -> tuple[tuple[str, str], ...]:
    return (
        ("Cache-Control", "no-store"),
        ("X-Content-Type-Options", "nosniff"),
        ("Referrer-Policy", "no-referrer"),
        (
            "Content-Security-Policy",
            "default-src 'none'; style-src 'unsafe-inline'; img-src 'self'; "
            "base-uri 'none'; frame-ancestors 'none'; form-action 'self'",
        ),
    )


def _with_local_console_metadata(html: str, *, refresh_seconds: int) -> str:
    marker = "<head>"
    if marker not in html:
        raise RuntimeError("application renderer omitted the HTML head element")
    metadata = (
        f'<meta http-equiv="refresh" content="{refresh_seconds}">\n'
        '<meta name="trade-scout-surface" content="local-evidence-console-v0.1">'
    )
    return html.replace(marker, marker + "\n" + metadata, 1)


def _with_edge_explorer_link(html: str, *, enabled: bool) -> str:
    return _with_research_link(
        html,
        href="/research/edge",
        label="Edge Explorer",
        enabled=enabled,
    )


def _with_universe_research_link(html: str, *, enabled: bool) -> str:
    return _with_research_link(
        html,
        href="/research/universe",
        label="Universe Research",
        enabled=enabled,
    )


def _with_risk_research_link(html: str, *, enabled: bool) -> str:
    return _with_research_link(
        html,
        href="/research/risk",
        label="Risk Research",
        enabled=enabled,
    )


def _with_exit_policy_lab_link(html: str, *, enabled: bool) -> str:
    return _with_research_link(
        html,
        href="/research/exits",
        label="Exit Policy Lab",
        enabled=enabled,
    )


def _with_strategy_builder_link(html: str, *, enabled: bool) -> str:
    return _with_research_link(
        html,
        href="/research/strategy",
        label="Strategy Builder",
        enabled=enabled,
    )


def _with_research_link(html: str, *, href: str, label: str, enabled: bool) -> str:
    marker = '<a href="#research">Research</a>'
    if marker not in html:
        raise RuntimeError("application renderer omitted Research navigation marker")
    resolved_label = label if enabled else f"{label} (not configured)"
    return html.replace(marker, marker + f'<a href="{href}">{resolved_label}</a>', 1)


def _json_ready(value: object) -> object:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Enum):
        return _json_ready(value.value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if is_dataclass(value) and not isinstance(value, type):
        return _json_ready(asdict(value))
    if isinstance(value, dict):
        return {str(key): _json_ready(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_ready(item) for item in value]
    return cast(Any, str(value))
