# Feishu Integration Plan (WebUI + Gateway + larksuite/cli)

## 1. Goal

Integrate larksuite/cli capabilities into semantier so users can:

- authenticate and manage Feishu app/user auth from WebUI,
- route Feishu chat traffic through our existing gateway path,
- safely execute Feishu CLI flows in workspace-isolated runtime,
- keep one canonical session history across WebUI and gateway channels.

This plan is based on:

- upstream larksuite/cli command behavior and source layout,
- semantier current backend/auth/gateway/session architecture,
- existing Feishu login + gateway sync regression tests.

## 2. What We Learned From larksuite/cli Source

### 2.1 Core command model

larksuite/cli is a Cobra-based CLI with strong auth/config workflows:

- `config init`, `config bind`, `config show`, `config remove`
- `auth login`, `auth status`, `auth check`, `auth scopes`, `auth list`, `auth logout`

Key auth flow characteristics:

- Device Flow first-class (`auth login`), including `--no-wait` and `--device-code` resume.
- JSON output mode for machine orchestration (`--json`).
- Explicit scope/domain model (`--scope`, `--domain`, `--recommend`).
- Strict-mode and identity constraints (user vs bot).
- Workspace detection via env (`HERMES_HOME`, OPENCLAW env, etc.).

### 2.2 Why this matters for semantier

For WebUI orchestration, `auth login --no-wait` + `--device-code` is the best primitive:

- start authorization without blocking request lifecycle,
- show verification URL in WebUI,
- poll/resume from backend job worker,
- persist final token/status deterministically.

For config onboarding, `config init --new` and/or `config bind --source hermes` can be delegated from backend wrappers as controlled operations.

## 3. Current Semantier Surfaces We Should Reuse

### 3.1 Existing backend auth and Feishu routing

We already have:

- Feishu OAuth endpoints in `agent/api_server.py` (`/auth/feishu/login`, callback).
- Feishu webhook handling (`/feishu/webhook`) and `_feishu_route_message(...)`.
- Per-user workspace resolution + isolation when OAuth is enabled.
- Messaging config API (`/messaging/platforms`, `/messaging/{platform}`).

### 3.2 Existing gateway/session consistency model

We already maintain bidirectional continuity:

- gateway -> SessionStore sync (`_sync_gateway_session_messages_to_store(...)`),
- SessionStore -> gateway projection into workspace `.hermes/state.db`.

This is the right architecture; integration should plug into it, not bypass it.

### 3.3 Existing frontend entry points

WebUI already supports Feishu sign-in links and auth state fetch:

- `frontend/src/lib/api.ts`
- `frontend/src/pages/Home.tsx`
- `frontend/src/components/layout/Layout.tsx`

## 4. Recommended Integration Strategy

## 4.1 Decision: Wrapper-First, Not Embedded SDK

Best path: treat larksuite/cli as an external capability behind deterministic backend wrappers.

Do not:

- shell out directly from prompts/tools ad hoc,
- push CLI orchestration into frontend,
- duplicate larksuite/cli auth state machine in Python.

Do:

- build a backend Feishu CLI adapter/service that owns process invocation, env, parsing, retries, and state persistence.

Rationale:

- lowest maintenance against upstream CLI evolution,
- easiest to keep deterministic and testable,
- aligns with repo policy: file/dir ops in deterministic code paths.

## 4.2 Integration topology

1. WebUI calls backend Feishu integration endpoints.
2. Backend Feishu adapter runs larksuite/cli with workspace-scoped env.
3. Backend stores command state + auth progress in Auth store (plus optional runtime cache).
4. Gateway configuration is updated via existing messaging config + `config.yaml` sync path.
5. Feishu chat messages still flow through existing `/feishu/webhook` -> `_feishu_route_message(...)`.

## 4.3 Workspace and env contract

For every CLI invocation:

