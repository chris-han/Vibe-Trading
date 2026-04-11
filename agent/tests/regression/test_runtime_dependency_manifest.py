"""Regression tests for Hermes runtime dependency coverage in Vibe-Trading manifests."""

from __future__ import annotations

import tomllib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
BACKEND = ROOT / "agent"


def _deps(pyproject_path: Path) -> list[str]:
    data = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))
    return list(data["project"]["dependencies"])


def _has_prefix(deps: list[str], prefix: str) -> bool:
    return any(dep.startswith(prefix) for dep in deps)


def test_root_manifest_covers_hermes_runtime_imports():
    deps = _deps(ROOT / "pyproject.toml")
    for prefix in [
        "openai",
        "httpx",
        "jiter",
        "urllib3",
        "firecrawl-py",
        "fal-client",
        "pypdfium2",
    ]:
        assert _has_prefix(deps, prefix), f"missing dependency in root manifest: {prefix}"


def test_backend_manifest_covers_hermes_runtime_imports():
    deps = _deps(BACKEND / "pyproject.toml")
    for prefix in [
        "openai",
        "httpx",
        "jiter",
        "urllib3",
        "firecrawl-py",
        "fal-client",
        "pypdfium2",
    ]:
        assert _has_prefix(deps, prefix), f"missing dependency in agent manifest: {prefix}"
