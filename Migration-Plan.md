# Migration Plan: Vibe-Trading WebUI + Tools -> Hermes Agent Backend

## Overview

**Revised strategy (April 2026):** The end-state is `api_server.py` as a thin FastAPI
wrapper that calls Hermes `AIAgent` directly. The custom `src/agent/`, `src/providers/`,
and `src/skills/` layers are **removed**; their job is done by Hermes. The application
still owns its backend/domain implementations in `src/tools/` plus the Hermes-facing
tool definitions in `src/vibe_trading_helper.py` and `agent/src/plugins/vibe_trading/`. Only the API surface, SSE bus, session/swarm
stores, models, and Hermes runtime integration remain in Vibe-Trading.

A `HermesAdapter` shim was initially considered but rejected: it creates a permanent
translation layer with no long-term benefit. Direct usage of `AIAgent.chat()` and
`AIAgent.run_conversation()` is simpler, requires no ongoing maintenance, and gives
`api_server.py` full access to Hermes capabilities (streaming, multi-provider, memory,
parallel tools, token budget, trajectory saving) without indirection.

### Target Architecture

```
BEFORE
------
React UI -> FastAPI (api_server.py)
              -> SessionService
                  -> AgentLoop  <- src/agent/loop.py
                       -> src/providers/chat.py (ChatLLM)
                       -> src/tools/ (18 tools)
              -> WorkflowRuntime
                  -> worker.py (custom ReAct loop per task)

AFTER
-----
React UI -> FastAPI (api_server.py)           [UNCHANGED]
              -> SessionService               [KEPT: stores + SSE only]
                  -> AIAgent (Hermes direct)  [REPLACES AgentLoop]
                       -> hermes-agent toolsets (file, web, bash, ...)
                       -> vibe_trading plugin toolset [NEW]
              -> WorkflowRuntime                 [KEPT: DAG orchestration only]
                  -> AIAgent per task         [REPLACES worker.py]

REMOVED
-------
  agent/src/agent/        (loop, context, memory, tools, trace, skills)
  agent/src/providers/    (chat.py / ChatLLM)
  agent/src/skills/       (skill loading -> Hermes has its own skill system)

KEPT
----
  agent/api_server.py           (FastAPI routes - unchanged)
  agent/src/session/models.py   (Attempt, Message, Session dataclasses)
  agent/src/session/store.py    (SQLite persistence)
  agent/src/session/events.py   (SSE EventBus)
  agent/src/session/service.py  (lifecycle - rewritten to use AIAgent directly)
  agent/src/swarm/              (YAML presets, DAG, TaskStore, SwarmStore)
  agent/src/core/state.py       (RunStateStore - run dir creation/status)
  agent/src/backtest/           (backtest engine - kept as finance domain)
  agent/src/tools/              (backend/domain implementations used by Hermes-facing wrappers)
    agent/src/vibe_trading_helper.py (shared Vibe-Trading plugin/runtime implementation)
  agent/src/ui_services.py      (run analysis helpers)
  hermes-agent/                 (used as library/runtime, no app-specific tool code)
```

---

## Phase 0: Baseline Snapshot (Day 1)

Before touching any execution code, record the current SSE event shapes so we
can catch regressions during migration.

### 0.1 Prerequisites

| Requirement | Command |
|---|---|
| Python >= 3.11 | `python --version` |
| Hermes installed into agent venv | `cd hermes-agent && uv pip install -e ".[dev]"` |
| Vibe-Trading installed | `cd agent && uv pip install -e .` |

### 0.2 Snapshot Events

Capture and freeze:
1. Single-agent SSE event sequence (session -> attempt.started -> tool_call -> tool_result -> attempt.completed)
2. Swarm SSE sequence (run_started -> task_started -> task_completed -> run_completed)
3. Response payload shapes for `/sessions/{id}/events` and `/swarm/runs/{id}/events`

These become the migration safety net in Phase 4.

---

## Phase 1: Hermes Runtime Plugin Integration (Week 1, Day 1-2)

