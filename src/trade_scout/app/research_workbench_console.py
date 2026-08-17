"""Thin local-console adapter for interactive research-workbench presentation assets.

Research calculations still delegate to ``local_console.build_console_response``. This adapter only
serves self-hosted Strategy Builder JavaScript and extends the existing CSP to permit scripts from
the same loopback origin; it does not add provider access or analytical logic.
"""

from __future__ import annotations

from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

from trade_scout.app.local_console import (
    ConsoleResponse,
    LocalConsoleConfig,
    build_console_response,
    validate_bind_host,
)
from trade_scout.app.strategy_builder_assets import STRATEGY_BUILDER_JS
from trade_scout.app.strategy_builder_clarity import STRATEGY_BUILDER_CLARITY_JS
from trade_scout.app.strategy_builder_clean_defaults import STRATEGY_BUILDER_CLEAN_DEFAULTS_JS
from trade_scout.app.strategy_builder_compact import STRATEGY_BUILDER_COMPACT_JS
from trade_scout.app.strategy_builder_help import STRATEGY_BUILDER_HELP_JS
from trade_scout.app.strategy_builder_readout import STRATEGY_BUILDER_READOUT_JS
from trade_scout.app.strategy_builder_sweep import STRATEGY_BUILDER_SWEEP_JS
from trade_scout.app.strategy_builder_sweep_controls import STRATEGY_BUILDER_SWEEP_CONTROLS_JS

_ASSET_PATH = "/assets/strategy-builder.js"
_CLEAN_DEFAULTS_ASSET_PATH = "/assets/strategy-builder-clean-defaults.js"
_CLARITY_ASSET_PATH = "/assets/strategy-builder-clarity.js"
_COMPACT_ASSET_PATH = "/assets/strategy-builder-compact.js"
_HELP_ASSET_PATH = "/assets/strategy-builder-help.js"
_READOUT_ASSET_PATH = "/assets/strategy-builder-readout.js"
_SWEEP_ASSET_PATH = "/assets/strategy-builder-sweep.js"
_SWEEP_CONTROLS_ASSET_PATH = "/assets/strategy-builder-sweep-controls.js"
_STRATEGY_PATH = "/research/strategy"
_SCRIPT_MARKER = '<script src="/assets/strategy-builder.js" defer></script>'
_CLEAN_DEFAULTS_SCRIPT = '<script src="/assets/strategy-builder-clean-defaults.js" defer></script>'
_CLARITY_SCRIPT = '<script src="/assets/strategy-builder-clarity.js" defer></script>'
_COMPACT_SCRIPT = '<script src="/assets/strategy-builder-compact.js" defer></script>'
_HELP_SCRIPT = '<script src="/assets/strategy-builder-help.js" defer></script>'
_READOUT_SCRIPT = '<script src="/assets/strategy-builder-readout.js" defer></script>'
_SWEEP_SCRIPT = '<script src="/assets/strategy-builder-sweep.js" defer></script>'
_SWEEP_CONTROLS_SCRIPT = '<script src="/assets/strategy-builder-sweep-controls.js" defer></script>'


