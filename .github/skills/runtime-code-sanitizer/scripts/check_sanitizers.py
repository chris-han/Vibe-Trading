#!/usr/bin/env python3
"""Pre-commit checker: verify that the output-format prompt keeps the ECharts,
Mermaid, and Markdown table rules for the web UI.

Usage:
  python check_sanitizers.py              # check only (exits non-zero on failure)
  python check_sanitizers.py --install-hook  # also install the pre-commit hook

Exit codes:
  0  all checks passed
  1  one or more checks failed
"""
from __future__ import annotations

import argparse
import ast
import re
import shutil
import stat
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Config — add prompt rules here
# ---------------------------------------------------------------------------

REQUIRED_PROMPT_PHRASES: list[tuple[str, str]] = [
    ("ECharts charts", "Use echarts blocks for charts in the web UI."),
    ("Markdown tables", "Render tables as Markdown pipe-tables."),
    ("Mermaid diagrams", "Use Mermaid for diagrams and flowcharts."),
]

FORBIDDEN_PROMPT_PHRASES = [
    "Use vchart blocks for charts.",
]

# Paths relative to repo root
PROMPT_SOURCE_FILES = (
    Path("agent/src/runtime_prompt_policy.py"),
    Path("agent/src/session/service.py"),
)
HOOK_DST = Path(".git/hooks/pre-commit")
HOOK_SRC = Path(".github/skills/runtime-code-sanitizer/scripts/pre-commit")

# ---------------------------------------------------------------------------

PASS = "\033[32m✔\033[0m"
FAIL = "\033[31m✘\033[0m"


def _find_repo_root() -> Path:
    here = Path(__file__).resolve()
    for parent in [here, *here.parents]:
        if (parent / ".git").exists():
            return parent
    sys.exit("ERROR: Could not locate repository root (.git not found)")


def _read_prompt_source(root: Path) -> tuple[Path, str]:
    for path in PROMPT_SOURCE_FILES:
        candidate = root / path
        if not candidate.exists():
            continue
        source = candidate.read_text(encoding="utf-8")
        if _extract_output_format_prompt(source):
            return path, source
    search_list = ", ".join(str(path) for path in PROMPT_SOURCE_FILES)
    sys.exit(f"ERROR: no prompt source with OUTPUT_FORMAT_PROMPT found; checked: {search_list}")


def _extract_from_ast(source: str) -> str:
    try:
        module = ast.parse(source)
    except SyntaxError:
        return ""

    for node in module.body:
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if not isinstance(target, ast.Name):
                continue
            if target.id not in {"OUTPUT_FORMAT_PROMPT", "_OUTPUT_FORMAT_PROMPT"}:
                continue
            try:
                value = ast.literal_eval(node.value)
            except Exception:
                value = None
            if isinstance(value, str):
                return value
            if (
                isinstance(node.value, ast.Call)
                and isinstance(node.value.func, ast.Name)
                and node.value.func.id == "_format_rules"
                and len(node.value.args) >= 2
            ):
                title = ast.literal_eval(node.value.args[0])
                rules = ast.literal_eval(node.value.args[1])
                if isinstance(title, str) and isinstance(rules, tuple) and all(isinstance(rule, str) for rule in rules):
                    return title + ":\n" + "\n".join(f"- {rule}" for rule in rules) + "\n"
    return ""


def _extract_output_format_prompt(source: str) -> str:
    """Return the string value of OUTPUT_FORMAT_PROMPT or _OUTPUT_FORMAT_PROMPT."""
    prompt = _extract_from_ast(source)
    if prompt:
        return prompt
    m = re.search(
        r'(?P<name>OUTPUT_FORMAT_PROMPT|_OUTPUT_FORMAT_PROMPT)\s*=\s*\((.*?)\)\s*\n',
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

    source_path, source = _read_prompt_source(root)
    results = check_all(source)

    print(f"Checking prompt guard in {source_path}")
    print()

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
