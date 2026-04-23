## Plan: Canonical Transcript Unification

Converge on a single canonical transcript authority owned by `agent` while keeping gateway runtimes stateless with respect to canonical history. Implement this in phases: first stabilize today’s bidirectional projection with strong idempotency and observability, then move gateway restore/read paths behind `agent` session APIs, and finally deprecate direct `SessionDB()` transcript dependency in embedded `hermes-agent` flows.

## Scope Split

### Must-Have Now (execution-critical)

- Define canonical transcript ownership contract in `agent` (session authority, message authority, required metadata, direction of projection).
- Lock regression invariants for cross-entry continuation: WebUI <-> Weixin, WebUI <-> Feishu, tombstones, and restart idempotency.
- Harden projection paths with explicit origin markers and idempotency keys to prevent loops/duplicate rows.
- Add projection observability (lag, skip reason, projection failure counters) and rollout gates.
- Introduce `agent` read-through adapter boundary for gateway history restore with guarded fallback to legacy `.hermes/state.db`.
- Run shadow-read comparison and block cutover until mismatch/failure SLO is met.

### Later Cleanup (post-cutover)

- Move gateway transcript writes fully through adapter-only contract.
- Deprecate and remove embedded direct `SessionDB()` transcript reads.
- Remove migration feature flags and compat code after one stable release window.
- Keep only operational/delivery state as gateway-local; retain transcript authority in `agent`.
- Finalize runbook and recovery scripts (cursor reset, replay, rollback).

## Milestones

### M1 - Contract and Test Guardrails

- [ ] Publish transcript ownership contract and metadata schema in code/docs.
- [ ] Add regression matrix for cross-entry continuation and tombstone reuse.
- [ ] Add bidirectional idempotency tests under restart and replay.
- Exit criteria: all new regressions pass in CI; no unresolved contract ambiguity.

### M2 - Projection Hardening and Observability

- [ ] Add projection origin markers and source IDs to all mirrored rows/events.
- [ ] Enforce duplicate prevention and loop guard at write boundaries.
- [ ] Add counters/logs for projection lag, skipped duplicates, and projection errors.
- Exit criteria: replay/retry does not duplicate transcript rows; metrics visible in logs/dashboard.

### M3 - Read Boundary and Shadow Mode

- [ ] Add `agent` transcript adapter for gateway restore reads.
- [ ] Route wrapper and embedded read paths through adapter with fallback flag (`GATEWAY_TRANSCRIPT_SOURCE=legacy|agent`).
- [ ] Run shadow-read and collect mismatches without changing user-visible behavior.
- Exit criteria: mismatch/error rate below agreed SLO for one release cycle.

### M4 - Cutover and Cleanup

- [ ] Flip default to `agent` transcript source with rollback flag retained.
- [ ] Deprecate direct embedded `SessionDB()` transcript reads and remove dead paths.
- [ ] Finalize docs/runbook and remove stale migration flags.
- Exit criteria: cutover stable, no rollback triggered, cleanup merged.

## Delivery Tracking

| Milestone | Owner | ETA | Risk | Dependencies |
|---|---|---|---|---|
| M1 - Contract and Test Guardrails | Backend (agent) | 1 week | Medium | None |
| M2 - Projection Hardening and Observability | Backend (agent) + Platform | 1 week | Medium | M1 |
| M3 - Read Boundary and Shadow Mode | Backend (agent) + Integration | 1-2 weeks | High | M1, M2 |
| M4 - Cutover and Cleanup | Backend (agent) + Integration + QA | 1 week | High | M3 |

## Team Assignment Template

Use this table to replace placeholders with actual names before kickoff.

| Role | Placeholder Owner | Responsibilities |
|---|---|---|
| Tech Lead | `TBD_TECH_LEAD` | Owns technical decisions, migration sign-off, rollback authority |
| Backend Lead (`agent`) | `TBD_BACKEND_AGENT` | Owns transcript contract, adapter boundary, projection correctness |
| Integration Lead (gateway/wrapper) | `TBD_INTEGRATION` | Owns wrapper routing, embedded call-site migration, flag rollout |
| QA Lead | `TBD_QA` | Owns regression matrix, cutover validation, rollback drill execution |
| SRE/Platform | `TBD_SRE` | Owns observability dashboards, alerting, and production SLO tracking |

## SLO Targets (Cutover Gates)

These thresholds are proposed defaults and should be finalized by Tech Lead + SRE.

