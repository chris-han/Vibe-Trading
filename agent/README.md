# Vibe-Trading Agent

Agent package for the Vibe-Trading workspace.

Use a single virtual environment at `agent/.venv`.

Typical local setup:

```bash
cd agent
python3 -m venv .venv
./.venv/bin/python -m pip install -U pip setuptools wheel
./.venv/bin/python -m pip install -e .
```

Run commands from `agent/` with `./.venv/bin/python`, not bare `python` or `pip`.

---

Deployment note — session state

- The `agent` process is the canonical control plane for workspace-scoped sessions and message history. Do not read or treat `<workspace>/.hermes/state.db` as the UI canonical store; instead, use the `agent` REST APIs which mirror gateway messages into the `SessionStore` (cursor: `gateway_last_state_message_id`).
- For running the Hermes dashboard against a workspace, use `agent/hermes_dashboard_wrapper.py` to ensure proper per-request `HERMES_HOME` scoping and to avoid `hermes-agent` directly managing session state in production.
