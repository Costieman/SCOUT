"""Thin local-console adapter for interactive research-workbench presentation assets.

Research calculations still delegate to application services backed by the canonical data source.
The workbench additionally routes Strategy Builder executions through the existing governed
experiment stack when an experiment recorder is configured; the HTTP layer contains no analytics.
"""

from __future__ import annotations

from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

from trade_scout.app.experiment_library_http import build_experiment_library_page
from trade_scout.app.local_console import (
    ConsoleResponse,
    LocalConsoleConfig,
    build_console_response,
    validate_bind_host,
)
from trade_scout.app.research_brain_http import (
    build_research_brains_page,
    handle_research_brain_post,
    render_research_brain_post_error,
)
from trade_scout.app.strategy_builder_assets import STRATEGY_BUILDER_JS
from trade_scout.app.strategy_builder_clarity import STRATEGY_BUILDER_CLARITY_JS
from trade_scout.app.strategy_builder_clean_defaults import STRATEGY_BUILDER_CLEAN_DEFAULTS_JS
from trade_scout.app.strategy_builder_compact import STRATEGY_BUILDER_COMPACT_JS
from trade_scout.app.strategy_builder_entry_sweep_controls import STRATEGY_BUILDER_ENTRY_SWEEP_JS
from trade_scout.app.strategy_builder_entry_sweep_http import (
    build_entry_sweep_page,
    is_entry_sweep_query,
)
from trade_scout.app.strategy_builder_experiments import StrategyBuilderExperimentRecorder
from trade_scout.app.strategy_builder_help import STRATEGY_BUILDER_HELP_JS
from trade_scout.app.strategy_builder_readout import STRATEGY_BUILDER_READOUT_JS
from trade_scout.app.strategy_builder_recorded_http import build_recorded_strategy_page
from trade_scout.app.strategy_builder_research_memory import STRATEGY_BUILDER_RESEARCH_MEMORY_JS
from trade_scout.app.strategy_builder_sweep import STRATEGY_BUILDER_SWEEP_JS
from trade_scout.app.strategy_builder_sweep_controls import STRATEGY_BUILDER_SWEEP_CONTROLS_JS
from trade_scout.experiments.research_brains import ResearchBrainError

_ASSET_PATH = "/assets/strategy-builder.js"
_CLEAN_DEFAULTS_ASSET_PATH = "/assets/strategy-builder-clean-defaults.js"
_CLARITY_ASSET_PATH = "/assets/strategy-builder-clarity.js"
_COMPACT_ASSET_PATH = "/assets/strategy-builder-compact.js"
_ENTRY_SWEEP_ASSET_PATH = "/assets/strategy-builder-entry-sweep.js"
_HELP_ASSET_PATH = "/assets/strategy-builder-help.js"
_READOUT_ASSET_PATH = "/assets/strategy-builder-readout.js"
_RESEARCH_MEMORY_ASSET_PATH = "/assets/strategy-builder-research-memory.js"
_SWEEP_ASSET_PATH = "/assets/strategy-builder-sweep.js"
_SWEEP_CONTROLS_ASSET_PATH = "/assets/strategy-builder-sweep-controls.js"
_STRATEGY_PATH = "/research/strategy"
_EXPERIMENT_LIBRARY_PATH = "/research/experiments"
_RESEARCH_BRAINS_PATH = "/research/brains"
_MAX_POST_BODY_BYTES = 64 * 1024
_SCRIPT_MARKER = '<script src="/assets/strategy-builder.js" defer></script>'
_CLEAN_DEFAULTS_SCRIPT = '<script src="/assets/strategy-builder-clean-defaults.js" defer></script>'
_CLARITY_SCRIPT = '<script src="/assets/strategy-builder-clarity.js" defer></script>'
_COMPACT_SCRIPT = '<script src="/assets/strategy-builder-compact.js" defer></script>'
_ENTRY_SWEEP_SCRIPT = '<script src="/assets/strategy-builder-entry-sweep.js" defer></script>'
_HELP_SCRIPT = '<script src="/assets/strategy-builder-help.js" defer></script>'
_READOUT_SCRIPT = '<script src="/assets/strategy-builder-readout.js" defer></script>'
_RESEARCH_MEMORY_SCRIPT = (
    '<script src="/assets/strategy-builder-research-memory.js" defer></script>'
)
_SWEEP_SCRIPT = '<script src="/assets/strategy-builder-sweep.js" defer></script>'
_SWEEP_CONTROLS_SCRIPT = '<script src="/assets/strategy-builder-sweep-controls.js" defer></script>'


