"""Visible runtime identity for the local Research Station.

The badge is intentionally presentation-only. It makes the exact running checkout obvious to the
operator without changing research configuration, analytical services, or persisted experiment data.
"""

from __future__ import annotations

import json
from typing import cast

from trade_scout.app import research_workbench_console as _console

_CONFIGURED_IDENTITIES: set[str] = set()


def configure_runtime_identity(*, commit_sha: str, branch: str) -> None:
    """Append a fixed bottom-right runtime badge to the Strategy Builder asset."""

    short_sha = commit_sha.strip()[:8]
    clean_branch = branch.strip() or "detached"
    identity = f"SCOUT {clean_branch} @ {short_sha}"
    if identity in _CONFIGURED_IDENTITIES:
        return
    payload = json.dumps(identity)
    source = f'''\n(() => {{
  "use strict";
  if (window.location.pathname !== "/research/strategy") return;
  const identity = {payload};
  const install = () => {{
    let badge = document.getElementById("scout-runtime-identity");
    if (!badge) {{
      badge = document.createElement("div");
      badge.id = "scout-runtime-identity";
      badge.setAttribute("aria-label", "SCOUT runtime version");
      badge.style.cssText = "position:fixed;right:10px;bottom:8px;z-index:5900;padding:5px 8px;border:1px solid #36536b;border-radius:7px;background:rgba(11,14,19,.92);color:#98a6b8;font:11px/1.2 ui-monospace,SFMono-Regular,Consolas,monospace;box-shadow:0 3px 14px rgba(0,0,0,.28);pointer-events:none";
      document.body.append(badge);
    }}
    badge.textContent = identity;
  }};
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", install, {{ once:true }});
  else install();
}})();\n'''
    namespace = vars(_console)
    asset_name = "STRATEGY_BUILDER_RESEARCH_MEMORY_JS"
    asset = cast(str, namespace[asset_name])
    namespace[asset_name] = asset + source
    _CONFIGURED_IDENTITIES.add(identity)


__all__ = ["configure_runtime_identity"]