Create application-owned Hermes plugin/runtime modules under `agent/src/` and `agent/src/plugins/vibe_trading/`
and register them through the installed Hermes entry-point plugin in `agent/src/plugins/vibe_trading/`.
The schemas and handlers stay in the Vibe-Trading application layer; Hermes loads them
at runtime through `hermes_agent.plugins` entry-point discovery.

### 1.1 Files

```text
agent/src/vibe_trading_helper.py
agent/src/hermes_tool_adapter/vibe_trading_compat.py (deleted)
agent/src/plugins/vibe_trading/__init__.py
agent/src/plugins/vibe_trading/schemas.py
agent/src/plugins/vibe_trading/tools.py
```

### 1.2 Runtime Registration Flow

1. Hermes starts with the Vibe-Trading agent package installed in its runtime environment.
2. `agent/pyproject.toml` exposes `vibe-trading = "src.plugins.vibe_trading"` in the `hermes_agent.plugins` group.
3. Hermes discovers that plugin entry point.
4. The plugin imports:
    - `src.vibe_trading_helper`
    - `src.hermes_tool_adapter.vibe_trading_compat` (deleted)
5. The plugin calls `ctx.register_tool(...)` for each exported tool spec.

### 1.3 Tool Compatibility Matrix

| Old Vibe-Trading Tool   | Hermes Replacement              | Action          |
|-------------------------|---------------------------------|-----------------|
| `BashTool`              | `terminal_tool.py`              | Use Hermes      |
| `ReadFileTool`          | `file_tools.py`                 | Use Hermes      |
| `WriteFileTool`         | `file_tools.py`                 | Use Hermes      |
| `EditFileTool`          | `file_operations.py`            | Use Hermes      |
| `WebReaderTool`         | `web_reader_tool.py`            | Use Hermes      |
| `DocReaderTool`         | `file_tools.py` (PDF extract)   | Use Hermes      |
| `LoadSkillTool`         | Hermes skill system             | Use Hermes      |
| `BacktestTool`          | `vibe_trading.backtest` | Plugin toolset |
| `FactorAnalysisTool`    | `vibe_trading`          | Plugin toolset |
| `OptionsPricingTool`    | `vibe_trading`          | Plugin toolset |
| `PatternTool`           | `vibe_trading`          | Plugin toolset |
| `SubagentTool`          | `delegate_tool.py`              | Use Hermes      |
| `SwarmTool`             | WorkflowRuntime (API call)         | Keep in API     |
| `CompactTool`           | Built-in Hermes compression     | Remove          |
| `BackgroundRunTool`     | `cronjob_tools.py`              | Use Hermes      |
| `TaskCreateTool`        | `todo_tool.py`                  | Use Hermes      |

---

## Phase 2: Rewrite SessionService to Use AIAgent Directly (Week 1, Day 3-4)

Replace `_run_with_agent()` in `agent/src/session/service.py`. Everything else
in `SessionService` (CRUD, SSE emit, history trimming) stays the same.

### 2.1 New `_run_with_agent()` implementation

```python
async def _run_with_agent(self, attempt: Attempt, messages: list = None) -> Dict[str, Any]:
    import os
    import sys
    from pathlib import Path

    _HERMES = Path(__file__).resolve().parents[3] / "hermes-agent"
    if str(_HERMES) not in sys.path:
        sys.path.insert(0, str(_HERMES))

    from run_agent import AIAgent
    from src.core.state import RunStateStore

    sid = attempt.session_id
    attempt_id = attempt.attempt_id

    state_store = RunStateStore()
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    run_dir = state_store.create_run_dir(RUNS_DIR)

    # SSE bridge callbacks
    def _on_tool_progress(event_type, tool_name, preview, args, **kwargs):
        if event_type == "tool.started":
            self.event_bus.emit(sid, "tool_call", {
                "attempt_id": attempt_id,
                "tool": tool_name,
                "args": args or {},
            })
        elif event_type == "tool.completed":
            self.event_bus.emit(sid, "tool_result", {
                "attempt_id": attempt_id,
                "tool": tool_name,
                "is_error": kwargs.get("is_error", False),
            })

    def _on_delta(chunk: str):
        self.event_bus.emit(sid, "text_delta", {
            "attempt_id": attempt_id,
            "content": chunk,
        })

    agent = AIAgent(
        model=os.getenv("HERMES_MODEL", ""),
        max_iterations=50,
        quiet_mode=True,
        session_id=sid,
        enabled_toolsets=["development", "research", "vibe_trading"],
        tool_progress_callback=_on_tool_progress,
        stream_delta_callback=_on_delta,
        ephemeral_system_prompt=f"Run directory: {run_dir}\nSession: {sid}",
        skip_context_files=True,
    )
    self._active_loops[sid] = agent

    history = self._convert_messages_to_history(messages) if messages else []

    try:
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            _AGENT_EXECUTOR,
            lambda: agent.run_conversation(
                user_message=attempt.prompt,
                conversation_history=history,
            ),
        )
        final_text = (result.get("final_response") or "").strip()
        state_store.mark_success(run_dir)
        return {
            "status": "success",
            "content": final_text,
            "run_dir": str(run_dir),
            "run_id": run_dir.name,
        }
    except Exception as exc:
        state_store.mark_failure(run_dir, str(exc))
        return {
            "status": "failed",
            "reason": str(exc),
            "content": "",
            "run_dir": str(run_dir),
            "run_id": run_dir.name,
        }
    finally:
        self._active_loops.pop(sid, None)
```

