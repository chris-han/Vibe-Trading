# Add Login Plan

## Summary

This document defines the design for:

- Feishu login for the Vibe-Trading web app
- Feishu chat auto-provisioning
- per-user isolated workspaces
- Hermes agent runtime integration
- Postgres-backed SaaS identity and configuration
- future per-user memory architecture

Core decisions:

- Feishu is the identity entry point for both web login and Feishu chat auto-provisioning.
- The app owns canonical user identity, tenant membership, roles, and profile mapping.
- The SaaS isolation boundary is the app-level user workspace.
- Hermes profiles are a separate Hermes framework concept for running multiple isolated Hermes agents.
- Hermes profiles must not be used as the primary SaaS end-user isolation primitive.
- End-user isolation is enforced by app workspace boundaries plus app auth/authorization.
- Recommended runtime model: one isolated Hermes runtime instance per user workspace.
- This means one `HERMES_HOME` per workspace, but not one Hermes CLI profile per end user.
- Hermes built-in memory should therefore be isolated by workspace-local Hermes homes, without conflating that with Hermes CLI profiles.
- Postgres is the long-term control-plane store.
- Session/run metadata moves to Postgres only after login/profile rollout is stable and tested.
- Filesystem or object storage remains the data-plane store.
- Hermes supports only one external memory provider at a time.
- A federated custom memory provider is a v3 option only, but the architecture should be ready for it from day one.

## Terminology

Two different concepts must stay separate in both code and docs.

### 1. User Profile / Workspace

This is the Vibe-Trading SaaS concept.

- one workspace per authenticated app user
- the strict isolation boundary for files, sessions, runs, uploads, and artifacts
- app-owned
- stored under `<workspace_root>/agent/`

Examples:

- `workspaces/chris/agent/`
- `workspaces/new_user/agent/`

This is where user work happens.

### 2. Hermes Agent Profile

This is the Hermes framework concept.

- one fully isolated Hermes environment for running an independent Hermes agent
- used by Hermes CLI as `hermes -p <name>` or alias commands like `coder chat`
- framework-owned layout under `HERMES_HOME`
- contains Hermes config, memories, installed skills, plugins, logs, and state
- documented by Hermes as a way to run multiple independent agents on one machine
- not the same thing as an app end-user identity

Examples:

- `~/.hermes/profiles/coder/`
- `~/.hermes/profiles/research-bot/`

This is where Hermes stores one agent's own state.

### Required Rule

Do not use the word `profile` by itself in implementation specs.

Use one of these exact names instead:

- `user profile` or `user workspace`
- `Hermes agent profile`

If a database field is needed:

- app isolation field: `workspace_slug`
- Hermes runtime field: `hermes_profile_name`

There must be no assumption that a user workspace maps 1:1 to a Hermes profile.

There may, however, be a deliberate 1:1 mapping between:

- one user workspace
- one isolated Hermes runtime instance
- one workspace-local `HERMES_HOME`

That is a Vibe-Trading tenancy decision, not a Hermes profile decision.

## Current Repo State

The current implementation is mostly file-backed and single-profile oriented:

- User/runtime data is scoped through `TERMINAL_CWD` and `get_data_root()` in [agent/runtime_env.py](/home/chris/repo/Vibe-Trading/agent/runtime_env.py).
- Session/run APIs and persistence are file-backed in [agent/api_server.py](/home/chris/repo/Vibe-Trading/agent/api_server.py) and [agent/src/session/store.py](/home/chris/repo/Vibe-Trading/agent/src/session/store.py).
- Feishu already exists as a messaging integration in [agent/api_server.py](/home/chris/repo/Vibe-Trading/agent/api_server.py), but not yet as the web login identity layer.
- `POSTGRES_URL` already exists in [agent/.env](/home/chris/repo/Vibe-Trading/agent/.env), but active user/profile/session code is not using it yet.

## Verified Hermes Findings

