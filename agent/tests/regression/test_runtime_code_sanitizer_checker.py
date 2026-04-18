from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
MODULE_PATH = REPO_ROOT / ".github" / "skills" / "runtime-code-sanitizer" / "scripts" / "check_sanitizers.py"
SPEC = importlib.util.spec_from_file_location("check_sanitizers", MODULE_PATH)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def test_extract_output_format_prompt_supports_shared_policy_module_name():
    source = (
        'OUTPUT_FORMAT_PROMPT = (\n'
        '    "Output format rules:\\n"\n'
        '    "- Render tables as Markdown pipe-tables.\\n"\n'
        ')\n'
    )

    prompt = MODULE._extract_output_format_prompt(source)

    assert "Markdown pipe-tables" in prompt


def test_extract_output_format_prompt_supports_legacy_session_name():
    source = (
        '_OUTPUT_FORMAT_PROMPT = (\n'
        '    "Output format rules:\\n"\n'
        '    "- Use Mermaid for diagrams and flowcharts.\\n"\n'
        ')\n'
    )

    prompt = MODULE._extract_output_format_prompt(source)

    assert "Use Mermaid for diagrams and flowcharts." in prompt


def test_check_all_passes_for_current_runtime_prompt_policy_source():
    source = (REPO_ROOT / "agent" / "src" / "runtime_prompt_policy.py").read_text(encoding="utf-8")

    results = MODULE.check_all(source)

    assert all(ok for _, ok, _ in results)