| Metric | Target | Window | Notes |
|---|---|---|---|
| Shadow-read mismatch rate | <= 0.1% of compared sessions | rolling 24h, sustained 7 days | Hard blocker for default flip |
| Projection write failure rate | <= 0.05% of projection attempts | rolling 24h, sustained 7 days | Includes retries exhausted |
| Duplicate suppression correctness | >= 99.99% (no duplicate user-visible turns) | rolling 7 days | Validate via replay/restart scenarios |
| Projection lag P95 | <= 3s | rolling 24h | From source write to mirrored availability |
| Projection lag P99 | <= 10s | rolling 24h | Investigate any burst beyond threshold |
| Rollback readiness | 100% successful flag rollback drill | once per release train | Must pass before cutover |

## Go/No-Go Checklist (Cutover Template)

Mark each item with `YES/NO` during release review.

| Check | Status (YES/NO) | Evidence |
|---|---|---|
| M1 regressions all green in CI | NO | local regressions are green, but no CI evidence linked yet |
| M2 observability dashboards and alerts active | NO | dashboard URL |
| Shadow mode ran >= 7 days with mismatch <= 0.1% | NO | report link |
| Projection failure rate <= 0.05% for last 7 days | NO | report link |
| Replay/restart idempotency tests passed in latest build | YES | local run: `agent/tests/regression/test_messaging_gateway_config_api.py` passed (`13 passed`) |
| Wrapper routing verified (no direct bypass) | YES | local run: `agent/tests/regression/test_hermes_dashboard_wrapper.py` passed (`4 passed in 0.35s`); CI link pending |
| Rollback flag tested in staging and prod-like env | NO | drill log link |
| On-call + incident runbook acknowledged | NO | sign-off record |
| Tech Lead sign-off | NO | name/date |
| QA Lead sign-off | NO | name/date |
| SRE sign-off | NO | name/date |

### Current Prefill Snapshot (2026-04-23)

| Signal | Current Status | Source | Gap to Close |
|---|---|---|---|
| Gateway/session-focused regressions | PASS (local) | `./.venv/bin/python -m pytest -q tests/regression/test_messaging_gateway_config_api.py` -> `13 passed` | Attach CI URL and commit SHA |
| Hermes session/system prompt tests | PASS (local) | `./.venv/bin/python -m pytest -q tests/run_agent -k "system_prompt or session"` exited `0` | Attach CI URL and commit SHA |
| Wrapper routing proof | PASS (local) | `./.venv/bin/python -m pytest -q tests/regression/test_hermes_dashboard_wrapper.py` -> `4 passed in 0.35s` | Attach CI URL and commit SHA |
| Shadow read mismatch SLO | NOT VERIFIED | no shadow telemetry yet | Run shadow mode >= 7 days and publish report |
| Projection failure SLO | NOT VERIFIED | no telemetry dashboard linked | Add dashboard + alert and record 7-day window |
| Rollback drill | NOT VERIFIED | no drill log | Execute and attach drill record |

### Missing Evidence Links (Fill Before Cutover)

- CI run URL for `agent/tests/regression/test_messaging_gateway_config_api.py`.
- CI run URL for `hermes-agent/tests/run_agent -k "system_prompt or session"`.
- CI run URL for `agent/tests/regression/test_hermes_dashboard_wrapper.py`.
- Shadow mode report URL covering a continuous 7-day window.
- Observability dashboard URL for projection lag/failure metrics.
- Rollback drill artifact (ticket, log, and operator sign-off).

Cutover decision rule:
- Go: all checks are `YES` and no unresolved Sev-1/Sev-2 issues.
- No-Go: any hard gate is `NO` or unresolved critical incident exists.

## Work Breakdown

1. Define and codify canonical data contract in `agent` for session/message ownership, required metadata (`channel`, `gateway_session_key`, `owner_user_id`, delivery cursors), and allowed projection directions.
2. Add architecture invariants as regression tests so cross-entry continuation is guaranteed (WebUI -> Weixin, Weixin -> WebUI, Feishu -> WebUI, deletion tombstones).
3. Add explicit projection markers (`origin`, projection source IDs, idempotency keys) and loop guards so repeated sync cannot duplicate rows.
4. Add metrics/logging for projection lag, duplicate skips, and failed projection writes.
5. Create an `agent` transcript adapter that serves gateway restore history from canonical `SessionStore` with compatibility fallback to workspace `.hermes/state.db` during migration.
6. Update wrapper startup and runtime wiring so embedded dashboard/gateway read paths route through `agent` boundary first, with fallback behind feature flag (`GATEWAY_TRANSCRIPT_SOURCE=legacy|agent`).
7. Run shadow-read mode (compare agent vs legacy transcript results per session) and emit mismatch diagnostics without changing user behavior.
8. Move gateway transcript writes to `agent`-owned adapter interface and make direct Hermes `SessionDB` transcript writes optional/compat-only.
9. Flip default to `agent` transcript source after mismatch/error SLOs are met; keep temporary rollback flag.
10. Deprecate and prune direct `SessionDB()` transcript read call sites in embedded contexts, leaving only runtime-local caches/delivery state.
11. Remove migration flags and dead projection code paths after one release window; keep data repair scripts for cursor/tombstone recovery.
12. Finalize docs and runbook with failure playbooks (projection backlog, cursor reset, replay, rollback).

