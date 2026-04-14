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

## Conventions

- For browser debugging, use Chrome DevTools with remote Chrome on port `9222`. Do not use the integrated browser.
- Use Markdown-native output for reports shown in the UI. Prefer Markdown tables, Mermaid, and VChart JSON; avoid ANSI art or terminal box drawing.
- Frontend imports use the `@/` alias defined in `frontend/vite.config.ts` and `frontend/tsconfig.json`.
- Mermaid and VChart rendering flows through `frontend/src/components/common/MarkdownRenderer.tsx`. If rich content rendering breaks, debug that path first instead of patching page components.
- Session, run, and swarm artifacts are file-backed under the data root resolved by `agent/runtime_env.py`. Do not hardcode `agent/runs` or `agent/sessions`; `TERMINAL_CWD` may redirect storage to nested paths such as `agent/chris/`.
- If a task touches generated runtime output or model-rendered blocks, prefer fixing the sanitizer/prompt path at the source instead of only masking the frontend symptom.

## Reference Docs

- See `README.md` for product overview, setup paths, and CLI/server entrypoints.
- See `Architecture-Design.md` for system structure and design rationale.
- See `Migration-Plan.md` for Hermes integration and current architectural direction.
- See `agent/README.md` and `agent/SKILL.md` for backend workflows, MCP usage, and tool expectations.
