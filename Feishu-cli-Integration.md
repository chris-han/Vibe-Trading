# Feishu CLI Integration Plan

## 1. Objective

Replace the existing `feishu-bot-meeting-coordinator` skill with a new `feishu-cli-gateway` skill that wraps the official `@larksuite/cli` npm package. This provides **complete Feishu API coverage** (drive, docs, sheets, calendar, IM, contact, approval, tasks, etc.) instead of the current custom Python script limited to meeting coordination.

**Key constraints:**
- Zero modifications to `feishu-cli` Go source code.
- Reuse existing credentials from `agent/.env` (`FEISHU_APP_ID`, `FEISHU_APP_SECRET`, `FEISHU_DOMAIN`).
- Support both **webUI** and **Feishu gateway** channels without channel-specific logic in the skill.
- `@larksuite/cli` installed via npm (not built from Go source).

---

## 2. Background / Current State

### 2.1 Existing Skill (`feishu-bot-meeting-coordinator`)

**Location:** `agent/src/skills/app-infra/productivity/feishu-bot-meeting-coordinator/`

**Contents:**
- `SKILL.md` — meeting-specific instructions with hard-coded `a2ui` schema forms
- `scripts/feishu_bot_api.py` — custom Python helper (~1000 lines) implementing:
  - Tenant token acquisition
  - Contact search
  - Multi-round meeting negotiation state machine
  - Calendar event creation
  - Invitation fan-out

**Limitations:**
- Only covers meetings and contacts.
- Custom business logic (negotiation rounds) is hand-coded in Python.
- Any new Feishu API surface requires writing new Python code.

**References in codebase:**
- `agent/src/runtime_prompt_policy.py` lines 51–55: directs meeting/contact tasks to this skill.

### 2.2 Target CLI (`@larksuite/cli`)

**What it is:** The official Lark/Feishu CLI distributed via npm. Its `postinstall` script downloads the platform-native Go binary from GitHub Releases.

**Coverage:** Auto-generated commands from OpenAPI metadata for all services:
`calendar`, `contact`, `drive`, `doc`, `im`, `sheets`, `approval`, `task`, `mail`, `vc`, `wiki`, etc.

**Credential model:** Reads `LARKSUITE_CLI_APP_ID`, `LARKSUITE_CLI_APP_SECRET`, `LARKSUITE_CLI_BRAND`, `LARKSUITE_CLI_DEFAULT_AS` from environment.

---

## 3. Proposed Architecture

```
┌─────────────────────────────────────┐
│  Agent Runtime (webUI / Feishu GW)  │
│                                     │
│  skill_view("feishu-cli-gateway")   │
│         ↓                           │
│  scripts/feishu_cli_bridge.py       │
│         ↓                           │
│  Maps FEISHU_* → LARKSUITE_CLI_*   │
│         ↓                           │
│  subprocess.run([lark-cli, ...])   │
│         ↓                           │
│  JSON stdout → parsed dict         │
│         ↓                           │
│  Channel adapters render output     │
└─────────────────────────────────────┘
```

The bridge is **channel-agnostic** — it returns structured Python dicts. The existing `WebVisualizationAdapter` or `FeishuVisualizationAdapter` handles final rendering based on the active channel.

---

## 4. File Changes

### 4.1 New Files

| File | Purpose |
|------|---------|
| `agent/src/skills/app-infra/productivity/feishu-cli-gateway/SKILL.md` | Skill definition and LLM instructions |
| `agent/src/skills/app-infra/productivity/feishu-cli-gateway/scripts/feishu_cli_bridge.py` | Python bridge: env mapping + CLI invocation |
| `agent/Makefile` | Local setup target for npm dependency |
| `agent/package.json` | Tracks `@larksuite/cli` npm dependency |

### 4.2 Modified Files

| File | Change |
|------|--------|
| `/home/chris/repo/semantier/Dockerfile` | Install Node.js + `@larksuite/cli` in runtime stage |
| `agent/src/runtime_prompt_policy.py` | Replace `feishu-bot-meeting-coordinator` references with `feishu-cli-gateway` |
| `agent/README.md` | Add npm/setup note |

### 4.3 Deleted Files

| Path | Reason |
|------|--------|
| `agent/src/skills/app-infra/productivity/feishu-bot-meeting-coordinator/` | Replaced by new skill |

---

## 5. Sandbox Injection & Runtime Pattern

Per the semantier architecture doc (Section 6.1 *网关集成统一架构模式* and Section 10 *Wrapper 级 Trajectory 开关与落盘边界*), the `feishu-cli-gateway` must follow the **Control Plane → Execution Plane → Sandbox Isolation** pattern:

| Layer | Responsibility | Implementation |
|-------|---------------|----------------|
| **Control Plane** (`/agent`) | Workspace resolution, credential persistence, config loading | `agent/.env` + `runtime_prompt_policy.py` |
| **Execution Plane** (Bridge) | Platform adapter, credential injection, CLI invocation | `scripts/feishu_cli_bridge.py` |
| **Sandbox Isolation** | Per-invocation temp scope, no cross-workspace leakage, no user-workspace pollution | `tempfile.mkdtemp()` for `LARKSUITE_CLI_CONFIG_DIR` + `LARKSUITE_CLI_LOG_DIR` |

**Key constraints from architecture:**
1. **默认不做平台特例转发** — the skill must not create a separate backend delegation architecture; it uses the standard agent tool-execution path.
2. **轨迹文件强制写入 wrapper 作用域** — any CLI-generated artifacts (config, logs, downloads, cache) must stay in wrapper/temp scope, NOT in `workspaces/<user_id>/`.
3. **请求级隔离** — each `run()` invocation gets a fresh, isolated config directory to prevent session drift and cross-tenant contamination.

---

## 6. Implementation Details

### 6.1 Bridge Script (`scripts/feishu_cli_bridge.py`)

Responsibilities:
1. Bootstrap `agent/.env` using the same traversal logic as `feishu_bot_api.py`.
2. Map `FEISHU_*` environment variables to `LARKSUITE_CLI_*`.
3. Resolve the `lark-cli` binary location (PATH → `agent/node_modules/.bin` → `agent/node_modules/@larksuite/cli/bin`).
4. **Sandbox injection**: create a per-invocation temp directory and set `LARKSUITE_CLI_CONFIG_DIR` and `LARKSUITE_CLI_LOG_DIR`.
5. Provide a `run(args: list[str]) -> dict` helper that invokes the CLI with `--format json`.
6. Parse the JSON envelope (`{"code", "msg", "data"}`) and return it.
7. Surface CLI errors as Python exceptions.
8. **Cleanup**: remove the temp config directory after execution (or use `tempfile.TemporaryDirectory`).

**Credential mapping:**

| Source (`agent/.env`) | Target env var | Value / Rule |
|---|---|---|
| `FEISHU_APP_ID` | `LARKSUITE_CLI_APP_ID` | Direct mapping |
| `FEISHU_APP_SECRET` | `LARKSUITE_CLI_APP_SECRET` | Direct mapping |
| `FEISHU_DOMAIN` | `LARKSUITE_CLI_BRAND` | `feishu` → `feishu`, `lark` → `lark`; default `feishu` |
| — | `LARKSUITE_CLI_DEFAULT_AS` | Hard-code to `bot` (matches existing bot-centric flow) |

**Sandbox environment injection:**

```python
import tempfile
import shutil
from pathlib import Path

def run(args: list[str]) -> dict:
    env = {k: v for k, v in _ENV_MAP.items() if v is not None}
    env.update(os.environ)
    
    # Sandbox isolation: per-invocation temp config directory
    # This prevents cross-workspace contamination and avoids writing to ~/.lark-cli
    with tempfile.TemporaryDirectory(prefix="lark-cli-") as sandbox_dir:
        env["LARKSUITE_CLI_CONFIG_DIR"] = sandbox_dir
        env["LARKSUITE_CLI_LOG_DIR"] = sandbox_dir  # keep logs in sandbox too
        
        # For file downloads, default to sandbox unless user overrides
        if "--output" not in args:
            # If the command is known to produce binary output, redirect to sandbox
            pass  # handled per-command in SKILL.md instructions
        
        bin_path = _resolve_binary()
        result = subprocess.run(
            [bin_path, *args, "--format", "json"],
            capture_output=True,
            text=True,
            env=env,
            cwd=sandbox_dir,  # keep cwd in sandbox to avoid workspace pollution
        )
        
        # Parse JSON envelope...
```

**Binary resolution order:**
1. `shutil.which("lark-cli")` (global / Docker install)
2. `agent/node_modules/.bin/lark-cli` (local dev install)
3. `agent/node_modules/@larksuite/cli/bin/lark-cli` (direct binary)

**Output boundary rules:**
- The bridge returns **parsed JSON dicts**, never raw file paths in the user's workspace.
- If a command produces a file download (e.g., `drive files download --output ...`), the bridge should:
  - Default the output path to the sandbox temp dir
  - Return the file content as base64 or bytes in the dict, OR
  - Return the sandbox-local path and let the caller read it, then clean up.
- **Never** write downloads, cache, or config to `workspaces/<user_id>/` unless the user explicitly requests persistent storage.

**Key API surface for LLM:**
- `run(["contact", "user", "--query", "Amy", "--format", "json"])`
- `run(["calendar", "events", "instance_view", "--params", json.dumps({...})])`
- `run(["im", "messages", "--data", json.dumps({...})])`

### 6.2 SKILL.md