- enforce workspace context before execution,
- set deterministic env (including `HERMES_HOME`, config directory, non-global overrides),
- prohibit process-wide mutable auth/env side effects crossing workspaces.

## 5. API Additions (Backend)

Add a new Feishu integration API namespace in `agent/api_server.py` (or a new router module).

### 5.1 Proposed endpoints

- `POST /integrations/feishu/cli/config/init`
- `POST /integrations/feishu/cli/config/bind`
- `POST /integrations/feishu/cli/auth/login/start`
- `POST /integrations/feishu/cli/auth/login/poll`
- `GET /integrations/feishu/cli/auth/status`
- `POST /integrations/feishu/cli/auth/check`
- `POST /integrations/feishu/cli/auth/logout`

### 5.2 Endpoint behavior

`login/start`:

- execute `lark-cli auth login --json --no-wait ...`,
- return verification URL + device code,
- persist operation record keyed by workspace + user.

`login/poll`:

- execute `lark-cli auth login --json --device-code <code>`,
- return completion status and granted/missing scopes,
- update integration state and telemetry.

`auth/status`:

- execute `lark-cli auth status` (prefer JSON mode if available),
- normalize to stable API schema for frontend.

## 5.3 First Implementation Slice (P0): Contact Search + Bot Calendar Invite

This is the first production use case to implement.

User intent:

- search Feishu contacts from the bot context,
- choose one or more recipients,
- create a meeting event on the bot calendar,
- send invitation to selected contacts.

### 5.3.1 P0 endpoints

- `GET /integrations/feishu/contacts/search?q=<text>&limit=<n>`
- `POST /integrations/feishu/calendar/meetings`

`contacts/search` response shape:

- `items[]` with stable fields:
  - `display_name`
  - `open_id`
  - `union_id` (optional)
  - `email` (optional)
  - `mobile` (optional, masked)
  - `source` (`gateway_directory` | `feishu_api`)
  - `score` (name match confidence)

`calendar/meetings` request shape:

- `title` (required)
- `start_time` (ISO8601, required)
- `end_time` (ISO8601, required)
- `timezone` (required)
- `attendees` (required; supports `open_id` or email forms)
- `description` (optional)
- `location` (optional)
- `idempotency_key` (required)

`calendar/meetings` response shape:

- `event_id`
- `calendar_id`
- `join_url` (if returned by Feishu)
- `attendee_results[]` (resolved recipient status)
- `warnings[]`

### 5.3.2 Execution pipeline

1. Validate workspace auth context and resolve workspace-local runtime.
2. Run recipient resolution:
   - query gateway channel directory cache first (fast local hit),
   - query Feishu contact API for authoritative lookup,
   - merge and rank results, dedupe by `open_id`.
3. Validate minimum required scopes with `lark-cli auth check` (or equivalent service wrapper).
4. Create calendar event on bot calendar through deterministic adapter call.
5. Add/invite resolved attendees.
6. Persist operation audit record (workspace/user/request/result IDs).
7. Return normalized response to WebUI.

### 5.3.3 Identity mode for this use case

P0 should run in bot identity mode by default:

- organizer is the bot calendar/account,
- invitees are selected contacts,
- no user impersonation required.

If bot permissions are insufficient, return explicit actionable error and required scope hints.

### 5.3.4 Recipient resolution rules

- If caller provides `open_id`, use it directly after existence validation.
- If caller provides free text, perform fuzzy search and return top candidates.
- If multiple high-confidence matches exist, require explicit confirmation in UI before create.
- Never auto-invite ambiguous recipients.

### 5.3.5 Failure handling

- Partial attendee failure must not silently pass.
- Return per-attendee status:
  - `invited`
  - `not_found`
  - `permission_denied`
  - `invalid_contact`
- Meeting creation must be idempotent by `idempotency_key` per workspace.

### 5.3.6 Security controls

- Mask PII in logs (mobile/email).
- Log only hashed contact identifiers in structured telemetry where possible.
- Keep raw Feishu payloads out of frontend responses unless explicitly required.

