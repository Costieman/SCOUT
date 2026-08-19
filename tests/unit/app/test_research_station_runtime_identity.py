from trade_scout.app import research_station_runtime_identity as identity
from trade_scout.app import research_workbench_console as console


def test_runtime_identity_badge_contains_branch_and_short_commit(monkeypatch) -> None:
    monkeypatch.setattr(console, "STRATEGY_BUILDER_RESEARCH_MEMORY_JS", "base-asset")
    monkeypatch.setattr(identity, "_CONFIGURED_IDENTITIES", set())

    identity.configure_runtime_identity(
        commit_sha="1234567890abcdef",
        branch="main",
    )

    asset = console.STRATEGY_BUILDER_RESEARCH_MEMORY_JS
    assert "scout-runtime-identity" in asset
    assert "SCOUT main @ 12345678" in asset
    assert "position:fixed;right:10px;bottom:8px" in asset


def test_runtime_identity_is_idempotent_for_same_checkout(monkeypatch) -> None:
    monkeypatch.setattr(console, "STRATEGY_BUILDER_RESEARCH_MEMORY_JS", "base-asset")
    monkeypatch.setattr(identity, "_CONFIGURED_IDENTITIES", set())

    identity.configure_runtime_identity(commit_sha="abcdef123456", branch="main")
    once = console.STRATEGY_BUILDER_RESEARCH_MEMORY_JS
    identity.configure_runtime_identity(commit_sha="abcdef123456", branch="main")

    assert console.STRATEGY_BUILDER_RESEARCH_MEMORY_JS == once
