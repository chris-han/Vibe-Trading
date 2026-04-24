# Feishu Integration Plan (Direct Bot/API)

## 1. Decision

For the scheduling use case, we should not use `larksuite/cli`.

We already have the required bot credentials and Feishu gateway surfaces in the backend:

- `FEISHU_APP_ID`
- `FEISHU_APP_SECRET`
- `FEISHU_CONNECTION_MODE=websocket`
- existing Feishu message ingress and session routing in `agent/api_server.py`

The best implementation path is:

- use Feishu bot/app credentials directly,
- call Feishu Open Platform APIs from deterministic backend code,
- keep WebUI and Feishu chat on the same session/gateway architecture,
- avoid CLI process management, device flow, and token-wrapper complexity.

## 2. Why This Is Better Than Feishu CLI

For this use case, CLI adds no real value.

Using direct bot/API integration is better because it:

- removes interactive login and token lifecycle complexity,
- avoids subprocess orchestration and env-injection security risk,
- fits our existing FastAPI + gateway control plane,
- keeps retries, validation, logging, and idempotency in Python backend code,
- aligns with repo policy that deterministic operations belong in code, not prompt/runtime shell flows.

## 3. Current Repo Surfaces To Reuse

We already have:

- Feishu bot credentials configured in `agent/.env`.
- Feishu long-connection / webhook support in `agent/api_server.py`.
- Feishu inbound routing via `_feishu_route_message(...)`.
- workspace-aware session continuity through gateway/session sync.
- messaging config persistence and workspace gateway restart helpers.

This means the missing piece is not channel connectivity. The missing piece is outbound Feishu productivity capability: contact lookup and calendar event creation.

## 4. P0 Use Case

Implement this first:

- the bot can search users who have added the bot or are otherwise visible to the app,
- the bot can create a meeting event as the bot organizer,
- the bot can invite one or more resolved contacts,
- the result is visible and actionable from WebUI and later from chat flows.

## 5. Product Assumptions

This design assumes:

- every participating user adds the bot or is otherwise visible through app/org policy,
- the app has the required Feishu scopes enabled,
- the bot is allowed to invite those users to calendar events,
- organizer identity being the bot is acceptable.

Important limitation:

- this coordinates meetings as the bot, not as each end user.
- it should not be described as acting on behalf of the user's private calendar.

## 6. Architecture

### 6.1 Core rule

Treat meeting coordination as a direct backend integration service.

Do not:

- shell out to `lark-cli`,
- build a token-injected CLI wrapper,
- use interactive OAuth for P0,
- route business logic through prompt text.

Do:

- introduce a deterministic Feishu scheduling service in backend code,
- use app credentials to obtain tenant access token,
- call Feishu contact and calendar APIs directly,
- normalize responses into stable backend schemas.

### 6.2 Recommended module layout

- `agent/src/integrations/feishu_client.py`
- `agent/src/integrations/feishu_contacts_service.py`
- `agent/src/integrations/feishu_calendar_service.py`

`api_server.py` should stay thin and delegate to these services.

## 7. API Design

### 7.1 Endpoints

- `GET /integrations/feishu/contacts/search?q=<text>&limit=<n>`
- `POST /integrations/feishu/calendar/meetings`

### 7.2 Contact search response

Return normalized candidates:

- `display_name`
- `open_id`
- `union_id` (optional)
- `avatar_url` (optional)
- `email` (optional when policy allows)
- `department_names` (optional)
- `match_reason`
- `score`

### 7.3 Meeting create request

- `title`
- `start_time`
- `end_time`
- `timezone`
- `attendees`
- `description` (optional)
- `location` (optional)
- `idempotency_key`

Attendees can be submitted as:

- exact `open_id`
- exact email
- unresolved text candidates coming from a prior search selection

### 7.4 Meeting create response

- `event_id`
- `organizer_identity = bot`
- `calendar_id`
- `join_url` (if provided by Feishu)
- `attendee_results[]`
- `warnings[]`