### Hermes Agent Profiles

Hermes agent profiles are real isolated homes under `profiles/<name>`.

Each profile has its own:

- `config.yaml`
- `.env`
- `memories`
- `sessions`
- `skills`
- `logs`
- `plans`
- `workspace`
- `cron`
- `home`

Verified in:

- [hermes-agent/hermes_cli/profiles.py](/home/chris/repo/Vibe-Trading/hermes-agent/hermes_cli/profiles.py)
- [hermes-agent/hermes_constants.py](/home/chris/repo/Vibe-Trading/hermes-agent/hermes_constants.py)

Official docs:

- <https://hermes-agent.nousresearch.com/docs/reference/cli-commands?_highlight=memery#hermes-auth>

### Built-in Memory

Hermes built-in memory is:

- always file-backed
- always profile-scoped
- stored in `HERMES_HOME/memories/MEMORY.md` and `HERMES_HOME/memories/USER.md`
- loaded as a frozen snapshot at session start
- still active even when an external provider is enabled

Verified in:

- [hermes-agent/tools/memory_tool.py](/home/chris/repo/Vibe-Trading/hermes-agent/tools/memory_tool.py)
- [hermes-agent/run_agent.py](/home/chris/repo/Vibe-Trading/hermes-agent/run_agent.py)

Official docs:

- <https://hermes-agent.nousresearch.com/docs/user-guide/features/memory?_highlight=memory>

### External Memory Providers

Hermes external memory providers:

- implement the `MemoryProvider` ABC
- are orchestrated through `MemoryManager`
- allow only one external provider at a time
- run alongside the built-in memory layer
- receive runtime context such as `hermes_home`, `agent_identity`, `agent_workspace`, and optional `user_id`

Verified in:

- [hermes-agent/agent/memory_provider.py](/home/chris/repo/Vibe-Trading/hermes-agent/agent/memory_provider.py)
- [hermes-agent/agent/memory_manager.py](/home/chris/repo/Vibe-Trading/hermes-agent/agent/memory_manager.py)
- [hermes-agent/plugins/memory/__init__.py](/home/chris/repo/Vibe-Trading/hermes-agent/plugins/memory/__init__.py)
- [hermes-agent/run_agent.py](/home/chris/repo/Vibe-Trading/hermes-agent/run_agent.py)

Official docs:

- <https://hermes-agent.nousresearch.com/docs/user-guide/features/memory-providers?_highlight=memory&_highlight=viki#openviking>

## Architecture Decisions

### Identity And Tenancy

- Feishu identity is the upstream external identity.
- Postgres stores canonical app users, external identities, tenants, memberships, roles, and config.
- Hermes does not own the SaaS user model.
- Use display-name slugging for the app-level `workspace_slug`.
- Example: `New User` -> `new_user`.
- Resolve collisions with suffixes like `_2`, `_3`.
- Persist a mapping from Feishu identity to app user and `workspace_slug` in Postgres.
- Do not model Hermes CLI profiles as end-user records.

### Multi-Tenant Directory Hierarchy And Boundaries

```text
/home/chris/repo/Vibe-Trading/
├── agent/                                  # source code / shared app runtime code
├── workspaces/
│   ├── chris/
│   │   └── agent/                          # workspace runtime root, mirrors current layout
│   │       ├── .hermes/                    # workspace-local Hermes runtime home
│   │       │   ├── config.yaml
│   │       │   ├── .env
│   │       │   ├── memories/
│   │       │   │   ├── MEMORY.md
│   │       │   │   └── USER.md
│   │       │   ├── skills/
│   │       │   ├── plugins/
│   │       │   ├── logs/
│   │       │   ├── home/
│   │       │   └── profiles/               # optional Hermes CLI multi-agent profiles
│   │       │       ├── coder/
│   │       │       └── research-bot/
│   │       ├── sessions/                   # app-owned session data
│   │       ├── runs/                       # app-owned run data
│   │       ├── uploads/
│   │       └── swarm/
│   └── new_user/
│       └── agent/
│           └── ...
├── frontend/
├── hermes-agent/
└── ...
```