**Relevant files**
- `/home/chris/repo/semantier/agent/api_server.py` — existing projection and backfill helpers (`_sync_gateway_session_messages_to_store`, reverse projection hook wiring) to evolve into explicit adapter boundaries.
- `/home/chris/repo/semantier/agent/src/session/service.py` — central message persistence path; maintain single hook point for projection/adapter writes.
- `/home/chris/repo/semantier/agent/src/session/store.py` — canonical file-backed store contract and metadata handling.
- `/home/chris/repo/semantier/agent/src/session/store_sqlite.py` — canonical sqlite-backed path and schema alignment for migration.
- `/home/chris/repo/semantier/agent/hermes_dashboard_wrapper.py` — enforce wrapper-first routing and per-request workspace scoping.
- `/home/chris/repo/semantier/hermes-agent/hermes_cli/web_server.py` — direct `SessionDB()` read call sites to isolate behind adapter/proxy boundary.
- `/home/chris/repo/semantier/hermes-agent/gateway/session.py` — gateway restore/history read path currently coupled to `SessionDB`.
- `/home/chris/repo/semantier/agent/tests/regression/test_messaging_gateway_config_api.py` — extend cross-entry sync/idempotency/deletion tests.
- `/home/chris/repo/semantier/agent/tests/regression/test_hermes_dashboard_wrapper.py` — validate wrapper routing and workspace isolation.
- `/home/chris/repo/semantier/Hermes Agent 架构与 semantier应用.md` — keep architecture contract and rollout status in sync with implementation.

**Verification**
1. Regression matrix tests pass for continuation across all entry combinations: WebUI->Weixin, Weixin->WebUI, WebUI->Feishu, Feishu->WebUI.
2. Idempotency tests pass for both projection directions under repeated sync and restarts.
3. Tombstone semantics tests pass for `session_key` reuse with different `session_id`.
4. Wrapper routing tests pass and do not bypass `agent` boundary.
5. Shadow mode mismatch/error rates remain below agreed SLO for one release cycle before default flip.
6. Rollback drill succeeds by switching `GATEWAY_TRANSCRIPT_SOURCE=legacy` with no data loss.

### Validation Commands

```bash
cd /home/chris/repo/semantier/agent && ./.venv/bin/python -m pytest -q tests/regression/test_messaging_gateway_config_api.py
cd /home/chris/repo/semantier/agent && ./.venv/bin/python -m pytest -q tests/regression/test_hermes_dashboard_wrapper.py
cd /home/chris/repo/semantier/hermes-agent && ./.venv/bin/python -m pytest -q tests/run_agent -k "session or gateway"
```

**Decisions**
- Included scope: transcript authority, projection correctness, wrapper routing, and direct read deprecation in embedded paths.
- Excluded scope: upstream Hermes standalone behavior outside semantier embedding; no upstream PR required.
- Migration strategy: feature-flagged, rollback-capable, with shadow comparison before default cutover.

**Further Considerations**
1. Canonical persistence backend choice in `agent`: keep file `SessionStore` now (lower migration risk) or move to sqlite canonical earlier (simpler query/consistency). Recommendation: keep file backend during boundary migration, then evaluate sqlite cutover separately.
2. Gateway replay source during cutover: read-through API call vs local adapter library call. Recommendation: local adapter in `agent` process first for latency/reliability, API boundary only if process separation is later required.
3. Data retention policy: keep full gateway/runtime rows or only canonical transcript + delivery cursors. Recommendation: retain canonical transcript + minimal runtime operational logs, expire duplicate projection artifacts after migration window.

---

## Architectural Review — Kimi (2026-04-23)

### Overall Assessment
The phased approach (contract → harden → shadow → cutover → cleanup) is sound and matches the existing projection scaffolding already present in `api_server.py`. The plan correctly identifies the core risk: **bidirectional projection without robust idempotency**. However, after reviewing the current codebase, there are several gaps, naming collisions, and policy tensions that need resolution before kickoff.