### 2.2 Update `cancel_current()`

```python
def cancel_current(self, session_id: str) -> bool:
    agent = self._active_loops.get(session_id)
    if agent is None:
        return False
    agent.interrupt("cancelled by user")   # AIAgent.interrupt() not cancel()
    return True
```

---

## Phase 3: Rewrite Swarm Worker to Use AIAgent Directly (Week 1, Day 5)

Replace `agent/src/swarm/worker.py`. The `WorkflowRuntime` DAG orchestration,
`TaskStore`, retries, SSE events, and topological scheduling are **unchanged**.
Only the inner execution loop changes.

### 3.1 New `run_worker()` signature (same as before)

```python
def run_worker(
    agent_spec: SwarmAgentSpec,
    task: SwarmTask,
    upstream_summaries: dict[str, str],
    user_vars: dict[str, str],
    run_dir: Path,
    event_callback: Callable[[SwarmEvent], None] | None = None,
) -> WorkerResult:
    import sys
    from pathlib import Path as _Path

    _HERMES = _Path(__file__).resolve().parents[3] / "hermes-agent"
    if str(_HERMES) not in sys.path:
        sys.path.insert(0, str(_HERMES))

    from run_agent import AIAgent

    agent_id = agent_spec.id
    task_id = task.id

    _emit(event_callback, "worker_started", agent_id, task_id)

    # Build system prompt (same content as before, minus the tool list since
    # Hermes injects its own tool descriptions)
    system_prompt = build_worker_prompt(agent_spec, upstream_summaries, skill_descriptions="")

    try:
        user_prompt = task.prompt_template.format(**user_vars)
    except KeyError as exc:
        error_msg = f"Missing variable in prompt template: {exc}"
        _emit(event_callback, "worker_failed", agent_id, task_id, {"error": error_msg})
        return WorkerResult(status="failed", summary="", iterations=0, error=error_msg,
                            input_tokens=0, output_tokens=0)

    artifact_dir = run_dir / "artifacts" / agent_id
    artifact_dir.mkdir(parents=True, exist_ok=True)

    def _on_progress(event_type, tool_name, preview, args, **kwargs):
        if event_type == "tool.started":
            _emit(event_callback, "tool_call", agent_id, task_id,
                  {"tool": tool_name, "args": args or {}})

    agent = AIAgent(
        model=agent_spec.model_name or "",
        max_iterations=agent_spec.max_iterations or 50,
        quiet_mode=True,
        session_id=f"swarm-{task_id}",
        enabled_toolsets=["development", "research", "vibe_trading"],
        tool_progress_callback=_on_progress,
        ephemeral_system_prompt=system_prompt + f"\nRun directory: {artifact_dir}",
        skip_context_files=True,
    )

    result = agent.run_conversation(user_message=user_prompt)
    summary = (result.get("final_response") or "").strip()

    _write_summary(artifact_dir, summary)
    _emit(event_callback, "worker_completed", agent_id, task_id)
    return WorkerResult(
        status="completed",
        summary=summary,
        artifact_paths=_collect_artifacts(artifact_dir),
        iterations=0,           # AIAgent does not expose iteration count externally
        input_tokens=0,
        output_tokens=0,
    )
```