Boundary rules:

- `<workspace_root>/agent/` is the strict app-level tenant workspace boundary.
- `<workspace_root>/agent/.hermes/` is the recommended Hermes runtime home for that workspace.
- the source-tree `agent/` directory is code, not tenant data.
- `<workspace_root>/agent/.hermes/profiles/<name>/` is only for Hermes multi-agent profile use cases, not for SaaS end-user tenancy.
- The app must never treat a Hermes profile directory as the user workspace.
- Hermes-managed files and app-generated artifacts must not be mixed in the same root.

### Workspace Per App User

For each app user:

- create or reuse a user workspace root such as `workspaces/<workspace_slug>/`
- create or reuse a workspace runtime root at `workspaces/<workspace_slug>/agent/`
- create or reuse a workspace-local Hermes runtime home at `workspaces/<workspace_slug>/agent/.hermes/`
- execute every request and background task inside that user workspace boundary
- point `HERMES_HOME` at that workspace-local Hermes runtime home

Do not create one Hermes CLI profile per end user as the primary tenancy model.

If Hermes needs multiple runtime personas later, those should be app/service agents such as:

- `coder`
- `research-bot`
- `ops-agent`

Those are Hermes agent profiles, not customer profiles.

### Recommended Isolation Model

Use one Hermes runtime instance per user workspace.

Concretely:

- user workspace root: `workspaces/<workspace_slug>/`
- workspace runtime root: `workspaces/<workspace_slug>/agent/`
- workspace Hermes home: `workspaces/<workspace_slug>/agent/.hermes/`
- request-scoped `HERMES_HOME`: `workspaces/<workspace_slug>/agent/.hermes/`

Why this is the recommended model:

- Hermes built-in memory becomes naturally per-workspace
- installed skills and plugins can be tenant-scoped
- logs, auth files, and provider config stay isolated
- no need to reinterpret Hermes CLI profiles as customer accounts
- matches Hermes’ actual contract: `HERMES_HOME` is the runtime home boundary

Tradeoff:

- more disk use and more provisioning work per tenant
- skill/plugin rollout needs a replication strategy

## Storage Split

### Postgres From Day One

Use Postgres for control-plane data:

- users
- Feishu identities
- tenants/workspaces
- memberships and roles
- profile slug allocation
- per-user config
- per-tenant config
- selected Hermes memory provider
- Feishu chat to user/profile/session mapping

### Defer Until Login/Profile Is Stable

Do not move session/run metadata to Postgres during the first login/profile rollout.

Migrate later, after isolation is stable and tested:

- session metadata indexes
- run metadata indexes
- reporting/admin query tables

### Filesystem Or Object Storage

Keep filesystem or object storage for data-plane state:

- workspace-local Hermes runtime home contents
- `USER.md` and `MEMORY.md`
- uploads
- session event logs
- run artifacts
- reports
- generated CSV/JSON/markdown outputs
- large working directories

Canonical rule:

- Postgres is the source of truth for identity and profile metadata.
- Filesystem paths are derived execution and storage locations.

## Feishu Login Design

### Web Login

Flow:

1. User clicks Sign in with Feishu in the frontend.
2. Backend completes the Feishu OAuth callback.
3. Backend resolves the external identity.
4. Backend finds or creates the app user and workspace mapping.
5. Backend creates or reuses the user workspace.
6. Backend issues an HttpOnly signed session cookie.
7. Subsequent API requests resolve user workspace context from the authenticated session.

### Feishu Chat Auto-Provision

Flow:

1. Inbound Feishu sender identity is resolved first.
2. Backend finds or creates the app user and workspace mapping.
3. Backend creates or reuses the user workspace.
4. Chat session is created under that user’s workspace-scoped data root.
5. Future messages reuse the mapped user/workspace/session.

