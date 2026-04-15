---
name: output-format-web
description: Output formatting rules for the Vibe-Trading web UI — Markdown tables, Mermaid diagrams, and ECharts JSON chart specs.
category: tool
---

# Output Format Rules (Web UI)

- Render all tables using Markdown pipe-table syntax, never ANSI or terminal box-drawing characters.
- Never use plain fenced code blocks (no language tag) to display data, metrics, or key-value information. Plain code blocks are reserved for actual code (Python, SQL, bash, etc.) only. Always use a Markdown pipe-table for named indicators or key-value pairs.
- Render flowcharts and relationship diagrams as Mermaid code blocks (` ```mermaid ... ``` `).
- Mermaid syntax: **always open with a diagram-type keyword on the first line**, e.g. `graph TD` or `flowchart TD`. Never write `top-down`, `left-right`, or any other English direction phrase as the first line — these are not valid Mermaid syntax. Valid opening keywords: `graph TD`, `graph LR`, `flowchart TD`, `flowchart LR`, `sequenceDiagram`, `classDiagram`, `stateDiagram-v2`, `erDiagram`, `gantt`, `pie`, `timeline`, `mindmap`, `gitGraph`.
- Mermaid layout: use `TD` (top-down) orientation for most diagrams; use `LR` only when node labels are very wide.
- Mermaid safety: avoid double quotes inside node labels (use plain text or single quotes), keep one statement per line, and never mix markdown headings/list markers inside a mermaid block.
- Mermaid timeline safety: for `timeline`, write section headers as `section Label` only, not `section Label : detail`; keep event text on the same `Period : Event` line and avoid HTML like `<br>`.
- Render time-series, bar charts, pie charts, and quantitative plots as ECharts JSON blocks (` ```echarts ... ``` ` with a valid ECharts option object); do NOT produce ASCII/ANSI chart art.
- Never use ANSI escape codes or terminal color sequences in responses.

## ECharts Spec Rules

Use standard ECharts option objects.

**Critical rule: every series must reference real data fields or literal arrays that exist in the option. Never invent field names or dimensions that are not present in the data source.**

For standard time-series charts, prefer explicit arrays with `xAxis.data` and `series[].data` because they are robust in the web renderer.

```json
{"title":{"text":"Monthly Sales"},"tooltip":{"trigger":"axis"},"legend":{"data":["Sales","Target"]},"xAxis":{"type":"category","data":["Jan","Feb"]},"yAxis":{"type":"value"},"series":[{"name":"Sales","type":"line","data":[1200,1400]},{"name":"Target","type":"line","data":[1000,1100]}]}
```

**Candlestick charts for the web UI should use standard ECharts candlestick options**, with:
- `xAxis.data` for timestamps
- `series[].type = "candlestick"`
- OHLC rows in `[open, close, low, high]` order

**Anti-pattern (WRONG):**
```json
{"type":"candlestick","data":{"values":[{"time":"2026-04-01","open":1,"high":2,"low":0.5,"close":1.5}]}}
```
This is wrong for the web UI because it is a VChart spec, not an ECharts option object.

For mixed charts, use a normal ECharts `series` array with one shared set of axes.

```json
{"tooltip":{"trigger":"axis"},"legend":{"data":["Volume","Price"]},"xAxis":{"type":"category","data":["Jan","Feb"]},"yAxis":[{"type":"value"},{"type":"value"}],"series":[{"name":"Volume","type":"bar","data":[120,130]},{"name":"Price","type":"line","yAxisIndex":1,"data":[90,95]}]}
```

If you cannot produce a valid ECharts option, fall back to a Markdown numeric table.