def build_research_workbench_response(
    request_target: str,
    config: LocalConsoleConfig,
    *,
    experiment_recorder: StrategyBuilderExperimentRecorder | None = None,
) -> ConsoleResponse:
    """Serve one workbench GET response with optional durable Strategy Builder capture."""

    parsed_target = urlsplit(request_target)
    path = parsed_target.path
    if path == _ASSET_PATH:
        return _javascript_response(STRATEGY_BUILDER_JS)
    if path == _CLEAN_DEFAULTS_ASSET_PATH:
        return _javascript_response(STRATEGY_BUILDER_CLEAN_DEFAULTS_JS)
    if path == _CLARITY_ASSET_PATH:
        return _javascript_response(STRATEGY_BUILDER_CLARITY_JS)
    if path == _COMPACT_ASSET_PATH:
        return _javascript_response(STRATEGY_BUILDER_COMPACT_JS)
    if path == _ENTRY_SWEEP_ASSET_PATH:
        return _javascript_response(STRATEGY_BUILDER_ENTRY_SWEEP_JS)
    if path == _HELP_ASSET_PATH:
        return _javascript_response(STRATEGY_BUILDER_HELP_JS)
    if path == _READOUT_ASSET_PATH:
        return _javascript_response(STRATEGY_BUILDER_READOUT_JS)
    if path == _RESEARCH_MEMORY_ASSET_PATH:
        return _javascript_response(STRATEGY_BUILDER_RESEARCH_MEMORY_JS)
    if path == _SWEEP_ASSET_PATH:
        return _javascript_response(STRATEGY_BUILDER_SWEEP_JS)
    if path == _SWEEP_CONTROLS_ASSET_PATH:
        return _javascript_response(STRATEGY_BUILDER_SWEEP_CONTROLS_JS)

    if path == _EXPERIMENT_LIBRARY_PATH:
        if experiment_recorder is None:
            return _unconfigured_response("Experiment Library")
        status, html = build_experiment_library_page(parsed_target.query, experiment_recorder)
        return _html_response(status, html)

    if path == _RESEARCH_BRAINS_PATH:
        if experiment_recorder is None:
            return _unconfigured_response("Research Brains")
        status, html = build_research_brains_page(parsed_target.query, experiment_recorder)
        return _html_response(status, html)

    strategy_parameters = (
        parse_qs(parsed_target.query, keep_blank_values=True) if path == _STRATEGY_PATH else {}
    )
    if path == _STRATEGY_PATH and is_entry_sweep_query(parsed_target.query):
        status, html = build_entry_sweep_page(
            parsed_target.query,
            config,
            experiment_recorder=experiment_recorder,
        )
        response = _html_response(status, html)
    elif (
        path == _STRATEGY_PATH
        and experiment_recorder is not None
        and "universe" in strategy_parameters
    ):
        status, html = build_recorded_strategy_page(
            parsed_target.query,
            config,
            experiment_recorder,
        )
        response = _html_response(status, html)
    else:
        response = build_console_response(request_target, config)
    body = response.body
    if path == _STRATEGY_PATH and response.content_type.startswith("text/html"):
        html = body.decode("utf-8")
        if _SCRIPT_MARKER not in html:
            raise RuntimeError("Strategy Builder HTML omitted its interactive script marker")
        scripts = (
            f"{_SCRIPT_MARKER}\n{_CLEAN_DEFAULTS_SCRIPT}\n{_CLARITY_SCRIPT}\n"
            f"{_COMPACT_SCRIPT}\n{_HELP_SCRIPT}\n{_READOUT_SCRIPT}\n"
            f"{_SWEEP_SCRIPT}\n{_SWEEP_CONTROLS_SCRIPT}\n{_ENTRY_SWEEP_SCRIPT}\n"
            f"{_RESEARCH_MEMORY_SCRIPT}"
        )
        body = html.replace(_SCRIPT_MARKER, scripts, 1).encode("utf-8")
    elif (
        path in {"/", "/index.html"}
        and experiment_recorder is not None
        and response.content_type.startswith("text/html")
    ):
        body = _with_research_memory_links(body)

    return ConsoleResponse(
        status_code=response.status_code,
        content_type=response.content_type,
        body=body,
        headers=_replace_csp(response.headers),
    )


