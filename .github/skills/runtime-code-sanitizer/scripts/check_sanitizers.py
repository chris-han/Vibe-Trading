#!/usr/bin/env python3
"""Pre-commit checker: verify that the output-format prompt keeps the VChart,
Mermaid, and Markdown table rules and does not regress to legacy ECharts
language.

Usage:
  python check_sanitizers.py              # check only (exits non-zero on failure)
  python check_sanitizers.py --install-hook  # also install the pre-commit hook

Exit codes:
  0  all checks passed
  1  one or more checks failed
"""
from __future__ import annotations

import argparse
import re
import shutil
import stat
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Config — add prompt rules here
# ---------------------------------------------------------------------------

REQUIRED_PROMPT_PHRASES: list[tuple[str, str]] = [
    ("VChart charts", "Use vchart blocks for charts."),
    ("Markdown tables", "Render tables as Markdown pipe-tables."),
    ("Mermaid diagrams", "Use Mermaid for diagrams and flowcharts."),
]

FORBIDDEN_PROMPT_PHRASES = [
    "ECharts",
    "echarts",
    "legacy chart",
    "_sanitize_echarts_blocks",
]

# Paths relative to repo root
SERVICE_PY = Path("agent/src/session/service.py")
HOOK_DST   = Path(".git/hooks/pre-commit")
HOOK_SRC   = Path(".github/skills/runtime-code-sanitizer/scripts/pre-commit")

# ---------------------------------------------------------------------------

PASS = "\033[32m✔\033[0m"
FAIL = "\033[31m✘\033[0m"


def _find_repo_root() -> Path:
    here = Path(__file__).resolve()
    for parent in [here, *here.parents]:
        if (parent / ".git").exists():
            return parent
    sys.exit("ERROR: Could not locate repository root (.git not found)")


def _read_service(root: Path) -> str:
    path = root / SERVICE_PY
    if not path.exists():
        sys.exit(f"ERROR: {SERVICE_PY} not found — run from repo root")
    return path.read_text(encoding="utf-8")


def _extract_output_format_prompt(source: str) -> str:
    """Return the string value of _OUTPUT_FORMAT_PROMPT."""
    m = re.search(
        r'_OUTPUT_FORMAT_PROMPT\s*=\s*\((.*?)\)\s*\n',
        source,
        re.DOTALL,
    )
    if not m:
        return ""
    # Strip Python string concatenation to get raw text
    raw = m.group(1)
    parts = re.findall(r'"((?:[^"\\]|\\.)*)"', raw)
    return "".join(parts)


def check_all(source: str) -> list[tuple[str, bool, str]]:
    """Return list of (check_label, passed, detail)."""
    results: list[tuple[str, bool, str]] = []
    prompt_text = _extract_output_format_prompt(source)
    for label, phrase in REQUIRED_PROMPT_PHRASES:
        present = phrase in prompt_text
        results.append((
            f"{label}: prompt guard contains '{phrase}'",
            present,
            "" if present else f"  → add a rule mentioning '{phrase}' to _OUTPUT_FORMAT_PROMPT",
        ))

    for phrase in FORBIDDEN_PROMPT_PHRASES:
        absent = phrase not in prompt_text
        results.append((
            f"Prompt guard no longer mentions '{phrase}'",
            absent,
            "" if absent else f"  → remove '{phrase}' from _OUTPUT_FORMAT_PROMPT",
        ))

    return results


def install_hook(root: Path) -> None:
    src = root / HOOK_SRC
    dst = root / HOOK_DST
    if not src.exists():
        sys.exit(f"ERROR: hook source {HOOK_SRC} not found")
    shutil.copy2(src, dst)
    dst.chmod(dst.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    print(f"Installed pre-commit hook → {dst}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--install-hook", action="store_true", help="Install the pre-commit git hook")
    args = parser.parse_args()

    root = _find_repo_root()

    if args.install_hook:
        install_hook(root)

    source = _read_service(root)
    results = check_all(source)

    passed = 0
    failed = 0
    for label, ok, detail in results:
        icon = PASS if ok else FAIL
        print(f"  {icon}  {label}")
        if not ok and detail:
            print(f"\033[33m{detail}\033[0m")
        if ok:
            passed += 1
        else:
            failed += 1

    print()
    if failed:
        print(f"\033[31mFAILED: {failed} check(s) failed, {passed} passed.\033[0m")
        sys.exit(1)
    else:
        print(f"\033[32mOK: all {passed} sanitizer checks passed.\033[0m")


if __name__ == "__main__":
    main()