Frontmatter:
```yaml
---
name: feishu-cli-gateway
description: >
  Complete Feishu/Lark API gateway via the official lark-cli.
  Use for drive, docs, sheets, calendar, IM, contact, approval,
  tasks, and any other Feishu operations.
version: 1.0.0
author: Semantier
tags:
  - feishu
  - lark
  - productivity
  - api
metadata:
  hermes:
    tags: [feishu, lark, productivity, api]
    category: productivity
---
```

Body sections:
- **Purpose** — complete API coverage via official CLI
- **Prerequisites** — `npm install @larksuite/cli` (handled by Makefile/Docker)
- **Usage** — load bridge with `skill_view(...)`, use `run(args)` helper
- **Credential contract** — auto-loaded from `agent/.env`; never ask users for secrets
- **Output format** — always use `--format json`; parse the envelope
- **Sandbox boundary** — the bridge runs each CLI invocation in an isolated temp directory; do not assume files persist across calls
- **Important note** — this skill replaces the legacy meeting coordinator; all Feishu tasks flow through here

### 6.3 Runtime Policy Update

In `agent/src/runtime_prompt_policy.py`, replace the existing Feishu rules block:

**Current (lines 51–55):**
```python
"For Feishu/Lark meeting scheduling or contact lookup tasks, call skill_view(name=\"feishu-bot-meeting-coordinator\") first and follow the backend Feishu bot/API flow.",
"Do not use lark-cli for Feishu/Lark meeting/contact tasks unless the user explicitly asks for a CLI workflow.",
"Do not use delegate_task for Feishu/Lark meeting scheduling or contact lookup tasks.",
"Handle Feishu/Lark meeting/contact tasks in the main agent with the backend Feishu bot/API path, and if that backend capability is unavailable, report that instead of attempting terminal-only work, ad hoc scripts, or raw HTTP calls.",
```

**New:**
```python
"For any Feishu/Lark task (meetings, contacts, drive, docs, sheets, calendar, IM, approval, tasks), call skill_view(name=\"feishu-cli-gateway\") first and use its bridge script.",
"Do not use delegate_task for Feishu/Lark tasks.",
"Do not invent raw HTTP calls or ad hoc scripts for Feishu APIs; use the feishu-cli-gateway bridge.",
"Do not ask users for Feishu app secrets or tokens; credentials are loaded automatically from agent/.env.",
```

### 6.4 Local Setup (`agent/Makefile`)

New file:
```makefile
.PHONY: setup setup-feishu-cli

setup: setup-feishu-cli

setup-feishu-cli:
	@echo "Installing @larksuite/cli..."
	@npm install @larksuite/cli
	@echo "Verifying installation..."
	@npx lark-cli --version
```

Developers run:
```bash
cd agent
make setup-feishu-cli
```

### 6.5 Local Dependency Tracking (`agent/package.json`)

New file:
```json
{
  "name": "semantier-agent",
  "version": "1.0.0",
  "private": true,
  "dependencies": {
    "@larksuite/cli": "^1.0.19"
  }
}
```

This ensures the dependency is version-pinned and reproducible.

### 6.6 Dockerfile Update

**File:** `/home/chris/repo/semantier/Dockerfile`

Add the following after the `FROM python:3.11-slim AS runtime` line and before the `WORKDIR /app` line:

```dockerfile
# ============================================================================
# Stage 2: Python runtime
# ============================================================================
FROM python:3.11-slim AS runtime

# Install Node.js 20.x (required for @larksuite/cli)
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates curl \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/* \
    && npm install -g @larksuite/cli \
    && lark-cli --version
```

**Rationale:**
- The `python:3.11-slim` base does not include Node.js.
- `@larksuite/cli` requires Node >=16 and npm for its `postinstall` download script.
- Global install (`-g`) places `lark-cli` in `/usr/bin/lark-cli`, making it available in `$PATH` without path discovery logic.
- `lark-cli --version` acts as a smoke test during the Docker build.
- The bridge script will set `LARKSUITE_CLI_CONFIG_DIR` to a temp dir per invocation, so no persistent CLI state accumulates in the container filesystem.

### 6.7 README Update

Add to `agent/README.md` after the pip install section:

```markdown
## Feishu CLI Setup

The agent depends on `@larksuite/cli` for Feishu API operations:

```bash
cd agent
make setup-feishu-cli
```

Credentials are read automatically from `agent/.env` (`FEISHU_APP_ID`, `FEISHU_APP_SECRET`).
The bridge runs each CLI invocation in an isolated temp sandbox to prevent cross-workspace leakage.
```

---

## 7. Channel Support (webUI vs Feishu Gateway)

No skill-level changes are required. The bridge returns Python `dict` objects (parsed from `lark-cli --format json`). The agent's existing pipeline handles channel-specific rendering:

