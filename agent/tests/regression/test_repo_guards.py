from __future__ import annotations

import sys
import importlib.util
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
MODULE_PATH = REPO_ROOT / ".github" / "scripts" / "check_repo_guards.py"
SPEC = importlib.util.spec_from_file_location("check_repo_guards", MODULE_PATH)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def test_target_file_selection_matches_guard_scope():
    assert MODULE.is_target_file("agent/src/session/service.py")
    assert MODULE.is_target_file("agent/src/swarm/worker.py")
    assert MODULE.is_target_file("agent/cli.py")
    assert MODULE.is_target_file("agent/src/skills/strategy-generate/SKILL.md")
    assert MODULE.is_target_file("agent/.hermes/skills/research/bear-side-research/SKILL.md")
    assert not MODULE.is_target_file("frontend/src/pages/Agent.tsx")


def test_scan_content_flags_absolute_app_agent_path():
    violations = MODULE.scan_content("with open('/app/agent/nvda_summary.json', 'w') as f:\n")
    assert any(v.rule_id == "absolute_app_agent_path" for v in violations)


def test_scan_content_ignores_negative_policy_text():
    violations = MODULE.scan_content("- Never hardcode /app/agent/... output paths; use runtime-relative paths instead.\n")
    assert violations == []


def test_scan_content_flags_root_agent_artifact_path():
    violations = MODULE.scan_content('print("saved to agent/nvda_summary.json")\n')
    assert any(v.rule_id == "root_agent_artifact_path" for v in violations)


def test_scan_content_flags_stale_agent_cwd_prompt_text():
    violations = MODULE.scan_content(
        "- Write ONE focused Python script via `write_file`, then change into agent/ and run it.\n"
        "- The terminal already starts in the agent/ working directory.\n"
    )
    ids = {v.rule_id for v in violations}
    assert "prompt_change_into_agent" in ids
    assert "prompt_agent_working_directory" in ids


def test_scan_content_allows_runtime_relative_guidance():
    violations = MODULE.scan_content(
        "- Use the runtime-provided cwd instead.\n"
        "- Keep output paths relative so the runtime chooses the final location.\n"
    )
    assert violations == []
