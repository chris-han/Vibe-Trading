---
name: deterministic-file-ops-policy
description: "Enforce the rule that file and directory operations must live in deterministic code paths such as tools, adapters, or helpers, not in prompts or skill text. Use when: reviewing prompt changes; adding new runtime prompts or skills; auditing path, create, update, or delete instructions; or wiring commit-time policy checks."
---

# Deterministic File Ops Policy

## Purpose

File and directory operations must be implemented in deterministic code, not delegated to model prompts.

That includes:

1. Create operations
2. Update operations
3. Delete operations
4. Path-layout assumptions

Prompts and runtime skill text may reference deterministic tools, but they must not tell the model to write files, edit files, delete files, create directories, or rely on hardcoded storage paths.

## Enforcement

This repo enforces the policy in three places:

1. Runtime code and helpers implement the actual file behavior
2. `tests/regression/test_prompt_file_ops_policy.py` guards prompt constants in backend runtime code
3. `.github/skills/deterministic-file-ops-policy/scripts/check_file_ops_policy.py` scans staged prompt/skill files and selected backend path-resolution helpers during commit

## When to Use This Skill

- You are editing `agent/src/session/service.py`
- You are editing `agent/src/runtime_prompt_policy.py`
- You are editing `agent/api_server.py` or `agent/src/skills/script_loader.py`
- You are editing `agent/src/swarm/worker.py`
- You are changing runtime prompt text or agent skill text
- You are adding a new shared skill under `agent/src/skills/` or `.github/skills/`
- You are reviewing a PR for prompt-level file or path instructions

## Disallowed in Prompts or Skill Text

- Direct `write_file`, `edit_file`, or delete-file instructions
- Telling the model to create `config.json` or `code/signal_engine.py`
- Telling the model where uploads live on disk
- Telling the model to rely on `uploads/` or hardcoded repo paths
- Telling the model to create or remove directories directly

## Disallowed in Selected Backend Helpers

- Single-location skill lookups such as `skills_dir / skill_name / "SKILL.md"` without fallback candidates or recursive discovery
- Backend path-resolution helpers that assume one fixed skill tree layout when the repo supports nested skill domains

## Allowed Pattern

- Prompts can tell the model to use deterministic tools such as `setup_backtest_run(...)` or `read_document(...)`
- The path resolution, create/update/delete behavior, and storage layout must be implemented in backend code

## Commit-Time Checks

The shared pre-commit hook runs the file-ops policy checker whenever relevant staged files change.

To install the shared hook for this repo clone:

```bash
python .github/skills/runtime-code-sanitizer/scripts/check_sanitizers.py --install-hook
```

The GitHub Action workflow `file-ops-policy.yml` also runs the checker in CI.