def build_research_workbench_post_response(
    request_target: str,
    content_type: str,
    body: bytes,
    *,
    experiment_recorder: StrategyBuilderExperimentRecorder | None = None,
) -> ConsoleResponse:
    """Apply one explicit local workbench mutation; analytical routes remain GET-only."""

    path = urlsplit(request_target).path
    if path != _RESEARCH_BRAINS_PATH:
        return ConsoleResponse(
            status_code=HTTPStatus.METHOD_NOT_ALLOWED,
            content_type="text/plain; charset=utf-8",
            body=b"",
            headers=(*_interactive_security_headers(), ("Allow", "GET, HEAD")),
        )
    if experiment_recorder is None:
        return _unconfigured_response("Research Brains")
    if not content_type.lower().startswith("application/x-www-form-urlencoded"):
        return ConsoleResponse(
            status_code=HTTPStatus.UNSUPPORTED_MEDIA_TYPE,
            content_type="text/plain; charset=utf-8",
            body=b"Research Brain forms require application/x-www-form-urlencoded.\n",
            headers=_interactive_security_headers(),
        )
    if len(body) > _MAX_POST_BODY_BYTES:
        return ConsoleResponse(
            status_code=HTTPStatus.REQUEST_ENTITY_TOO_LARGE,
            content_type="text/plain; charset=utf-8",
            body=b"Research Brain form is too large.\n",
            headers=_interactive_security_headers(),
        )
    try:
        status, location = handle_research_brain_post(body, experiment_recorder)
    except (KeyError, OSError, ValueError, ResearchBrainError) as exc:
        html = render_research_brain_post_error(exc, experiment_recorder)
        return _html_response(HTTPStatus.BAD_REQUEST, html)
    if status is not HTTPStatus.SEE_OTHER:
        raise RuntimeError("Research Brain mutation did not return a safe redirect")
    return ConsoleResponse(
        status_code=status,
        content_type="text/plain; charset=utf-8",
        body=b"",
        headers=(*_interactive_security_headers(), ("Location", location)),
    )


