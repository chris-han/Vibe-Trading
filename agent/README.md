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
