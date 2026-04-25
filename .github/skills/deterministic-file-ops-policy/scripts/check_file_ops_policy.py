#!/usr/bin/env python3
"""Commit-time checker for deterministic file/path policy.

This guard enforces the repo rule that prompts and skill text must not encode
file or directory create/update/delete behavior, and selected backend helpers
must not rely on single-location skill path assumptions. Those behaviors must
live in deterministic code paths such as tools, adapters, helpers, or backend
runtime services.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


SKILL_TEXT_TARGET_RE = re.compile(r"^(\.github/skills/.*|agent/src/skills/.*/SKILL\.md)$")
BACKEND_TARGET_RE = re.compile(
    r"^("
    r"agent/src/runtime_prompt_policy\.py|"
    r"agent/api_server\.py|"
    r"agent/src/skills/script_loader\.py|"
    r"agent/src/session/service\.py"
    r")$"
)

EXEMPT_FILES = {
    ".github/skills/deterministic-file-ops-policy/SKILL.md",
    ".github/skills/deterministic-file-ops-policy/scripts/check_file_ops_policy.py",
    "agent/tests/regression/test_file_ops_policy_checker.py",
    "agent/tests/regression/test_prompt_file_ops_policy.py",
}

NEGATION_HINTS = (
    "do not",
    "don't",
    "never",
    "must not",
    "should not",
    "not delegated",
    "deterministic code",
    "forbidden",
    "disallow",
    "disallowed",
    "banned",
    "assert fragment not in",
)


@dataclass(frozen=True)
class Violation:
    rule_id: str
    line_no: int
    line: str
    message: str


RULES: list[tuple[str, re.Pattern[str], str]] = [
    (
        "prompt_write_file_instruction",
        re.compile(r"`?write_file`?", re.IGNORECASE),
        "Prompts and skill text must not tell the model to write files directly; use deterministic code paths instead.",
    ),
    (
        "prompt_edit_file_instruction",
        re.compile(r"`?edit_file`?", re.IGNORECASE),
        "Prompts and skill text must not tell the model to edit files directly; use deterministic code paths instead.",
    ),
    (
        "prompt_delete_file_instruction",
        re.compile(r"delete[_ -]?file|remove[_ -]?file", re.IGNORECASE),
        "Prompts and skill text must not tell the model to delete files directly; use deterministic code paths instead.",
    ),
    (
        "prompt_directory_creation_instruction",
        re.compile(r"\bmkdir\b|create (?:a )?director", re.IGNORECASE),
        "Prompts and skill text must not tell the model to create directories directly; use deterministic code paths instead.",
    ),
    (
        "prompt_uploads_path_layout",
        re.compile(r"uploads/", re.IGNORECASE),
        "Prompts and skill text must not encode uploads/ path layout assumptions; backend path resolution must handle that.",
    ),
    (
        "prompt_config_file_layout",
        re.compile(r"config\.json|code/signal_engine\.py", re.IGNORECASE),
        "Prompts and skill text must not encode file layout contracts such as config.json or code/signal_engine.py.",
    ),
    (
        "prompt_absolute_temp_path",
        re.compile(r"(?:^|[\s\"'`])(\/tmp\/|\/var\/tmp\/)", re.IGNORECASE),
        "Prompts and skill text must not encode absolute temp paths like /tmp/...; keep file paths workspace/home-rooted via deterministic helpers.",
    ),
]

BACKEND_SINGLE_PATH_LOOKUP_RE = re.compile(r'skills_dir\s*/\s*skill_name\s*/\s*["\']SKILL\.md["\']')


PASS = "\033[32m✔\033[0m"
FAIL = "\033[31m✘\033[0m"


def _repo_root() -> Path:
    here = Path(__file__).resolve()
    for parent in [here, *here.parents]:
        if (parent / ".git").exists():
            return parent
    sys.exit("ERROR: Could not locate repository root (.git not found)")


def is_target_file(path: str) -> bool:
    return bool(SKILL_TEXT_TARGET_RE.match(path) or BACKEND_TARGET_RE.match(path))


def is_skill_text_target(path: str) -> bool:
    return bool(SKILL_TEXT_TARGET_RE.match(path))


def is_backend_target(path: str) -> bool:
    return bool(BACKEND_TARGET_RE.match(path))


def _git_list(root: Path, *args: str) -> list[str]:
    proc = subprocess.run(
        ["git", *args],
        cwd=root,
        capture_output=True,
        text=True,
        check=True,
    )
    return [line.strip() for line in proc.stdout.splitlines() if line.strip()]


def staged_files(root: Path) -> list[str]:
    return _git_list(root, "diff", "--cached", "--name-only", "--diff-filter=ACMR")


def tracked_files(root: Path) -> list[str]:
    return _git_list(root, "ls-files")


def read_staged_text(root: Path, path: str) -> str:
    proc = subprocess.run(
        ["git", "show", f":{path}"],
        cwd=root,
        capture_output=True,
        text=True,
        check=True,
    )
    return proc.stdout


def read_worktree_text(root: Path, path: str) -> str:
    return (root / path).read_text(encoding="utf-8")


def scan_content(text: str) -> list[Violation]:
    violations: list[Violation] = []
    for line_no, line in enumerate(text.splitlines(), start=1):
        lowered = line.lower()
        if any(hint in lowered for hint in NEGATION_HINTS):
            continue
        for rule_id, pattern, message in RULES:
            if pattern.search(line):
                violations.append(Violation(rule_id=rule_id, line_no=line_no, line=line.strip(), message=message))
    return violations


def scan_backend_content(text: str) -> list[Violation]:
    violations: list[Violation] = []
    direct_match = BACKEND_SINGLE_PATH_LOOKUP_RE.search(text)
    if not direct_match:
        return violations

    has_recursive_fallback = 'rglob("SKILL.md")' in text or "rglob('SKILL.md')" in text
    if has_recursive_fallback:
        return violations

    line_no = text.count("\n", 0, direct_match.start()) + 1
    line = text.splitlines()[line_no - 1].strip()
    violations.append(
        Violation(
            rule_id="backend_single_location_skill_lookup",
            line_no=line_no,
            line=line,
            message=(
                "Backend helpers must not rely on a single skills_dir/skill_name/SKILL.md lookup; "
                "add fallback candidates or recursive skill discovery."
            ),
        )
    )
    return violations


def scan_file(root: Path, path: str, *, staged: bool) -> list[Violation]:
    if path in EXEMPT_FILES:
        return []
    text = read_staged_text(root, path) if staged else read_worktree_text(root, path)
    if is_backend_target(path):
        return scan_backend_content(text)
    return scan_content(text)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--all-files", action="store_true", help="Scan tracked target files in the worktree instead of staged content")
    args = parser.parse_args()

    root = _repo_root()
    paths = tracked_files(root) if args.all_files else staged_files(root)
    targets = [path for path in paths if is_target_file(path)]

    if not targets:
        print(f"  {PASS}  file-ops-policy: no relevant files")
        return

    failures = 0
    for path in targets:
        violations = scan_file(root, path, staged=not args.all_files)
        if not violations:
            print(f"  {PASS}  file-ops-policy: {path}")
            continue
        failures += len(violations)
        print(f"  {FAIL}  file-ops-policy: {path}")
        for violation in violations:
            print(
                f"    L{violation.line_no} [{violation.rule_id}] {violation.message}\n"
                f"      {violation.line}"
            )

    if failures:
        print(f"\n\033[31mFAILED: {failures} file-ops policy violation(s) found.\033[0m")
        sys.exit(1)

    print(f"\n\033[32mOK: file-ops policy checks passed for {len(targets)} file(s).\033[0m")


if __name__ == "__main__":
    main()