---

## Phase 4: Delete Replaced Code (Week 2, Day 1-2)

After both session and swarm paths are green against the Phase 0 fixtures:

| Path | Action |
|---|---|
| `agent/src/agent/` | **DELETE** (loop, context, memory, tools, trace, skills) |
| `agent/src/providers/` | **DELETE** (ChatLLM) |
| `agent/src/tools/` | **DELETE** (all 18 tools replaced by Hermes + finance toolset) |
| `agent/src/skills/` | **DELETE** (Hermes skill system used instead) |
| `agent/src/agent/hermes_adapter.py` | **DELETE** (adapter approach abandoned) |

`api_server.py` imports of `src.agent`, `src.providers`, `src.tools` are removed at this step.

---

## Phase 5: Provider Configuration (Week 2, Day 3)

After deletion, model/provider config follows Hermes conventions only.

```yaml
# ~/.hermes/config.yaml
model:
  default: "anthropic/claude-opus-4.6"
  provider: "openrouter"
  base_url: "https://openrouter.ai/api/v1"
```

```bash
# ~/.hermes/.env
OPENROUTER_API_KEY=sk-or-...
```

`HERMES_MODEL` environment variable can override the default for the Vibe-Trading
`api_server.py` process.

Legacy `LANGCHAIN_*` env vars are dropped during this phase.

---

## Phase 6: Optional Enhancements (Week 3+)

Once the core migration is stable:

### 6.1 Session Memory (RAG)
Hermes `MemoryManager` with vector search — sessions accumulate searchable history
("use the same strategy from last week's run").

### 6.2 Trajectory Saving
```python
AIAgent(..., save_trajectories=True, trajectories_dir=run_dir / "trajectories")
```
Slots into existing `runs/{run_id}/` directory structure.

### 6.3 MoA Routing (Deferred)
Add `execution_mode: ai_agent | moa | auto` to YAML agent specs.
Use Hermes `mixture_of_agents` for synthesis-heavy tasks only.

---

## Phase 7: Testing

### 7.1 Current checked-in regression coverage

The repository currently contains these migration-relevant regression tests:

```text
agent/tests/regression/
├── test_hermes_sse_regression.py      # Hermes SessionService + SSE bridge regressions
├── test_backtest_bootstrap.py         # run dir/bootstrap behavior
├── test_runtime_dependency_manifest.py
├── test_runtime_env.py
└── test_web_reader_tool.py
```

### 7.2 Recommended replay commands after upstream sync

Run these after updating the vendored `hermes-agent/` copy or rebasing onto a newer upstream snapshot:

```bash
cd agent && uv run pytest tests/regression/test_hermes_sse_regression.py
cd agent && uv run pytest \
  tests/regression/test_backtest_bootstrap.py \
  tests/regression/test_runtime_env.py \
  tests/regression/test_web_reader_tool.py
```

### 7.3 Manual smoke checks

1. **Single-agent session run**
   - Submit a normal chat/backtest prompt from the UI.
   - Verify SSE deltas/tool events stream correctly.
   - Verify the returned run directory has `state.json`, `artifacts/`, and expected report/metrics files.

2. **Swarm run**
   - Launch a preset from the Full Report / swarm flow.
   - Verify each worker writes only under `runs/<run_id>/artifacts/<agent_id>/`.

3. **Artifact isolation**
   - Confirm no stray runtime files appear under `agent/` root (for example `agent/*.csv`).
   - Confirm relative-path writes from bash or generated scripts land inside the active artifact directory.

4. **Frontend status rendering**
   - If a run has no explicit failure and status is `unknown`, verify the Full Report page shows a neutral icon rather than a red error icon.

---

## Current Migration Status (2026-04-11)

