from __future__ import annotations

from src import runtime_prompt_policy
from src.session import service as session_service
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
            session_service._BACKTEST_WORKFLOW_PROMPT,
            session_service._DOCUMENT_WORKFLOW_PROMPT,
            session_service._MARKET_DATA_WORKFLOW_PROMPT,
        ]
    )

    for fragment in banned_fragments:
        assert fragment not in combined

    assert "current workspace upload area" in session_service._DOCUMENT_WORKFLOW_PROMPT
    assert "Never search Desktop, Downloads, /mnt" in session_service._DOCUMENT_WORKFLOW_PROMPT


def test_swarm_workflow_hints_do_not_encode_file_or_dir_operations():
    banned_fragments = [
        "write_file",
        "edit_file",
        "config.json",
        "code/signal_engine.py",
        "hardcode output file paths",
        "Worker file tools",
    ]
    combined = "\n".join(
        [
            swarm_worker._BACKTEST_WORKFLOW_HINT,
            swarm_worker._DOCUMENT_WORKFLOW_HINT,
            swarm_worker._MARKET_DATA_WORKFLOW_HINT,
        ]
    )

    for fragment in banned_fragments:
        assert fragment not in combined

    assert "current workspace upload area" in swarm_worker._DOCUMENT_WORKFLOW_HINT
    assert "Never search Desktop, Downloads, /mnt" in swarm_worker._DOCUMENT_WORKFLOW_HINT


def test_session_and_swarm_runtime_prompts_share_common_policy_source():
    assert session_service._BACKTEST_WORKFLOW_PROMPT == runtime_prompt_policy.BACKTEST_WORKFLOW_PROMPT
    assert session_service._DOCUMENT_WORKFLOW_PROMPT == runtime_prompt_policy.DOCUMENT_WORKFLOW_PROMPT
    assert session_service._MARKET_DATA_WORKFLOW_PROMPT == runtime_prompt_policy.MARKET_DATA_WORKFLOW_PROMPT
    assert session_service._OUTPUT_FORMAT_PROMPT == runtime_prompt_policy.OUTPUT_FORMAT_PROMPT

    assert swarm_worker._BACKTEST_WORKFLOW_HINT == runtime_prompt_policy.BACKTEST_WORKFLOW_PROMPT
    assert swarm_worker._DOCUMENT_WORKFLOW_HINT == runtime_prompt_policy.DOCUMENT_WORKFLOW_PROMPT
    assert swarm_worker._MARKET_DATA_WORKFLOW_HINT == runtime_prompt_policy.MARKET_DATA_WORKFLOW_PROMPT