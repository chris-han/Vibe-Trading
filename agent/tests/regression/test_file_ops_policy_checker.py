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
    assert MODULE.is_target_file("agent/src/skills/app-infra/productivity/feishu-bot-meeting-coordinator/SKILL.md")
    assert MODULE.is_target_file("agent/src/runtime_prompt_policy.py")
    assert MODULE.is_target_file("agent/api_server.py")
    assert MODULE.is_target_file("agent/src/skills/script_loader.py")
    assert not MODULE.is_target_file("frontend/src/pages/Agent.tsx")


def test_backend_target_classification_is_separate_from_skill_text_targets():
    assert MODULE.is_skill_text_target(".github/skills/runtime-code-sanitizer/SKILL.md")
    assert MODULE.is_skill_text_target("agent/src/skills/app-infra/productivity/feishu-bot-meeting-coordinator/SKILL.md")
    assert not MODULE.is_skill_text_target("agent/src/runtime_prompt_policy.py")
    assert MODULE.is_backend_target("agent/src/runtime_prompt_policy.py")
    assert not MODULE.is_backend_target(".github/skills/runtime-code-sanitizer/SKILL.md")


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


def test_scan_content_flags_absolute_temp_paths():
    violations = MODULE.scan_content("- Save the review card to /tmp/meeting_confirm.md before replying.\n")
    assert any(v.rule_id == "prompt_absolute_temp_path" for v in violations)


def test_scan_content_ignores_negative_policy_text():
    violations = MODULE.scan_content(
        "- Do not use `write_file` in prompts.\n"
        "- File ops must live in deterministic code.\n"
    )
    assert violations == []


def test_scan_backend_content_flags_single_location_skill_lookup_without_fallback():
    violations = MODULE.scan_backend_content(
        'skills_dir = Path(__file__).resolve().parent / "skills"\n'
        'skill_file = skills_dir / skill_name / "SKILL.md"\n'
        'text = skill_file.read_text(encoding="utf-8")\n'
    )

    assert any(v.rule_id == "backend_single_location_skill_lookup" for v in violations)


def test_scan_backend_content_allows_recursive_skill_fallback():
    violations = MODULE.scan_backend_content(
        'skills_dir = Path(__file__).resolve().parent / "skills"\n'
        'candidate_files = [skills_dir / skill_name / "SKILL.md"]\n'
        'for nested in skills_dir.rglob("SKILL.md"):\n'
        '    pass\n'
    )

    assert violations == []