def serve_research_workbench_console(
    config: LocalConsoleConfig,
    *,
    host: str = "127.0.0.1",
    port: int = 8765,
    allow_remote: bool = False,
    experiment_recorder: StrategyBuilderExperimentRecorder | None = None,
) -> None:
    """Serve the console, interactive assets, and optional experiment/brain capture."""

    validate_bind_host(host, allow_remote=allow_remote)
    if not 1 <= port <= 65535:
        raise ValueError("port must be between 1 and 65535")

    class Handler(BaseHTTPRequestHandler):
        server_version = "TradeScoutResearchWorkbench/0.1"

        def do_GET(self) -> None:
            self._respond_get(head_only=False)

        def do_HEAD(self) -> None:
            self._respond_get(head_only=True)

        def do_POST(self) -> None:
            response = self._build_post_response()
            self._send_console_response(response, head_only=False)

        def _respond_get(self, *, head_only: bool) -> None:
            try:
                response = build_research_workbench_response(
                    self.path,
                    config,
                    experiment_recorder=experiment_recorder,
                )
            except Exception as exc:
                body = f"application unavailable: {type(exc).__name__}: {exc}\n".encode()
                response = ConsoleResponse(
                    status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
                    content_type="text/plain; charset=utf-8",
                    body=body,
                    headers=_interactive_security_headers(),
                )
            self._send_console_response(response, head_only=head_only)

        def _build_post_response(self) -> ConsoleResponse:
            raw_length = self.headers.get("Content-Length")
            if raw_length is None:
                return ConsoleResponse(
                    status_code=HTTPStatus.LENGTH_REQUIRED,
                    content_type="text/plain; charset=utf-8",
                    body=b"Content-Length is required.\n",
                    headers=_interactive_security_headers(),
                )
            try:
                length = int(raw_length)
            except ValueError:
                return ConsoleResponse(
                    status_code=HTTPStatus.BAD_REQUEST,
                    content_type="text/plain; charset=utf-8",
                    body=b"Invalid Content-Length.\n",
                    headers=_interactive_security_headers(),
                )
            if length < 0 or length > _MAX_POST_BODY_BYTES:
                return ConsoleResponse(
                    status_code=HTTPStatus.REQUEST_ENTITY_TOO_LARGE,
                    content_type="text/plain; charset=utf-8",
                    body=b"Research Brain form is too large.\n",
                    headers=_interactive_security_headers(),
                )
            body = self.rfile.read(length)
            try:
                return build_research_workbench_post_response(
                    self.path,
                    self.headers.get("Content-Type", ""),
                    body,
                    experiment_recorder=experiment_recorder,
                )
            except Exception as exc:
                payload = f"application unavailable: {type(exc).__name__}: {exc}\n".encode()
                return ConsoleResponse(
                    status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
                    content_type="text/plain; charset=utf-8",
                    body=payload,
                    headers=_interactive_security_headers(),
                )

        def _send_console_response(self, response: ConsoleResponse, *, head_only: bool) -> None:
            try:
                self.send_response(response.status_code)
                self.send_header("Content-Type", response.content_type)
                self.send_header("Content-Length", str(len(response.body)))
                for name, value in response.headers:
                    self.send_header(name, value)
                self.end_headers()
                if not head_only and response.body:
                    self.wfile.write(response.body)
            except (BrokenPipeError, ConnectionAbortedError, ConnectionResetError):
                # A local browser tab may be closed or replaced while a synchronous research
                # response is being prepared. That is a client disconnect, not an application error.
                return

    server = ThreadingHTTPServer((host, port), Handler)
    try:
        server.serve_forever(poll_interval=0.25)
    finally:
        server.server_close()


def _with_research_memory_links(body: bytes) -> bytes:
    html = body.decode("utf-8")
    marker = '<a href="#research">Research</a>'
    if marker not in html:
        return body
    links = (
        '<a href="/research/experiments">Experiment Library</a>'
        '<a href="/research/brains">Research Brains</a>'
    )
    return html.replace(marker, marker + links, 1).encode("utf-8")


def _unconfigured_response(name: str) -> ConsoleResponse:
    return ConsoleResponse(
        status_code=HTTPStatus.SERVICE_UNAVAILABLE,
        content_type="text/plain; charset=utf-8",
        body=f"{name} is not configured for this workbench.\n".encode(),
        headers=_interactive_security_headers(),
    )


def _html_response(status: HTTPStatus, html: str) -> ConsoleResponse:
    return ConsoleResponse(
        status_code=status,
        content_type="text/html; charset=utf-8",
        body=html.encode("utf-8"),
        headers=_interactive_security_headers(),
    )


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


__all__ = [
    "build_research_workbench_post_response",
    "build_research_workbench_response",
    "serve_research_workbench_console",
]