### 5.3.7 P0 tests

Add targeted tests for this slice:

- contact search by exact display name,
- contact search by partial/fuzzy keyword,
- create meeting with one resolved contact,
- create meeting with multiple contacts,
- ambiguous contact requires user disambiguation,
- attendee partial failure surfaced correctly,
- idempotency key replay returns same meeting result,
- cross-workspace isolation for contacts and meeting operations.

## 6. WebUI Plan

### 6.1 UX flow

Add an Integration panel (or Messaging settings extension) for Feishu CLI:

- Connect app credentials (init/bind),
- Start user authorization,
- Show verification URL + copy action,
- Live status polling with clear states:
  - idle
  - waiting_user_authorization
  - authorized
  - missing_scopes
  - failed

### 6.2 UX guardrails

- Make identity mode explicit (bot-only vs user-default) where relevant.
- Show scope deltas (requested/granted/missing) after login completion.
- Never expose app secret or raw tokens in UI payloads/logs.

## 7. Gateway Integration Plan

### 7.1 Keep current runtime path

Do not alter primary gateway routing semantics. Continue using:

- `/feishu/webhook`
- `_feishu_route_message(...)`
- session mapping via workspace-aware keys

### 7.2 Bridge CLI auth state into gateway config lifecycle

After successful CLI config/auth operations:

- validate and persist platform config in auth store,
- apply to workspace `.hermes/config.yaml` through existing helper path,
- force-restart workspace gateway when required.

This keeps one control plane for config + one execution plane for gateway transport.

## 8. Security and Compliance

- Secrets must remain in backend-managed stores and workspace-local secure files only.
- Redact process arguments/log lines that may contain sensitive data.
- Keep per-workspace command execution and state directories isolated.
- Enforce allowlisted command templates; no arbitrary command passthrough.

## 9. Testing Plan

## 9.1 Unit tests

Add tests for Feishu CLI adapter:

- command construction,
- env injection,
- JSON parsing and error normalization,
- state transitions for start/poll flows.

## 9.2 Regression tests

Extend existing regressions in `agent/tests/regression/`:

- login start/poll happy path,
- missing-scope path,
- stale/invalid device code,
- cross-workspace isolation (cannot poll another workspace device code),
- gateway config apply + restart behavior after success.

## 9.3 Non-regression

Ensure existing suites still pass:

- `test_feishu_login_workspace.py`
- `test_feishu_streaming_cards.py`
- messaging gateway config API tests.

## 10. Rollout Phases

Phase 1: backend adapter + API

- implement deterministic Feishu CLI adapter module,
- expose minimal login start/poll/status APIs,
- implement P0 endpoints: contact search + bot calendar meeting invite,
- add telemetry and regression tests.

Phase 2: WebUI integration

- integrate new API flows into settings/auth surfaces,
- add user-visible status handling and errors.

Phase 3: gateway coupling hardening

- verify config apply/restart contract under concurrency,
- add recovery paths for partial failures.

Phase 4: operational polish

- metrics dashboards (success rate, time-to-authorize, scope mismatch rate),
- docs/runbooks.

## 11. Implementation Notes

- Prefer introducing `agent/src/integrations/feishu_cli_service.py` and keeping API handlers thin.
- Keep invocation contract stable so frontend remains decoupled from CLI output changes.
- Avoid touching `hermes-agent/` internals unless strictly required.

## 12. Open Questions For Review

1. Should we support both `config init --new` and `config bind --source hermes` in v1, or only `bind` for existing app credentials?
2. Do we expose advanced scope selection in WebUI v1, or start with a safe recommended set and add advanced mode later?
3. Should gateway auto-restart happen immediately after successful login/config, or only after explicit user confirmation in UI?
4. Do we need org-level policy controls (allowed scopes/domains) in v1, or defer to v2?