| Area | Status | Current implementation |
|---|---|---|
| Hermes entry-point plugin registration | ✅ Complete | `agent/src/plugins/vibe_trading/` loads `src.vibe_trading_helper` |
| Session execution migrated to Hermes | ✅ Complete | `agent/src/session/service.py::_run_with_agent()` uses `AIAgent.run_conversation()` |
| Swarm worker execution migrated to Hermes | ✅ Complete | `agent/src/swarm/worker.py` runs one `AIAgent` per task |
| Legacy `src/agent/` / `src/providers/` layers | ✅ Removed | No longer part of runtime path |
| Domain/backend tools in `src/tools/` | ✅ Intentionally kept | Still owned by Vibe-Trading; wrapped via Hermes-facing adapter tools |
| Runtime artifact file controls | ✅ Hardened | `set_artifact_dir()` + `_resolve_write_path()` + bash `cwd` fallback to artifact dir |
| Returned run status propagation | ✅ Hardened | `state.json` is propagated to the final `run_id` directory returned to the UI |
| Frontend unknown-status handling | ✅ Hardened | `frontend/src/pages/RunDetail.tsx` shows neutral icon for non-failed unknown states |
| Optional memory / trajectory enhancements | ⏳ Deferred | Still optional follow-up work |

### Current local invariants to preserve

When replaying this migration after an upstream Hermes update, the following behaviors are **mandatory** and should be treated as acceptance criteria:

1. **No app-specific patches inside `hermes-agent/`**
   - Hermes remains vendored/upstream-owned.
    - All Vibe-Trading behavior lives in app-owned files under `agent/src/vibe_trading_helper.py`, `agent/src/plugins/vibe_trading/`, `agent/src/session/`, and `agent/src/swarm/`.

2. **All runtime writes stay inside the active run directory**
   - `write_file` relative/out-of-tree paths are redirected into the active artifact directory.
   - `bash` execution uses the artifact directory as `cwd` when no explicit `run_dir` is provided.
   - Agent-generated scripts using `open()`, `to_csv()`, etc. therefore resolve relative paths inside the artifact directory rather than the process cwd.

3. **The `run_id` returned to the frontend must contain `state.json`**
   - This remains true even when the backtest engine creates its own run directory and the API returns that directory instead of the wrapper/session run directory.

4. **Swarm artifacts remain isolated per agent**
   - Worker outputs must land in `runs/<run_id>/artifacts/<agent_id>/`.

---

## Upstream Update Replay Procedure

Use this checklist whenever `hermes-agent/` is refreshed from upstream and the Vibe-Trading integration needs to be revalidated or re-applied.

### Step 1 — Refresh the upstream Hermes runtime

```bash
cd hermes-agent && uv pip install -e ".[dev]"
cd ../agent && uv pip install -e .
```

### Step 2 — Reconfirm the app-owned integration surfaces

These files are the canonical Vibe-Trading migration surface and must remain intact after the update:

- `agent/src/plugins/vibe_trading/__init__.py`
- `agent/src/plugins/vibe_trading/schemas.py`
- `agent/src/plugins/vibe_trading/tools.py`
- `agent/src/vibe_trading_helper.py`
- `agent/src/hermes_tool_adapter/vibe_trading_compat.py` (deleted)
- `agent/src/session/service.py`
- `agent/src/swarm/worker.py`
- `agent/src/core/state.py`
- `frontend/src/pages/RunDetail.tsx` *(UI hardening for unknown status)*

### Step 3 — Reapply the runtime artifact-control hardening if needed

After any upstream sync, explicitly verify these implementation details still exist:

- `vibe_trading_compat.py` (deleted)
  - `_artifact_dir_var` context variable
  - `set_artifact_dir()` / `reset_artifact_dir()`
  - `_resolve_write_path()` redirect logic
  - `_bash()` fallback to `args.get("run_dir") or _artifact_dir_var.get()`

- `session/service.py`
  - `set_artifact_dir(run_dir / "artifacts")` around `agent.run_conversation()`
  - `actual_run_dir = latest_backtest_run_dir or latest_prepared_run_dir or result.get("run_dir")`
  - `state.json` propagation to the final returned run directory

- `swarm/worker.py`
  - `set_artifact_dir(run_dir / "artifacts" / agent_id)` around each worker execution

