from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
MODULE_PATH = REPO_ROOT / ".github" / "skills" / "deterministic-file-ops-policy" / "scripts" / "check_file_ops_policy.py"
SPEC = importlib.util.spec_from_file_location("check_file_ops_policy", MODULE_PATH)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def test_target_file_selection_matches_policy_scope():
    assert MODULE.is_target_file(".github/skills/deterministic-file-ops-policy/SKILL.md")
    assert MODULE.is_target_file(".github/skills/runtime-code-sanitizer/SKILL.md")
    assert not MODULE.is_target_file("frontend/src/pages/Agent.tsx")
    assert not MODULE.is_target_file("agent/src/session/service.py")


def test_scan_content_flags_write_file_instruction():
    violations = MODULE.scan_content("- Write ONE focused Python script via `write_file`, then run it.\n")
    assert any(v.rule_id == "prompt_write_file_instruction" for v in violations)


def test_scan_content_flags_edit_file_instruction():
    violations = MODULE.scan_content("- If it fails, fix with `edit_file` and retry.\n")
    assert any(v.rule_id == "prompt_edit_file_instruction" for v in violations)


def test_scan_content_flags_uploads_path_layout():
    violations = MODULE.scan_content("- Look under sessions/<session_id>/uploads/ for the file.\n")
    assert any(v.rule_id == "prompt_uploads_path_layout" for v in violations)


def test_scan_content_flags_file_layout_contracts():
    violations = MODULE.scan_content("- Create config.json and code/signal_engine.py before running the backtest.\n")
    ids = {v.rule_id for v in violations}
    assert "prompt_config_file_layout" in ids


def test_scan_content_ignores_negative_policy_text():
    violations = MODULE.scan_content(
        "- Do not use `write_file` in prompts.\n"
        "- File ops must live in deterministic code.\n"
    )
    assert violations == []