def build_research_workbench_response(
    request_target: str,
    config: LocalConsoleConfig,
) -> ConsoleResponse:
    """Serve one workbench response while keeping analytical routing in the existing console."""

    path = urlsplit(request_target).path
    if path == _ASSET_PATH:
        return _javascript_response(STRATEGY_BUILDER_JS)
    if path == _CLEAN_DEFAULTS_ASSET_PATH:
        return _javascript_response(STRATEGY_BUILDER_CLEAN_DEFAULTS_JS)
    if path == _CLARITY_ASSET_PATH:
        return _javascript_response(STRATEGY_BUILDER_CLARITY_JS)
    if path == _COMPACT_ASSET_PATH:
        return _javascript_response(STRATEGY_BUILDER_COMPACT_JS)
    if path == _HELP_ASSET_PATH:
        return _javascript_response(STRATEGY_BUILDER_HELP_JS)
    if path == _READOUT_ASSET_PATH:
        return _javascript_response(STRATEGY_BUILDER_READOUT_JS)
    if path == _SWEEP_ASSET_PATH:
        return _javascript_response(STRATEGY_BUILDER_SWEEP_JS)
    if path == _SWEEP_CONTROLS_ASSET_PATH:
        return _javascript_response(STRATEGY_BUILDER_SWEEP_CONTROLS_JS)

    response = build_console_response(request_target, config)
    body = response.body
    if path == _STRATEGY_PATH and response.content_type.startswith("text/html"):
        html = body.decode("utf-8")
        if _SCRIPT_MARKER not in html:
            raise RuntimeError("Strategy Builder HTML omitted its interactive script marker")
        scripts = (
            f"{_SCRIPT_MARKER}\n{_CLEAN_DEFAULTS_SCRIPT}\n{_CLARITY_SCRIPT}\n"
            f"{_COMPACT_SCRIPT}\n{_HELP_SCRIPT}\n{_READOUT_SCRIPT}\n"
            f"{_SWEEP_SCRIPT}\n{_SWEEP_CONTROLS_SCRIPT}"
        )
        body = html.replace(_SCRIPT_MARKER, scripts, 1).encode("utf-8")

    return ConsoleResponse(
        status_code=response.status_code,
        content_type=response.content_type,
        body=body,
        headers=_replace_csp(response.headers),
    )


def serve_research_workbench_console(
    config: LocalConsoleConfig,
    *,
    host: str = "127.0.0.1",
    port: int = 8765,
    allow_remote: bool = False,
) -> None:
    """Serve the existing console plus same-origin interactive Strategy Builder assets."""

    validate_bind_host(host, allow_remote=allow_remote)
    if not 1 <= port <= 65535:
        raise ValueError("port must be between 1 and 65535")

    class Handler(BaseHTTPRequestHandler):
        server_version = "TradeScoutResearchWorkbench/0.1"

        def do_GET(self) -> None:
            self._respond(head_only=False)

        def do_HEAD(self) -> None:
            self._respond(head_only=True)

        def do_POST(self) -> None:
            self.send_response(HTTPStatus.METHOD_NOT_ALLOWED)
            self.send_header("Allow", "GET, HEAD")
            self.send_header("Content-Length", "0")
            self.end_headers()

        def _respond(self, *, head_only: bool) -> None:
            try:
                response = build_research_workbench_response(self.path, config)
            except Exception as exc:
                body = f"application unavailable: {type(exc).__name__}: {exc}\n".encode()
                response = ConsoleResponse(
                    status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
                    content_type="text/plain; charset=utf-8",
                    body=body,
                    headers=_interactive_security_headers(),
                )
            self.send_response(response.status_code)
            self.send_header("Content-Type", response.content_type)
            self.send_header("Content-Length", str(len(response.body)))
            for name, value in response.headers:
                self.send_header(name, value)
            self.end_headers()
            if not head_only and response.body:
                self.wfile.write(response.body)

    server = ThreadingHTTPServer((host, port), Handler)
    try:
        server.serve_forever(poll_interval=0.25)
    finally:
        server.server_close()


def _javascript_response(source: str) -> ConsoleResponse:
    return ConsoleResponse(
        status_code=HTTPStatus.OK,
        content_type="text/javascript; charset=utf-8",
        body=source.encode("utf-8"),
        headers=_interactive_security_headers(),
    )


def _replace_csp(headers: tuple[tuple[str, str], ...]) -> tuple[tuple[str, str], ...]:
    kept = tuple(
        (name, value) for name, value in headers if name.lower() != "content-security-policy"
    )
    return (*kept, ("Content-Security-Policy", _csp_value()))


def _interactive_security_headers() -> tuple[tuple[str, str], ...]:
    return (
        ("Cache-Control", "no-store"),
        ("X-Content-Type-Options", "nosniff"),
        ("Referrer-Policy", "no-referrer"),
        ("Content-Security-Policy", _csp_value()),
    )


def _csp_value() -> str:
    return (
        "default-src 'none'; style-src 'unsafe-inline'; script-src 'self'; img-src 'self'; "
        "base-uri 'none'; frame-ancestors 'none'; form-action 'self'"
    )


__all__ = ["build_research_workbench_response", "serve_research_workbench_console"]
