from trade_scout import __version__


def test_package_imports_and_exposes_version() -> None:
    assert __version__ == "0.1.0.dev0"