## 8. Execution Flow

### 8.1 Contact search

1. Validate request and workspace context.
2. Acquire tenant access token using `FEISHU_APP_ID` + `FEISHU_APP_SECRET`.
3. Query Feishu-visible contact directory.
4. Rank and normalize results.
5. Return candidates for explicit user confirmation when ambiguous.

### 8.2 Meeting creation

1. Validate request and workspace context.
2. Resolve all attendees to stable Feishu identities.
3. Fail fast on ambiguity.
4. Acquire tenant access token.
5. Create calendar event as bot organizer.
6. Attach or invite attendees.
7. Persist operation audit metadata.
8. Return normalized result.

## 9. Identity Model

P0 is bot-only.

- organizer is the Feishu bot/app calendar identity,
- contacts are bot-visible users,
- invitations are sent by the bot/app,
- no user access token is needed.

If later we need true user-calendar ownership, that becomes a separate v2 user-identity design.

## 10. Contact Visibility Rules

The design should assume contact search is limited to users visible to the bot/app.

Expected behavior:

- if a user added the bot and org policy allows lookup, they are searchable,
- if multiple users match, return candidates and require confirmation,
- if no visible user matches, return `not_found` rather than guessing,
- never auto-invite an ambiguous target.

## 11. Error Handling

Return normalized errors such as:

- `not_found`
- `ambiguous_contact`
- `permission_denied`
- `scope_not_enabled`
- `bot_not_allowed`
- `rate_limited`
- `invalid_request`
- `upstream_api_error`

For attendee-level failures, return per-attendee status:

- `invited`
- `not_found`
- `permission_denied`
- `invalid_contact`

Meeting creation must be idempotent per workspace via `idempotency_key`.

## 12. Security

- do not expose raw Feishu tokens in logs or responses,
- keep tenant token acquisition inside backend service helpers,
- mask PII in logs where possible,
- keep all path/file/state operations inside deterministic backend code.

## 13. WebUI

Add a scheduling panel or action flow with:

- contact search box,
- candidate disambiguation picker,
- meeting title/time form,
- result panel showing invited and failed attendees,
- explicit note that organizer is the bot.

The UI should not mention CLI, login, or token injection for P0.

## 14. Testing Plan

### 14.1 Unit tests

Add tests for:

- tenant token acquisition helper,
- contact search normalization and scoring,
- attendee resolution,
- meeting create request builder,
- error mapping from Feishu responses.

### 14.2 Regression tests

Add regression coverage for:

- exact contact search,
- fuzzy contact search,
- ambiguous name returns multiple candidates,
- single-recipient meeting success,
- multi-recipient meeting success,
- partial attendee failure reporting,
- idempotent replay with same key,
- workspace isolation.

### 14.3 Existing suites to preserve

- Feishu login workspace regression tests
- Feishu streaming card tests
- messaging gateway config API tests

These are still relevant because chat ingress and session continuity remain part of the platform.

## 15. Rollout

Phase 1:

- implement direct Feishu backend client and service,
- implement contact search endpoint,
- implement bot-calendar meeting create endpoint,
- add regression tests.

Phase 2:

- integrate WebUI scheduling flow,
- add clear invite result rendering,
- add operator-facing error messages.

Phase 3:

- connect chat-triggered scheduling flows,
- add audit views and operational telemetry,
- harden retries and rate-limit handling.

## 16. Explicit Non-Goals For P0

- no `lark-cli` wrapper,
- no interactive Feishu CLI login,
- no user-token injection mode,
- no user-calendar ownership,
- no per-user delegated OAuth scheduling flow.

## 17. Open Questions

1. Which exact Feishu APIs and scopes should we standardize for bot-visible contact lookup in this tenant?
2. Does the bot organizer model satisfy the product expectation for all meeting invites?
3. Should failed attendees block the whole operation, or should we allow partial success by default?