- **webUI** — `WebVisualizationAdapter` renders markdown tables, JSON fences, and plain text.
- **Feishu gateway** — `FeishuVisualizationAdapter` converts structured output to Feishu Card 2.0 JSON when appropriate.

If richer Card formatting is needed later (e.g., contact search results as a Card table), that enhancement belongs in `FeishuVisualizationAdapter`, not in this skill.

The sandbox injection pattern is channel-agnostic: the temp config directory and credential injection happen identically regardless of whether the request originated from webUI or Feishu gateway.

---

## 8. Rollback Plan

1. **Before deletion:** ensure `feishu-bot-meeting-coordinator/` is committed to git.
2. **Deploy new skill first**, verify in staging.
3. **Delete old skill** only after successful verification.
4. If rollback is needed:
   ```bash
   git revert <integration-commit>
   ```
   This restores the old skill directory and runtime policy in one step.

---

## 9. Testing Checklist

### 9.1 Local Dev
- [ ] `cd agent && make setup-feishu-cli` succeeds
- [ ] `npx lark-cli --version` prints version
- [ ] Bridge script loads `agent/.env` without errors
- [ ] `run(["contact", "user", "--query", "test", "--format", "json"])` returns valid dict
- [ ] `run(["calendar", "calendars", "--format", "json"])` returns valid dict
- [ ] Missing `FEISHU_APP_ID` raises clear error
- [ ] Credential mapping produces correct `LARKSUITE_CLI_*` env vars
- [ ] Sandbox isolation: `LARKSUITE_CLI_CONFIG_DIR` is a temp dir that is cleaned up after execution
- [ ] No files written to `~/.lark-cli` or user workspace during bridge execution
- [ ] Binary download commands default output to sandbox temp dir, not workspace

### 9.2 Docker
- [ ] `docker build` completes without error
- [ ] `lark-cli --version` works inside container
- [ ] Bridge resolves binary via `shutil.which("lark-cli")`
- [ ] No persistent CLI config accumulates in container filesystem across restarts

### 9.3 Integration
- [ ] webUI: contact search results render as readable markdown
- [ ] Feishu gateway: contact search results render without truncation
- [ ] Runtime policy no longer references `feishu-bot-meeting-coordinator`
- [ ] Old skill directory is removed from repo
- [ ] Cross-workspace isolation verified: simultaneous requests from different workspaces do not share CLI config or tokens

---

## 10. Risks & Mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| `@larksuite/cli` npm `postinstall` fails (network/GitHub rate limit) | Docker build fails | The install runs at Docker build time; retry CI or use mirror. Binary can be pre-copied as fallback. |
| Node 20 not available in future base image | Docker build fails | Use `apt-get install nodejs npm` (Debian stock) as fallback; package only requires `>=16`. |
| `lark-cli` JSON envelope format changes | Bridge parsing breaks | Pin version in `package.json`; monitor changelogs. |
| Loss of custom meeting negotiation logic | UX regression for multi-round scheduling | Document that complex negotiation may need re-implementation. The CLI provides raw API access; high-level workflows can be rebuilt on top if needed. |
| Binary not found at runtime | Skill fails | Bridge checks 3 resolution paths; Dockerfile global install ensures PATH availability. |
| Sandbox leak: CLI writes outside temp dir | Cross-workspace contamination | Force `LARKSUITE_CLI_CONFIG_DIR` + `LARKSUITE_CLI_LOG_DIR` to temp; validate with filesystem audit tests. |
| Large binary downloads fill temp dir | Disk pressure | Bridge checks file size before download; use `tempfile.TemporaryDirectory` with explicit cleanup. |

---

## 11. Summary of Changes

| Path | Action | Owner Review |
|------|--------|--------------|
| `agent/src/skills/app-infra/productivity/feishu-cli-gateway/SKILL.md` | **Create** | Content / UX |
| `agent/src/skills/app-infra/productivity/feishu-cli-gateway/scripts/feishu_cli_bridge.py` | **Create** | Backend |
| `agent/Makefile` | **Create** | DevOps |
| `agent/package.json` | **Create** | Backend |
| `agent/src/runtime_prompt_policy.py` | **Modify** (5 lines) | Backend |
| `agent/README.md` | **Modify** (add setup section) | Docs |
| `/home/chris/repo/semantier/Dockerfile` | **Modify** (add Node.js + npm install) | DevOps |
| `agent/src/skills/app-infra/productivity/feishu-bot-meeting-coordinator/` | **Delete** | Cleanup |

**Estimated effort:** 1 developer, 1 day (including testing).

**Architecture alignment:** This plan follows the semantier sandbox injection pattern documented in *Hermes Agent 架构与 semantier应用.md* (Sections 6.1, 10, and 11): control plane in `/agent`, execution plane in the bridge, and strict workspace isolation via per-invocation temp directories.
