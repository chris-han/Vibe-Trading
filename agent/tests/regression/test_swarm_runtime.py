from __future__ import annotations

import threading
import time
from datetime import datetime, timezone

from src.swarm.models import RunStatus, SwarmAgentSpec, SwarmRun, SwarmTask, WorkerResult
from src.swarm.runtime import WorkflowRuntime
from src.swarm.store import SwarmStore


def _sample_run(timeout_seconds: int = 1) -> SwarmRun:
    return SwarmRun(
        id="swarm-test-timeout",
        preset_name="test_preset",
        status=RunStatus.pending,
        user_vars={},
        agents=[
            SwarmAgentSpec(
                id="worker",
                role="Test Worker",
                system_prompt="You are a test worker.",
                timeout_seconds=timeout_seconds,
                max_retries=0,
            )
        ],
        tasks=[
            SwarmTask(
                id="task-1",
                agent_id="worker",
                prompt_template="Run the task.",
                depends_on=[],
                blocked_by=[],
            )
        ],
        created_at=datetime.now(timezone.utc).isoformat(),
    )


def test_workflow_runtime_finishes_hung_runs_after_worker_timeout(tmp_path, monkeypatch):
    store = SwarmStore(base_dir=tmp_path)
    runtime = WorkflowRuntime(store=store, max_workers=1)
    run = _sample_run(timeout_seconds=1)

    def _hang_forever(**kwargs):
        threading.Event().wait(60)
        return WorkerResult(status="completed", summary="unexpected")

    monkeypatch.setattr("src.swarm.runtime.build_run_from_preset", lambda preset_name, user_vars: run)
    monkeypatch.setattr("src.swarm.runtime.run_worker", _hang_forever)

    started = runtime.start_run("ignored", {})

    deadline = time.monotonic() + 2.5
    current = store.load_run(started.id)
    while (
        current is not None
        and current.status in (RunStatus.pending, RunStatus.running)
        and time.monotonic() < deadline
    ):
        time.sleep(0.05)
        current = store.load_run(started.id)

    assert current is not None
    assert current.status not in (RunStatus.pending, RunStatus.running)
    assert current.completed_at is not None
