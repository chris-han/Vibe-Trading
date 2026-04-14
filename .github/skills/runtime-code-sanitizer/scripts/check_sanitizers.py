#!/usr/bin/env python3
"""Pre-commit checker: verify that every runtime-generated code type has both
a sanitizer function and a prompt guard in service.py.

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
# Config — add new output types here
# ---------------------------------------------------------------------------

# Each entry:  (type_name, sanitizer_fn_name, prompt_guard_phrase)
# prompt_guard_phrase: a substring that MUST appear in _OUTPUT_FORMAT_PROMPT
REQUIRED_TYPES: list[tuple[str, str, str]] = [
    (
        "Legacy ECharts",
        "_sanitize_echarts_blocks",
        "Do NOT emit echarts blocks for new reports. Use vchart instead.",
    ),
    # Template for adding more types:
    # (
    #     "Mermaid",
    #     "_sanitize_mermaid_blocks",
    #     "Mermaid safety",
    # ),
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

    for type_name, sanitizer_fn, guard_phrase in REQUIRED_TYPES:
        # 1. Sanitizer function defined
        fn_defined = f"def {sanitizer_fn}(" in source
        results.append((
            f"{type_name}: sanitizer function '{sanitizer_fn}' defined",
            fn_defined,
            "" if fn_defined else f"  → add 'def {sanitizer_fn}(text: str) -> str:' to {SERVICE_PY}",
        ))

        # 2. Sanitizer called on final_text
        call_pattern = re.compile(
            rf'final_text\s*=\s*{re.escape(sanitizer_fn)}\s*\(', re.MULTILINE
        )
        fn_called = bool(call_pattern.search(source))
        results.append((
            f"{type_name}: sanitizer '{sanitizer_fn}' wired into output pipeline",
            fn_called,
            "" if fn_called else f"  → add 'final_text = {sanitizer_fn}(final_text)' before report.md write",
        ))

        # 3. Prompt guard present
        guard_present = guard_phrase in prompt_text
        results.append((
            f"{type_name}: prompt guard contains '{guard_phrase}'",
            guard_present,
            "" if guard_present else f"  → add a rule mentioning '{guard_phrase}' to _OUTPUT_FORMAT_PROMPT",
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
