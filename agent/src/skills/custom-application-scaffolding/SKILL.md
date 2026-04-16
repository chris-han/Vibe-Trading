---
name: custom-application-scaffolding
description: Scaffold a custom Hermes-based application with the right split between domain tools, channel skills, and rendering adapters.
category: architecture
---

# Custom Application Scaffolding

Use this skill when building a new Hermes-based application or when extracting a repo-specific runtime into a reusable app skeleton.

The `scaffold-app` CLI command generates a custom application skeleton. That skeleton includes a Hermes plugin registration surface, but the plugin is only one part of the generated app.

## Core Rule

Keep these responsibilities separate:

| Concern | Put it in | Why |
|---------|-----------|-----|
| Domain/business execution | Tool | The model may need to invoke it |
| Channel formatting policy | Skill | The model needs render guidance, not executable code |
| Deterministic payload translation | Adapter | The app already knows how to serialize canonical output |
| Channel side effects | Platform action surface or channel-specific action tool | This is transport/integration behavior, not generic domain logic |

## Decision Matrix

| Need | Component |
|------|-----------|
| Backtest, data fetch, analysis, report assembly | Domain tool |
| Send Feishu approval card, push Slack reply, update page-local UI state | Channel-specific action tool or platform action surface |
| Convert canonical report/chart output into Feishu Card JSON | Adapter |
| Tell the model Feishu only supports Markdown tables and VChart subset | Skill |

## Recommended Skeleton

```text
<app>/
├── README.md
├── pyproject.toml
└── src/
    ├── __init__.py
    ├── app_runtime.py
    ├── adapters/
    │   ├── __init__.py
    │   ├── base.py
    │   ├── factory.py
    │   ├── web_visualization_adapter.py
    │   └── feishu_visualization_adapter.py
    ├── plugins/
    │   └── <app_module>/
    │       ├── __init__.py
    │       ├── schemas.py
    │       └── tools.py
    └── skills/
        ├── output-format-web/
        │   └── SKILL.md
        └── output-format-feishu/
            └── SKILL.md
```

Read the generated tree with this boundary in mind:

- `src/plugins/` is the Hermes discovery and registration surface.
- `src/skills/` is the prompt contract for channel behavior.
- `src/adapters/` is the deterministic runtime translation layer.
- `src/app_runtime.py` is the shared channel-agnostic runtime surface.
- `tests/` is the architectural regression layer that locks these boundaries in.

## CLI Scaffold

Use the built-in CLI to generate that starter layout:

```bash
cd agent
./.venv/bin/python cli.py scaffold-app my-custom-app --dest /tmp
```

Or, after install:

```bash
vibe-trading scaffold-app my-custom-app --dest /tmp
```

### CLI Usage Notes

The command shape is:

```bash
vibe-trading scaffold-app <name> --dest <parent-directory>
```

Behavior:

- `<name>` becomes the project directory name and Python module name after normalization.
- `--dest` is the parent directory where the new app folder will be created.
- The command creates `<parent-directory>/<normalized-name>/`.
- The command fails if the target directory already exists and is not empty.

Example:

```bash
vibe-trading scaffold-app "Acme Research" --dest /tmp
```

This produces a project rooted at:

```text
/tmp/acme-research/
```

If you are iterating on the scaffold repeatedly, delete the previous output or choose a new destination before rerunning the command.

## What the Scaffold Gives You

- A Hermes plugin entry point package for tool registration.
- A shared runtime module where channel-agnostic business logic belongs.
- Output-format skills for web and Feishu.
- A visualization adapter package for deterministic rendering.
- Generated regression tests that enforce plugin-boundary and channel-contract rules.
- A pyproject example showing how to export the Hermes plugin entry point.

## Generated Design Tests

The scaffold should generate tests immediately, not leave architectural enforcement as a TODO.

The generated tests should enforce at least these rules:

| Test concern | What it protects |
|--------------|------------------|
| Plugin boundary | Tool registration stays in the Hermes plugin surface rather than drifting into channel rendering code |
| Adapter factory contract | Channel selection stays centralized and deterministic |
| Skill/adapter channel set consistency | The set of channel skills stays aligned with the set of channel adapters |
| Channel payload boundary | Tool handlers do not start embedding renderer-specific payload details that belong in adapters or channel action surfaces |

When extending the scaffold, update these generated tests alongside the implementation so the architecture remains executable, not just documented.

## Channel Contract Consistency Rule

The generated scaffold contains multiple channel-specific surfaces that must describe the same rendering contract.

Keep these aligned:

| Surface | What it declares |
|---------|------------------|
| `src/skills/output-format-<channel>/SKILL.md` | What the model is told the channel can render |
| `src/adapters/*_<channel>*adapter.py` | What the runtime can actually translate deterministically |
| Channel-specific action tool, if you add one later | What the platform-side channel action accepts or sends |

The rule is simple:

- The skill must not advertise channel features the adapter cannot actually produce.
- The adapter must not silently emit payload structures the skill never tells the model about.
- If a channel action tool exists, its payload/input contract must match the adapter output it consumes.

Example consistency checks:

- If `output-format-feishu` says Feishu supports Markdown tables and a specific VChart subset, the Feishu adapter should emit only that subset.
- If a web skill says the web channel supports ECharts-style chart blocks, the web adapter should normalize canonical chart specs into that same render contract.
- If a Feishu send/update tool consumes Card 2.0 chart payloads, the Feishu adapter should output the same Card 2.0 structure rather than a parallel private shape.

## Scaffold Completion Checklist

After generating the scaffold, verify these before extending it:

1. The channel skill says only what the adapter can really render.
2. The adapter implements only the channel contract you want the model to rely on.
3. Any channel-specific action tool accepts the same payload shape the adapter emits.
4. Canonical domain output stays channel-agnostic; channel syntax stays in the adapter/action layer.
5. Regression tests lock in the chosen contract so skill and adapter cannot drift apart later.

## What to Customize First

1. Replace the sample schemas and handlers in `src/plugins/<app_module>/schemas.py` and `src/plugins/<app_module>/tools.py`.
2. Move real business logic into `src/app_runtime.py` or a domain package.
3. Update `output-format-web` and `output-format-feishu` for your application's rendering rules.
4. Replace placeholder adapter logic with real canonical-output translation.
5. Check that each channel skill and adapter describe the same rendering contract.
6. If you add channel-specific action tools, make their payload contract match the adapter output.
7. Add regression tests for plugin registration, adapter selection, and any channel-specific invariants.

The scaffold should already generate an initial version of those tests. Your job is to evolve them with the application rather than starting from zero.

## Guardrails

- Do not put Feishu Card JSON generation in tool handlers.
- Do not make the model call a renderer tool for deterministic serialization.
- Do not hardcode channel payload formats into domain services.
- Do not let generated skill docs and adapter/tool payload contracts drift apart.
- Do not add channel-specific side effects to otherwise reusable finance/domain tools.
- Every architectural refactor should add regression tests that lock in the intended boundary.