### Critical Findings

#### 1. Nomenclature Collision: `SessionStore` is Ambiguous
There are **two** `SessionStore` classes in play:
- `agent/src/session/store.py` — canonical backend store (file-backed, and optionally `SQLiteSessionStore`).
- `hermes-agent/gateway/session.py` — gateway runtime index (manages `sessions.json` + `SessionDB` transcripts).

**Impact:** The plan uses "SessionStore" without qualification. During implementation this will cause confusion in code reviews, logs, and incident response.
**Recommendation:** Rename the gateway-side class to `GatewaySessionIndex` (it is already closer to an index than a store) or adopt explicit prefixes (`BackendSessionStore` vs `GatewaySessionIndex`) in all docs and code.

#### 2. Projection Infrastructure Already Exists — M2 is "Harden," Not "Add"
- `SessionService.message_projection_hook` already exists and is wired in `_get_session_service()` to call `_append_message_to_gateway_state_db()`.
- `_sync_gateway_session_messages_to_store()` already performs the reverse read-through from `state.db`.

**Impact:** M2 deliverables are framed as greenfield additions; they are actually hardening/refactoring of existing ad-hoc sync logic.
**Recommendation:** Update M2 tasks to "harden existing projection paths" and inventory the current idempotency gaps:
  - `agent→gateway` (`_append_message_to_gateway_state_db`) performs **blind INSERT** with no idempotency key.
  - `gateway→agent` uses `gw-{message_id_num}` but `message.id` in `state.db` is an auto-increment integer that resets if the DB is rebuilt, making this prefix fragile.

#### 3. Adapter Boundary Shape is Undefined
The plan says "Create an `agent` transcript adapter" but does not define:
- **Interface:** Is it a Python callable (in-process), a FastAPI dependency, or an HTTP client?
- **Scope:** Per-workspace or global?
- **Failure mode:** Fallback to legacy is mentioned, but what happens when the adapter throws an exception vs. returns stale data?

**Current state:** `hermes_dashboard_wrapper.py` is an ASGI middleware that simply sets `HERMES_HOME` and forwards to `hermes_cli.web_server`. There is no interception point for transcript reads today.
**Recommendation:** Define the adapter as an in-process Python boundary first (e.g., `AgentTranscriptAdapter` class) with two implementations:
  - `CanonicalAdapter` → calls `SessionService` / `SessionStore`
  - `LegacyAdapter` → calls `SessionDB` directly
  The wrapper middleware can inject the chosen adapter into request scope so `hermes_cli.web_server` endpoints can consume it without hardcoding `SessionDB()`.

#### 4. Gateway Subprocess Read Path is a Harder Problem Than the Wrapper
The plan focuses heavily on the **wrapper/embedded dashboard** read path, but the gateway also runs as a **subprocess** (`_start_workspace_hermes_gateway`). In that mode, `hermes-agent/gateway/session.py::SessionStore.load_transcript()` reads from `SessionDB` or JSONL to build LLM conversation context.

**Impact:** If canonical authority moves to `agent`, the subprocess cannot reach `agent` memory. It would need either:
- An HTTP callback to agent (latency risk on every message receive)
- A shared SQLite file with WAL (reintroduces coupling)
- A local-agent proxy inside the gateway process (complex)
**Recommendation:** Clarify in M3 whether "gateway read path" includes the subprocess case or only the embedded dashboard. If subprocess is out of scope for this plan, state that explicitly and treat it as a separate architectural epoch.

#### 5. `AGENTS.md` Policy Tension
`AGENTS.md` states: *"Do not modify vendored or submodule directories like `hermes-agent/` unless the task explicitly requires it."*

**Impact:** Deprecating direct `SessionDB()` reads in embedded flows requires modifying `hermes-agent/hermes_cli/web_server.py` and `hermes-agent/gateway/session.py`. This is a direct violation of the repo's own agent policy.
**Recommendation:** Either
  - (a) Add an explicit policy exception to `AGENTS.md` for this migration, or
  - (b) Implement the adapter entirely in `agent/` by subclassing/monkey-patching at the wrapper boundary instead of touching upstream files. Option (b) is cleaner for long-term maintainability but may be more work.

#### 6. FTS5 Search Parity Gap
`hermes_state.SessionDB` provides FTS5 search (`search_sessions`). Neither `SessionStore` nor `SQLiteSessionStore` currently implements search.

