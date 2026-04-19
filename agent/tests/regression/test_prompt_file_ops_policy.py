from __future__ import annotations

from types import SimpleNamespace

from src import runtime_prompt_policy
from src.swarm import worker as swarm_worker


def test_session_workflow_prompts_do_not_encode_file_or_dir_operations():
    banned_fragments = [
        "write_file",
        "edit_file",
        "uploads/",
        "config.json",
        "code/signal_engine.py",
        "hardcode output file paths",
        "keep output paths relative",
    ]
    combined = "\n".join(
        [
            runtime_prompt_policy.BACKTEST_WORKFLOW_PROMPT,
            runtime_prompt_policy.DOCUMENT_WORKFLOW_PROMPT,
            runtime_prompt_policy.MARKET_DATA_WORKFLOW_PROMPT,
        ]
    )

    for fragment in banned_fragments:
        assert fragment not in combined

    assert "current workspace upload area" in runtime_prompt_policy.DOCUMENT_WORKFLOW_PROMPT
    assert "Never search Desktop, Downloads, /mnt" in runtime_prompt_policy.DOCUMENT_WORKFLOW_PROMPT


def test_swarm_workflow_hints_do_not_encode_file_or_dir_operations():
    banned_fragments = [
        "write_file",
        "edit_file",
        "config.json",
        "code/signal_engine.py",
        "hardcode output file paths",
        "Worker file tools",
    ]
    prompt = swarm_worker.build_worker_prompt(
        SimpleNamespace(role="analyst", system_prompt="{upstream_context}"),
        {},
        "",
    )

    for fragment in banned_fragments:
        assert fragment not in prompt

    assert runtime_prompt_policy.BACKTEST_WORKFLOW_PROMPT in prompt
    assert runtime_prompt_policy.DOCUMENT_WORKFLOW_PROMPT in prompt
    assert runtime_prompt_policy.MARKET_DATA_WORKFLOW_PROMPT in prompt
    assert "current workspace upload area" in prompt
    assert "Never search Desktop, Downloads, /mnt" in prompt


def test_session_and_swarm_runtime_prompts_share_common_policy_source():
    prompt = swarm_worker.build_worker_prompt(
        SimpleNamespace(role="analyst", system_prompt="{upstream_context}"),
        {},
        "",
    )

    assert runtime_prompt_policy.BACKTEST_WORKFLOW_PROMPT in prompt
    assert runtime_prompt_policy.DOCUMENT_WORKFLOW_PROMPT in prompt
    assert runtime_prompt_policy.MARKET_DATA_WORKFLOW_PROMPT in prompt


def test_output_format_prompt_lives_in_runtime_prompt_policy():
    assert "Markdown pipe-tables" in runtime_prompt_policy.OUTPUT_FORMAT_PROMPT
    assert "echarts blocks" in runtime_prompt_policy.OUTPUT_FORMAT_PROMPT


def test_skill_writes_are_routed_through_skill_manage_policy():
    prompt = runtime_prompt_policy.MARKET_DATA_WORKFLOW_PROMPT

    assert "use skill_manage instead of general file-editing tools" in prompt
    assert "active workspace HERMES_HOME/skills directory" in prompt
    assert "relative .hermes/skills paths resolve inside the active run/artifacts sandbox" in prompt