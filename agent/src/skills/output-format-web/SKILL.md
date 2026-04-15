---
name: output-format-web
description: Output formatting rules for the Vibe-Trading web UI — Markdown tables, Mermaid diagrams, and VChart JSON chart specs.
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
- Render time-series, bar charts, pie charts, and quantitative plots as VChart JSON blocks (` ```vchart ... ``` ` with a valid VChart spec object); do NOT produce ASCII/ANSI chart art.
- Never use ANSI escape codes or terminal color sequences in responses.

## VChart Spec Rules

**Allowed single types:** `line`, `bar`, `area`, `pie`, `scatter`, `radar`, `funnel`, `gauge`, `circularProgress`, `linearProgress`, `wordCloud`, `waterfall`, `histogram`, `rose`, `rangeColumn`, `rangeArea`, `boxPlot`, `heatmap`, `sunburst`, `circlePacking`, `treemap`, `sankey`, `correlation`, `sequence`, `map`, `candlestick`.

**Critical rule: every field name referenced in `xField`, `yField`, `seriesField`, `categoryField`, `valueField`, etc. MUST be an exact key present in the data `values` objects. Never invent a field name that is not in the data.**

For multi-series of the **same** chart type (e.g. two lines), convert to **long/tidy format** — one row per data point with a `value` column and a `series` column:

```json
{"type":"line","data":{"values":[{"month":"Jan","value":1200,"series":"Sales"},{"month":"Jan","value":1000,"series":"Target"},{"month":"Feb","value":1400,"series":"Sales"},{"month":"Feb","value":1100,"series":"Target"}]},"xField":"month","yField":"value","seriesField":"series","axes":[{"orient":"bottom","type":"band"},{"orient":"left","type":"linear"}]}
```

**Anti-pattern (WRONG) — wide format with mismatched field names:**
```json
{"type":"line","data":{"values":[{"month":"Jan","Sales":1200,"Target":1000}]},"xField":"month","yField":"value","seriesField":"type"}
```
This is wrong because `"value"` and `"type"` are not keys in the data rows. Always use long format for multi-series.

For mixing **different** chart types (e.g. bar + line combo), use `type: "common"` with a `series` array. Each series must have its own `xField`/`yField`. Data is a top-level array with `id` per entry:

```json
{"type":"common","data":[{"id":"d0","values":[{"x":"Jan","bar":120,"line":90}]}],"series":[{"type":"bar","dataIndex":0,"xField":"x","yField":"bar"},{"type":"line","dataIndex":0,"xField":"x","yField":"line"}],"axes":[{"orient":"bottom","type":"band"},{"orient":"left","type":"linear"}]}
```

Do NOT use unsupported types. If a chart idea requires an unsupported type, fall back to a Markdown table.

- **Data format:** `"data": {"values": [...]}` for most types. Pie uses `categoryField`/`valueField`; **radar uses `categoryField`/`valueField`** (NOT `xField`/`yField`); candlestick uses `openField`/`closeField`/`lowField`/`highField`.
- **Radar chart field names:** ALWAYS use `categoryField` for the dimension axis and `valueField` for the score axis. Using `xField`/`yField` on a radar chart renders only a single dot — this is a known silent failure.
- **Axes:** Cartesian charts (line, bar, area, scatter, common, candlestick) MUST include an `axes` array: `[{"orient":"bottom","type":"band"},{"orient":"left","type":"linear"}]`. Radar charts do NOT use an `axes` array.
- **Self-check before output:** For every field name in the spec (`xField`, `yField`, `seriesField`, etc.), verify it is an exact key in the `values` array objects. If any field name is missing from the data, fix the data or the field name before outputting.
- **Style:** Use VChart-native fields and styles only. VChart tooltips: use `"tooltip": {}`. VChart smooth lines: use `"line": {"style": {"curveType": "monotone"}}`.
- If you cannot produce a valid VChart spec, fall back to a Markdown numeric table.