### Step 4 — Verify with regression + smoke checks

Run the tests in **Phase 7**, then execute one single-agent run and one swarm run from the UI.

### Step 5 — Check for stray files

After the smoke runs, confirm there are no new runtime outputs written to the repo root or `agent/` root:

```bash
find agent -maxdepth 1 \( -name '*.csv' -o -name '*.json' -o -name '*.md' \) \
  ! -name 'README.md' ! -name 'pyproject.toml' ! -name 'config.json'
```

If unexpected outputs appear there, treat it as a regression in artifact control and re-check the bash `cwd` enforcement and path-redirection logic.

---

## Implementation Sequence

```
Week 1
  Day 1:   Phase 0 -- snapshot SSE event shapes
    Day 2:   Phase 1 -- Hermes plugin + app-owned plugin runtime module
  Day 3-4: Phase 2 -- rewrite SessionService._run_with_agent()
  Day 5:   Phase 3 -- rewrite swarm worker.py

Week 2
  Day 1-2: Phase 4 -- delete src/agent/, src/providers/, src/tools/, src/skills/
  Day 3:   Phase 5 -- provider config cleanup, drop LANGCHAIN_* vars
  Day 4-5: Phase 7 -- regression + unit tests pass

Week 3+
  Phase 6 -- optional: memory, trajectories, MoA
```

---

## Risk Register

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Hermes plugin toolsets missing a capability needed by VT | Medium | Medium | Runtime plugin fills domain gap; Hermes has bash/file/web natively |
| Thread safety: AIAgent internal asyncio vs SessionService threads | Medium | High | AIAgent.run_conversation() is synchronous and thread-safe; use run_in_executor |
| SSE event shape mismatch after rewrite | Medium | Medium | Phase 0 fixture replay catches this before deletion |
| run_dir / artifact_dir not propagated to runtime writes | Low | Medium | Enforce `set_artifact_dir()` context, `_resolve_write_path()` redirection, and bash `cwd` fallback to the active artifact directory |
| Swarm worker loses token count tracking | Low | Low | AIAgent does not expose per-call token counts; drop from WorkerResult |

---

## File Change Summary

| File / Path | Migration action | Current status |
|---|---|---|
| `agent/src/vibe_trading_helper.py` | **CREATE** plugin tool definitions | Active, app-owned integration surface |
| `agent/src/hermes_tool_adapter/vibe_trading_compat.py` | **CREATE** compatibility/runtime control definitions | Deleted; replaced by Hermes built-ins + `register_task_env_overrides` |
| `agent/src/plugins/vibe_trading/` | **CREATE** runtime registration plugin | Active; this is the preferred hook point for replaying the migration |
| `agent/src/session/service.py` | **REWRITE** `_run_with_agent()` + `cancel_current()` | Active; direct Hermes execution + final `run_id` state propagation |
| `agent/src/swarm/worker.py` | **REWRITE** `run_worker()` | Active; per-worker artifact isolation enforced |
| `agent/src/agent/hermes_adapter.py` | **DELETE** | Abandoned; do not reintroduce |
| `agent/src/agent/` | **DELETE** | Removed from runtime |
| `agent/src/providers/` | **DELETE** | Removed from runtime |
| `agent/src/tools/` | **KEEP** | Intentionally retained as backend/domain implementation layer |
| `agent/src/skills/` | **REVIEW / OPTIONAL CLEANUP** | Still present in repo; do not delete blindly during replay without checking references |
| `frontend/src/pages/RunDetail.tsx` | **PATCH** | UI hardening for `unknown` vs `failed` run status |

**App-owned files that should remain stable across upstream Hermes updates:**
- `agent/src/plugins/vibe_trading/*`
- `agent/src/vibe_trading_helper.py`
- `agent/src/session/service.py`
- `agent/src/swarm/worker.py`
- `agent/src/core/state.py`
- `agent/src/backtest/`
- `agent/src/ui_services.py`
- `agent/api_server.py`
- `frontend/src/pages/RunDetail.tsx`

**Vendored/upstream-owned area that should stay clean:**
- `hermes-agent/` — update from upstream, but keep Vibe-Trading-specific logic out of this tree whenever possible.