### Runtime Contract

Every authenticated request or background task must:

- resolve workspace context before runtime execution
- set `HERMES_HOME=workspaces/<workspace_slug>/agent/.hermes`
- set the Vibe-Trading runtime root to `workspaces/<workspace_slug>/agent/`
- ensure sessions, runs, uploads, and swarm data remain within that user scope

The default service deployment should therefore be understood as:

- Hermes home per user request: `workspaces/<workspace_slug>/agent/.hermes`
- user workspace root: `workspaces/<workspace_slug>/agent/`

not:

- one shared `HERMES_HOME` for all end users

## Memory Strategy

### V1: Built-in Hermes Memory First

Use Hermes built-in memory first:

- per-user `USER.md`
- per-user `MEMORY.md`
- optional session search for deeper history

Why:

- it is already scoped to the active `HERMES_HOME`
- it requires no custom provider work
- it is the safest first layer for multi-tenant isolation

Important caveat:

- because Hermes built-in memory is tied to `HERMES_HOME`, per-user memory isolation is only rigorous if each user workspace has its own isolated Hermes runtime home
- this is the main reason to prefer one Hermes runtime instance per workspace

### Constraint: Only One External Provider

Hermes supports only one external memory provider at a time.

This is both:

- documented in the official Hermes memory-provider docs
- enforced in the vendored source code

Therefore:

- OpenViking + Hindsight cannot both be active natively inside Hermes at the same time

### V2: Choose One Active Provider Per User/Profile

Preferred v2 pattern:

- choose one active Hermes external provider strategy for the application runtime, or explicitly partition it by user workspace through the app’s integration layer
- keep the other system outside Hermes as an app-managed enrichment or indexing pipeline

Under the recommended model, external provider configuration should also be scoped per workspace-local `HERMES_HOME`.

Recommended provider roles:

- OpenViking for structured self-hosted knowledge browsing, ingestion, and tiered retrieval
- Hindsight for graph-style long-term recall, entity relationships, and reflection

### Day-One Readiness For Future Federation

Even before implementing advanced memory, prepare the architecture now:

- store per-user memory backend preference/config in Postgres
- keep provider selection behind an app abstraction rather than scattered request logic
- isolate provider bootstrap behind a single runtime resolver
- treat built-in Hermes memory as the always-on baseline layer
- keep separate resolvers for:
  - app workspace resolution
  - Hermes runtime resolution
- add a replicator/provisioner for seeding each workspace-local Hermes home with the approved base config, skills, and plugins

### Workspace Hermes Provisioning

Because each user workspace gets its own Hermes runtime home, the system needs a provisioning mechanism.

The plan should assume a workspace Hermes provisioner that can:

- create `workspaces/<workspace_slug>/agent/.hermes/`
- seed `config.yaml` and `.env` defaults
- seed approved skills
- seed approved plugins
- apply tenant entitlements
- run upgrades/sync when shared paid bundles change

This provisioner is the right place to implement future paid skill/plugin subscriptions.

## Backlog

### Shared Skill Publication

Design a deterministic backend function for promoting a workspace-local user skill into an approved shared skill location.

Proposed shape:

- `publish_workspace_skill(workspace_hermes_home, skill_name, actor, destination, approval_context)`

Required behavior:

- read only from the caller's workspace-local `HERMES_HOME`
- verify the actor is authorized to publish into the target shared scope
- require an explicit approval or moderation record before any copy occurs
- reuse deterministic path validation and security scanning from skill install/edit flows
- record provenance metadata: source workspace, publisher, approval record, publish time, source content hash
- reject prompt-driven direct file publication; the publish path must live in backend code
- support future scopes such as publish-to-org, publish-to-tenant, and publish-to-global without changing the call contract

### Hermes Runtime Isolation Follow-Up

