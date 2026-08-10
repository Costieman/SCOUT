"""Small local HTTP shell for the evidence-backed Trade Scout application.

The server is deliberately presentation-only. Every request rebuilds the application snapshot from
persisted application-service evidence; it never calls market-data providers, exposes raw provider
payloads, or implements analytical logic. The default bind is loopback-only.
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
from urllib.parse import urlsplit

from trade_scout.app.application_snapshot_service import build_phase1_application_snapshot
from trade_scout.app.data_health_service import DataHealthSourcePaths, build_data_health_summary
from trade_scout.app.operational_surface import render_operational_application_html


class LocalConsoleConfigurationError(ValueError):
    """Raised when the local console is configured unsafely or inconsistently."""


@dataclass(frozen=True, slots=True)
class LocalConsoleConfig:
    """Read-only sources and presentation settings for the local console."""

    sources: DataHealthSourcePaths
    build_label: str = "local-console-v0.1"
    refresh_seconds: int = 15

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
    path = urlsplit(request_target).path

    if path == "/favicon.ico":
        return ConsoleResponse(
            status_code=HTTPStatus.NO_CONTENT,
            content_type="image/x-icon",
            body=b"",
            headers=_security_headers(),
        )

    if path not in {"/", "/index.html", "/api/snapshot.json", "/api/data-health.json", "/healthz"}:
        return _json_response(
            HTTPStatus.NOT_FOUND,
            {"error": "not_found", "path": path},
        )

    health = build_data_health_summary(config.sources)
    snapshot = build_phase1_application_snapshot(
        health,
        generated_at=now,
        build_label=config.build_label,
    )

    if path in {"/", "/index.html"}:
        html = render_operational_application_html(snapshot)
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
    if allow_remote:
        return
    if normalized == "localhost":
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
                        "error": "data_health_unavailable",
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
            "base-uri 'none'; frame-ancestors 'none'; form-action 'none'",
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
