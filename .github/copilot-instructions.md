# Project Guidelines

## Build and Test

- Backend work happens from `agent/` using the repo virtualenv only. Prefer explicit commands such as `./.venv/bin/python -m pip install -e .`, `./.venv/bin/python api_server.py --port 8899`, and `./.venv/bin/python -m pytest -q`.
- Do not rely on bare `python`, `python3`, or `pip` for repo automation. Venv activation can be inconsistent here.
- Frontend work happens from `frontend/` and should use Bun: `bun install`, `bun dev`, and `bun run build`.
- The frontend dev server runs on port `5899` and proxies API/SSE requests to the backend on port `8899`. HMR uses port `5901`.

## Architecture

- `agent/api_server.py` is the FastAPI entrypoint for REST, SSE, session APIs, swarm APIs, uploads, and serving the built frontend.
- `agent/src/session/service.py` is the main chat/session orchestration layer. Changes to output formatting, report rendering, tool fallback behavior, or session UX usually belong there.
- `agent/src/swarm/` owns multi-agent swarm runtime, persistence, and task orchestration.
- `agent/src/backtest/` and `agent/backtest/` contain the trading/backtest engines and related domain models.
- `frontend/src/pages/Agent.tsx` is the main chat UI. Shared renderers and rich content blocks live in `frontend/src/components/common/`.
- `hermes-agent/` is a separate upstream-style subsystem in the same workspace. Avoid changing it unless the task explicitly targets Hermes internals.

## Project Structure & Module Organization

`agent/` contains the Python backend, CLI, API server, MCP entrypoints, and most tests. Key paths are `agent/src/` for runtime code, `agent/tests/` for unit and regression coverage, and `agent/config/` for swarm presets. `frontend/` is the Vite + React UI, with components under `frontend/src/components/`, pages in `frontend/src/pages/`, and shared utilities in `frontend/src/lib/`. `assets/` holds repo-level images and docs media.

## Conventions

- For browser debugging, use Chrome DevTools with remote Chrome on port `9222`. Do not use the integrated browser.
- Use Markdown-native output for reports shown in the UI. Prefer Markdown tables, Mermaid, and VChart JSON; avoid ANSI art or terminal box drawing.
- Frontend imports use the `@/` alias defined in `frontend/vite.config.ts` and `frontend/tsconfig.json`.
- Mermaid and VChart rendering flows through `frontend/src/components/common/MarkdownRenderer.tsx`. If rich content rendering breaks, debug that path first instead of patching page components.
- Session, run, and swarm artifacts are file-backed under the data root resolved by `agent/runtime_env.py`. Do not hardcode `agent/runs` or `agent/sessions`; `TERMINAL_CWD` may redirect storage to nested paths such as `agent/chris/`.
- If a task touches generated runtime output or model-rendered blocks, prefer fixing the sanitizer/prompt path at the source instead of only masking the frontend symptom.

## Coding Style & Naming Conventions

Python targets 3.11 with Ruff enforcing a 120-character line limit. Keep code ASCII unless a file already uses Unicode. Use `snake_case` for Python functions/modules, `PascalCase` for React components, and `camelCase` for hooks and local TS variables. Match existing patterns in `agent/src/` and `frontend/src/`; avoid introducing new framework conventions unless necessary.

## Testing Guidelines

Pytest discovers `test_*.py` files, and `pytest.ini` keeps output quiet with `-q` while ignoring `hermes-agent/tinker-atropos`. Place fast unit tests near the relevant module and broader behavior checks in `agent/tests/regression/`. Prefer explicit async markers such as `@pytest.mark.asyncio` when testing coroutine code.

## Commit & Pull Request Guidelines

Recent commits use short Conventional Commit prefixes such as `feat:` and `fix:` followed by a clear imperative summary. Keep PRs focused, describe the user-facing effect, link related issues when applicable, and include screenshots or logs for UI and behavior changes. If a change touches both backend and frontend, call out the affected commands you used to verify it.

## Configuration & Safety

Set secrets in `agent/.env` rather than hard-coding them. Common variables include `OPENAI_API_KEY`, `OPENAI_BASE_URL`, `LANGCHAIN_PROVIDER`, and `LANGCHAIN_MODEL_NAME`. Do not modify vendored or submodule directories like `hermes-agent/` or `hermes-webui/` unless the task explicitly requires it.

## Workflow Guidance

Use the `systematic-debugging` skill for debugging work. Use the `ui-ux-pro-max` skill and [DESIGN.md](DESIGN.md) for UI design and implementation decisions. Treat [Architecture-Design.md](Architecture-Design.md) as the architecture design spec for repo changes.

## Visual Testing

For browser-based UI verification, run Chromium with remote debugging enabled on port `9222` and attach Chrome DevTools to that session. Use this path for visual regression checks, layout inspection, and interactive debugging instead of relying on screenshots alone.

## Reference Docs

- See `README.md` for product overview, setup paths, and CLI/server entrypoints.
- See `Architecture-Design.md` for system structure and design rationale.
- See `Migration-Plan.md` for Hermes integration and current architectural direction.
- See `agent/README.md` and `agent/SKILL.md` for backend workflows, MCP usage, and tool expectations.