Fix remaining import-time `HERMES_HOME` snapshots in the authenticated Hermes runtime so each request consistently uses `workspaces/<workspace_slug>/agent/.hermes`.

Priority areas:

- modules that cache `HERMES_HOME` or derived paths at import time
- `run_agent` startup that loads `.env` from `HERMES_HOME` before workspace context is applied
- authenticated session and swarm execution paths that isolate run/session directories but still rely on a process-wide Hermes home

### V3 Option: Federated Custom Memory Provider

Explicit v3 option:

- build a custom Vibe-Trading federated memory provider plugin
- it becomes the single active Hermes external provider
- internally it can route:
  - OpenViking for hierarchical knowledge assets and browse/retrieval
  - Hindsight for relationship recall and reflection

This is v3 only. Do not attempt it before:

- Feishu login is stable
- per-user Hermes profile isolation is stable
- initial Postgres identity rollout is stable in production

## Provider Notes

### OpenViking

OpenViking is a good fit when you want:

- self-hosted knowledge management
- filesystem-style hierarchy
- `viking://` browse/read workflows
- tiered context loading
- structured ingestion and categorized memory

References:

- <https://hermes-agent.nousresearch.com/docs/user-guide/features/memory-providers?_highlight=memory&_highlight=viki#openviking>
- [hermes-agent/plugins/memory/openviking/__init__.py](/home/chris/repo/Vibe-Trading/hermes-agent/plugins/memory/openviking/__init__.py)

### Hindsight

Hindsight is a good fit when you want:

- knowledge graph style recall
- relationship-heavy long-term memory
- reflection and synthesis
- local embedded PostgreSQL or cloud-backed operation
- auto-retain and auto-recall workflows

References:

- <https://hermes-agent.nousresearch.com/docs/user-guide/features/memory-providers?_highlight=memory&_highlight=viki#openviking>
- [hermes-agent/plugins/memory/hindsight/__init__.py](/home/chris/repo/Vibe-Trading/hermes-agent/plugins/memory/hindsight/__init__.py)

## Implementation Phases

1. Add Feishu-authenticated app user/profile mapping in Postgres.
2. Create real Hermes profiles per user with config-only cloning.
3. Make backend request handling profile-scoped via per-request `HERMES_HOME`.
4. Keep Hermes built-in memory as the initial per-user memory solution.
5. Stabilize and test login/profile isolation thoroughly.
6. Add Postgres-backed session/run metadata after the rollout is stable.
7. Add one optional external Hermes memory provider after profile isolation is stable.
8. Treat a custom federated memory provider as a v3 option only.

## Risks And Constraints

- Current backend has process-global and file-global assumptions that are unsafe for SaaS multi-tenancy.
- If `HERMES_HOME` is set too late, users can leak memory, config, or session state across profiles.
- `--clone-all` profile creation is unsafe for new-user provisioning.
- Built-in memory is frozen at session start, so mid-session memory writes do not affect the current prompt.
- Hermes supports only one external provider at a time.
- Native OpenViking + Hindsight simultaneous activation is not a supported runtime mode.
- A federated provider is a v3 option, not a v1 or v2 deliverable.
- Session/run metadata should not move into Postgres during the first login/profile rollout because it increases migration surface area and makes tenant-isolation debugging harder.

## Acceptance Criteria

The implementation based on this plan must preserve these rules:

- the app, not Hermes, owns canonical user identity
- Hermes profiles are the per-user runtime boundary
- Postgres is used for control-plane state from day one
- session/run metadata moves to Postgres only after login/profile rollout is stable and tested
- filesystem/object storage remains the runtime/data-plane store
- built-in Hermes memory remains enabled for every user
- only one external Hermes memory provider can be active at a time
- OpenViking and Hindsight can both be part of the long-term architecture, but not as two simultaneously active Hermes providers
- day-one architecture is ready for a future federated provider
- the federated memory provider is a v3 option explicitly, not a v1/v2 deliverable
