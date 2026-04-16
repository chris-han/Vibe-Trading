# Repository Guidelines

## Project Structure & Module Organization
`agent/` contains the Python backend, CLI, API server, MCP entrypoints, and most tests. Key paths are `agent/src/` for runtime code, `agent/tests/` for unit and regression coverage, and `agent/config/` for swarm presets. `frontend/` is the Vite + React UI, with components under `frontend/src/components/`, pages in `frontend/src/pages/`, and shared utilities in `frontend/src/lib/`. `assets/` holds repo-level images and docs media.

## Build, Test, and Development Commands
Use a single Python environment in `agent/.venv` and prefer `uv`/explicit interpreter paths over bare `python3` or `pip`.
- `cd agent && uv run python cli.py serve --port 8899`: run the FastAPI backend.
- `cd frontend && bun install && bun run dev`: start the local UI on Vite. Use `bun` instead of `npm` for frontend work.
- `cd frontend && bun run build`: type-check and build the production frontend.
- `cd agent && uv run pytest`: run the Python test suite.
- `cd agent && uv run ruff check .`: lint Python code.

## Coding Style & Naming Conventions
Python targets 3.11 with Ruff enforcing a 120-character line limit. Keep code ASCII unless a file already uses Unicode. Use `snake_case` for Python functions/modules, `PascalCase` for React components, and `camelCase` for hooks and local TS variables. Match existing patterns in `agent/src/` and `frontend/src/`; avoid introducing new framework conventions unless necessary.

## Testing Guidelines
Pytest discovers `test_*.py` files, and `pytest.ini` keeps output quiet with `-q` while ignoring `hermes-agent/tinker-atropos`. Place fast unit tests near the relevant module and broader behavior checks in `agent/tests/regression/`. Prefer explicit async markers such as `@pytest.mark.asyncio` when testing coroutine code.

## Commit & Pull Request Guidelines
Recent commits use short Conventional Commit prefixes such as `feat:` and `fix:` followed by a clear imperative summary. Keep PRs focused, describe the user-facing effect, link related issues when applicable, and include screenshots or logs for UI and behavior changes. If a change touches both backend and frontend, call out the affected commands you used to verify it.

## Configuration & Safety
Set secrets in `agent/.env` rather than hard-coding them. Common variables include `OPENAI_API_KEY`, `OPENAI_BASE_URL`, `LANGCHAIN_PROVIDER`, and `LANGCHAIN_MODEL_NAME`. Do not modify vendored or submodule directories like `hermes-agent/` or `hermes-webui/` unless the task explicitly requires it.

## Workflow Guidance
Use the `systematic-debugging` skill for debugging work. Use the `ui-ux-pro-max` skill and [`UI-DESIGN.md`](/home/chris/repo/Vibe-Trading/UI-DESIGN.md) for UI design and implementation decisions. Treat [`Architecture-Design.md`](/home/chris/repo/Vibe-Trading/Architecture-Design.md) as the architecture design spec for repo changes.

## Visual Testing
For browser-based UI verification, run Chromium with remote debugging enabled on port `9222` and attach Chrome DevTools to that session. Use this path for visual regression checks, layout inspection, and interactive debugging instead of relying on screenshots alone.
