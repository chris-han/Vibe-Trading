from __future__ import annotations

import tomllib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def _has_statsmodels(entries: list[str]) -> bool:
    return any(str(entry).strip().lower().startswith("statsmodels") for entry in entries)


def test_pyproject_declares_statsmodels_dependency():
    data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    deps = data["project"]["dependencies"]
    assert _has_statsmodels(deps)


def test_requirements_txt_declares_statsmodels_dependency():
    deps = [
        line.strip()
        for line in (ROOT / "requirements.txt").read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]
    assert _has_statsmodels(deps)
