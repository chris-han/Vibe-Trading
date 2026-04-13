# Visualization-producing prompts and code in agent/

This file lists locations in the `agent/` tree that contain prompts, code, or generated output which produce diagrams, tables, or charts (Mermaid, ECharts, Markdown tables, Rich tables, printed charts, etc.). Use the links to jump to the relevant file/lines.

- **Session rendering rules & ECharts/Mermaid sanitizer**: [agent/src/session/service.py](agent/src/session/service.py#L58-L96) — guidance to render tables as Markdown, flowcharts as Mermaid (```mermaid```), and plots as ECharts (```echarts```); includes `_sanitize_echarts_blocks` and usage at [agent/src/session/service.py](agent/src/session/service.py#L958).

- **CLI Rich tables**: [agent/cli.py](agent/cli.py#L40) (imports `rich.table.Table`) and multiple table builders, e.g. commands table at [agent/cli.py](agent/cli.py#L527), dashboard live table builder at [agent/cli.py](agent/cli.py#L793-L813), and run/session tables at [agent/cli.py](agent/cli.py#L988-L1001) and [agent/cli.py](agent/cli.py#L1286-L1304).

- **MCP / skill prompts referencing chart patterns**: [agent/mcp_server.py](agent/mcp_server.py#L320) — mentions detection of technical chart patterns and related tooling.

- **Skill / README guidance**: [agent/SKILL.md](agent/SKILL.md#L65) and [agent/SKILL.md](agent/SKILL.md#L90) — references to charting, backtesting outputs, and recommended DataFrame usage (tables).

- **Backtest / DataFrame code (table-like outputs)**: Examples where `pandas` DataFrames are central (often rendered as numeric tables): [agent/backtest/runner.py](agent/backtest/runner.py#L37-L40), [agent/backtest/metrics.py](agent/backtest/metrics.py#L11), and optimizer modules such as [agent/backtest/optimizers/mean_variance.py](agent/backtest/optimizers/mean_variance.py#L6-L19).

- **Swarm config prompts that request tables/scorecards**: multiple YAML prompts under `agent/config/swarm/` request explicit table outputs or score tables, for example:
  - [agent/config/swarm/sector_rotation_team.yaml](agent/config/swarm/sector_rotation_team.yaml#L99)
  - [agent/config/swarm/crypto_trading_desk.yaml](agent/config/swarm/crypto_trading_desk.yaml#L137)
  - [agent/config/swarm/fundamental_research_team.yaml](agent/config/swarm/fundamental_research_team.yaml#L42)
  - [agent/config/swarm/geopolitical_war_room.yaml](agent/config/swarm/geopolitical_war_room.yaml#L41)

- **Generated run artifacts with Markdown tables & reports**: the `.swarm` run outputs include many Markdown reports and pipe-tables. Example run files with large embedded tables and summaries:
  - [agent/.swarm/runs/swarm-20260412-130547-053a70ff/run.json](agent/.swarm/runs/swarm-20260412-130547-053a70ff/run.json#L124)
  - [agent/.swarm/runs/swarm-20260412-130547-053a70ff/events.jsonl](agent/.swarm/runs/swarm-20260412-130547-053a70ff/events.jsonl#L36)

Notes and next steps
- The scan focused on explicit keywords (Mermaid, ECharts, chart/table/plot, Rich tables, pandas DataFrame and prompt YAML). There may be additional places that render visuals indirectly (e.g., functions producing JSON intended for ECharts, or skills that return Markdown). If you want, I can:
  - expand the scan with additional keywords, or
  - open each referenced file and extract short code snippets/examples for the report.

If you'd like more detail (code snippets, extracted Mermaid/ECharts blocks, or a CSV summary), tell me which format you prefer.

**Visualization Index Table**

| Visualization Type | Render component / location | Tech stack (prompt / js / py) |
|---|---|---|
| Flowcharts / diagrams (Mermaid) | [agent/src/session/service.py](agent/src/session/service.py#L58-L96) — LLM should emit ```mermaid``` blocks; renderer/sanitizer enforces format | Prompt (Mermaid) → rendered by frontend Markdown/Mermaid renderer |
| Charts (ECharts JSON) | [agent/src/session/service.py](agent/src/session/service.py#L66-L96) and `_sanitize_echarts_blocks` at [agent/src/session/service.py](agent/src/session/service.py#L78); frontend expects ```echarts``` blocks | Prompt (ECharts JSON) → frontend ECharts (JS); validated in Python service |
| Markdown tables / scorecards | Swarm prompt YAML under [agent/config/swarm/](agent/config/swarm/) and generated run reports such as [agent/.swarm/runs/swarm-20260412-130547-053a70ff/run.json](agent/.swarm/runs/swarm-20260412-130547-053a70ff/run.json#L124) | Prompt (Markdown) and Python-generated Markdown |
| Terminal / live tables (Rich) | `rich.table.Table` usages in [agent/cli.py](agent/cli.py#L527-L552), dashboard/live panel builders at [agent/cli.py](agent/cli.py#L793-L813) | Python (rich)
| Pandas DataFrame outputs (numeric tables) | Backtest and optimizer modules: [agent/backtest/runner.py](agent/backtest/runner.py#L37-L40), [agent/backtest/metrics.py](agent/backtest/metrics.py#L11) | Python (pandas) — often converted to Markdown or console tables
| Printed / ASCII charts in artifacts | Generated analysis scripts and `.swarm` run artifacts (see [agent/.swarm/runs/.../events.jsonl](agent/.swarm/runs/swarm-20260412-130547-053a70ff/events.jsonl#L36)) | Python scripts (console printing) — sometimes legacy ASCII art

