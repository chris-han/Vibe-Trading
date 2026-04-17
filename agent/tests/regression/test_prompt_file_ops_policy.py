from __future__ import annotations

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