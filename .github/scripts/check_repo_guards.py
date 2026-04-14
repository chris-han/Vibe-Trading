#!/usr/bin/env python3
"""Pre-commit checker for repo-local runtime path and prompt guard policies.

This checker scans staged content for local Vibe-Trading rules that are not
covered by Hermes' external skills security scanner:

- no hardcoded output paths like /app/agent/...
- no root-level artifact paths like agent/foo.json
- no prompt text telling models to change into or assume agent/ as cwd
"""
from __future__ import annotations

import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


TARGET_FILE_RE = re.compile(
    r"^("
    r"agent/src/session/service\.py|"
    r"agent/src/swarm/worker\.py|"
    r"agent/cli\.py|"
    r"agent/src/skills/.*|"
    r"agent/\.hermes/skills/.*|"
    r"\.github/skills/runtime-code-sanitizer/scripts/pre-commit"
    r")$"
)

EXEMPT_FILES = {
    ".github/scripts/check_repo_guards.py",
    ".github/skills/runtime-code-sanitizer/SKILL.md",
    ".github/skills/runtime-code-sanitizer/scripts/check_sanitizers.py",
    ".github/skills/runtime-code-sanitizer/scripts/pre-commit",
    "agent/tests/regression/test_repo_guards.py",
}

NEGATION_HINTS = (
    "never hardcode",
    "do not hardcode",
    "do not emit",
    "do not tell",
    "never tell",
    "runtime-provided cwd",
    "runtime controlled",
    "runtime-controlled",
    "fallback",
)


@dataclass(frozen=True)
class Violation:
    rule_id: str
    line_no: int
    line: str
    message: str


RULES: list[tuple[str, re.Pattern[str], str]] = [
    (
        "absolute_app_agent_path",
        re.compile(r"/app/agent/"),
        "Do not hardcode /app/agent/... output paths; use runtime-relative paths instead.",
    ),
    (
        "root_agent_artifact_path",
        re.compile(r"(?<![\w./-])agent/[^/\s\"'`)]*\.(?:json|csv|md|txt|py)\b"),
        "Do not hardcode root-level agent/<file> artifact paths; use runtime-relative paths instead.",
    ),
    (
        "prompt_change_into_agent",
        re.compile(r"change into agent/", re.IGNORECASE),
        "Prompts must not tell the model to change into agent/; runtime cwd is task-scoped.",
    ),
    (
        "prompt_agent_working_directory",
        re.compile(r"starts in the agent/ working directory", re.IGNORECASE),
        "Prompts must not claim the terminal starts in agent/; runtime cwd is task-scoped.",
    ),
    (
        "prompt_bash_in_agent",
        re.compile(r"bash in agent/ instead", re.IGNORECASE),
        "Prompts must not instruct bash execution 'in agent/'; use the runtime-provided cwd.",
    ),
    (
        "prompt_install_from_agent",
        re.compile(r"install packages only from agent/", re.IGNORECASE),
        "Prompts must not instruct package installs from agent/; use the runtime-provided cwd.",
    ),
]


PASS = "\033[32m✔\033[0m"
FAIL = "\033[31m✘\033[0m"


def _repo_root() -> Path:
    here = Path(__file__).resolve()
    for parent in [here, *here.parents]:
        if (parent / ".git").exists():
            return parent
    sys.exit("ERROR: Could not locate repository root (.git not found)")


def is_target_file(path: str) -> bool:
    return bool(TARGET_FILE_RE.match(path))


def staged_files(root: Path) -> list[str]:
    proc = subprocess.run(
        ["git", "diff", "--cached", "--name-only", "--diff-filter=ACMR"],
        cwd=root,
        capture_output=True,
        text=True,
        check=True,
    )
    return [line.strip() for line in proc.stdout.splitlines() if line.strip()]


def read_staged_text(root: Path, path: str) -> str:
    proc = subprocess.run(
        ["git", "show", f":{path}"],
        cwd=root,
        capture_output=True,
        text=True,
        check=True,
    )
    return proc.stdout


def scan_content(text: str) -> list[Violation]:
    violations: list[Violation] = []
    for line_no, line in enumerate(text.splitlines(), start=1):
        line_l = line.lower()
        if any(hint in line_l for hint in NEGATION_HINTS):
            continue
        for rule_id, pattern, message in RULES:
            if pattern.search(line):
                violations.append(
                    Violation(
                        rule_id=rule_id,
                        line_no=line_no,
                        line=line.strip(),
                        message=message,
                    )
                )
    return violations


def scan_file(root: Path, path: str) -> list[Violation]:
    if path in EXEMPT_FILES:
        return []
    return scan_content(read_staged_text(root, path))


def main() -> None:
    root = _repo_root()
    staged = [path for path in staged_files(root) if is_target_file(path)]
    if not staged:
        print(f"  {PASS}  repo-guard: no relevant staged files")
        return

    failures = 0
    for path in staged:
        violations = scan_file(root, path)
        if not violations:
            print(f"  {PASS}  repo-guard: {path}")
            continue

        failures += len(violations)
        print(f"  {FAIL}  repo-guard: {path}")
        for violation in violations:
            print(
                f"    L{violation.line_no} [{violation.rule_id}] {violation.message}\n"
                f"      {violation.line}"
            )

    if failures:
        print(f"\n\033[31mFAILED: {failures} repo guard violation(s) found.\033[0m")
        sys.exit(1)

    print(f"\n\033[32mOK: repo guard checks passed for {len(staged)} staged file(s).\033[0m")


if __name__ == "__main__":
    main()