**Impact:** If the dashboard/wrapper routes session search through the agent adapter, search will regress unless search is added to the agent backend.
**Recommendation:** Add "search parity" as a M3 deliverable or explicitly exclude search from adapter scope and keep search on a read-replica of `state.db`.

#### 7. Shadow-Read "Mismatch" Needs Normalized Definition
The SLO targets a <=0.1% mismatch rate, but the schemas differ:
- Agent canonical events: `role`, `content`, `timestamp` (ISO8601), `metadata` (rich), `event_id` (UUID).
- Gateway messages: `role`, `content`, `timestamp` (Unix float), `id` (autoinc).

**Impact:** Timestamp precision differences and metadata richness will generate false mismatches.
**Recommendation:** Define a canonical normalization function for shadow comparison (e.g., compare `(role, normalized_content, timestamp_within_1s)` only) and document it before M3 starts.

#### 8. SQLiteBackend is Already Implemented — Consider Activating It Sooner
`SQLiteSessionStore` in `agent/src/session/store_sqlite.py` is complete, tested, and uses WAL + foreign keys. The plan recommends keeping the file backend during migration.

**Concern:** The file-based `SessionStore` is **not process-safe** for concurrent writes. During the migration window, both agent and gateway may write to the same session tree (agent via canonical events, gateway via backfill/projection). This creates a race condition on `events.jsonl` append and `session.json` updates.
**Recommendation:** Re-evaluate the file-backend decision. SQLite with WAL is safer for concurrent cross-process access and already feature-gated. Activating `SESSION_STORE_BACKEND=sqlite` for the migration window reduces a class of data-corruption risks.

#### 9. Missing: Workspace-Scoped Adapter Lifecycle
`_get_session_service()` already maintains `_session_service_by_workspace`, which is correct. However, the plan does not mention how the adapter will be scoped (per-request, per-workspace singleton, or global).
**Recommendation:** Mandate per-workspace adapter instances to maintain data isolation, matching the existing `SessionService` lifecycle.

#### 10. Rollback Flag `GATEWAY_TRANSCRIPT_SOURCE` Needs Plumbing
The plan proposes `GATEWAY_TRANSCRIPT_SOURCE=legacy|agent`. Today, `hermes_dashboard_wrapper.py` has no routing table — it blindly forwards all requests. Implementing this flag requires either:
- Intercepting specific transcript endpoints (`/api/sessions/{id}/messages`, etc.) in the wrapper middleware and routing them based on the flag, or
- Injecting the flag into `hermes_cli.web_server` and branching there.

**Recommendation:** Prefer wrapper-level interception to minimize upstream changes. Document the exact endpoint list that will be shadowed/routed.

### Questions for the Tech Lead / Backend Lead

1. **Subprocess scope:** Does "gateway read path" in M3 include the gateway subprocess's `load_transcript()` calls, or only the embedded dashboard wrapper? If subprocess is included, what is the IPC mechanism?
2. **Upstream modification policy:** Are we approved to modify `hermes-agent/hermes_cli/web_server.py` and `hermes-agent/gateway/session.py`, or should the adapter be injected via wrapper-level monkey-patching?
3. **SQLite activation:** Can we flip `SESSION_STORE_BACKEND=sqlite` as part of M1/M2 to eliminate file-based concurrency risks during the migration?
4. **Search parity:** Is session search (FTS5) in scope for the adapter, or will search remain on a legacy read path indefinitely?
5. **Shadow comparison schema:** What constitutes a "mismatch"? Please define the normalized tuple before M3 begins.
6. **Idempotency key source:** For agent→gateway projection, what should the idempotency key be? `agent_event_id` (UUID from `SessionEvent`)? A hash of `(session_id, event_id)`?
7. **Tombstone definition:** The plan mentions "tombstone semantics tests." The current implementation uses `deleted_sessions.json` markers. Is the plan referring to these markers, or do we need a new tombstone concept in `SessionStore`?

### Minor Suggestions
- Add `channel` and `gateway_session_key` to the `SessionResponse` model in `api_server.py` so the frontend can display entry-point provenance without extra lookups.
- Consider adding `origin` and `projection_source_id` fields to `SessionEvent.metadata` schema now (M1) so M2 has a stable contract to enforce.
- The ETA of 1 week per milestone feels optimistic for M3 given the undefined adapter shape and subprocess question; consider buffering M3 to 2 weeks.

### Verdict
**Conditional Go.** The strategy is correct, but the plan needs the adapter interface defined, the subprocess scope clarified, and the upstream-modification policy exception granted before M1 kickoff. M2 and M3 should not start until these architectural decisions are documented in `Architecture-Design.md` and `AGENTS.md`.
