---
name: output-format-feishu
description: Output formatting rules for the Feishu/Lark Card 2.0 channel — Markdown tables and VChart v1.x specs only. Candlestick and other unsupported types must be replaced with Markdown tables.
category: tool
---

# Output Format Rules (Feishu Card 2.0)

- Render all tables using Markdown pipe-table syntax, never ANSI or terminal box-drawing characters.
- **Never use plain fenced code blocks (no language tag) for ANY content** — this includes data, metrics, key-value pairs, numbered lists, hierarchical outlines, tree structures, and process/logic flows. Plain code blocks render as monospace text in Feishu and must not be used.
- **Never emit bare JSON fragments or raw key-value lines as prose**, for example `"session_id": "b12c8b5d724b"` or `{ "status": "ok" }`, unless you are intentionally showing code in a fenced block with an explicit language such as `json`.
- For identifiers, metadata, and named values, use one of these formats instead:
  - Markdown bullet list, for example `- Session ID: \`b12c8b5d724b\``
  - Markdown pipe-table when there are multiple fields
  - Fenced code block with an explicit language like `json` only when the user truly needs raw machine-readable payload
- Render flowcharts, relationship diagrams, numbered outlines, and hierarchical/tree-style content as **pure Markdown text** using nested bullet lists, numbered lists, or indented outline style with arrow symbols (→, ↓). Do NOT use mermaid fenced code blocks, plain fenced code blocks, or ASCII box-drawing characters; Feishu Card 2.0 does not render them correctly.
- Render quantitative charts as VChart JSON blocks (` ```vchart ... ``` `).
- Never use ANSI escape codes or terminal color sequences.

## VChart Rules for Feishu Card 2.0

Feishu Card 2.0 uses **VChart v1.x** (NOT v2.x).

**Supported chart types ONLY:**

| Type | Notes |
|------|-------|
| `line` | |
| `area` | |
| `bar` | horizontal via `direction: "horizontal"` |
| `pie` | doughnut via `isDonut: true` |
| `common` | mixed-type combo |
| `funnel` | |
| `scatter` | |
| `radar` | |
| `linearProgress` | |
| `circularProgress` | |
| `wordCloud` | |

**FORBIDDEN — these will fail to render:**

`candlestick`, `rangeColumn`, `histogram`, `heatmap`, `treemap`, `sankey`, `boxPlot`, and any VChart type not listed above.

> **For OHLC / candlestick data: use a Markdown pipe-table instead. Never emit `"type": "candlestick"`.**

Additional constraints:
- Max 5 chart elements per card.
- No JavaScript in chart specs.
- Do NOT use VChart v2-only syntax. Use only simple `xField`/`yField`/`seriesField` patterns as shown in the Feishu chart type examples.
- If unsure whether a chart type is supported, fall back to a Markdown pipe-table.
- For a **single-series** line, area, or bar chart, **omit `seriesField` entirely**. Adding `seriesField` to a single-series chart causes VChart to split data into one mini-series per distinct field value; when that field is numeric (e.g. the same column as `yField`), every series contains only the rows matching that value and all dots render at the same Y height.
- When `seriesField` is needed for multi-series charts, it **must** be a dedicated categorical string column. It must **never** be the same field as `xField` or `yField`, and must never be a numeric column.
- For a **`common` combo chart**, follow the official Feishu combo schema exactly: use `data` as an array of datasets, and define every entry in `series[]` with its own `type`, `dataIndex`, `xField`, and `yField`. Do **not** emit the loose shorthand `data: {"values": [...]}` with top-level `xField` plus partial `series[]`; that shape is not the stable Feishu combo contract.
- For `common` charts that mix **bar + line**, include cartesian axes explicitly as `[{"orient":"bottom","type":"band"},{"orient":"left","type":"linear"}]` unless the user already supplied a stricter valid axis config.

Official `common` combo pattern:

```vchart
{
  "type": "common",
  "title": {"text": "组合图"},
  "data": [
    {
      "id": "combo_bar",
      "values": [
        {"x": "周一", "type": "早餐", "y": 15},
        {"x": "周一", "type": "午餐", "y": 25}
      ]
    },
    {
      "id": "combo_line",
      "values": [
        {"x": "周一", "type": "饮料", "y": 22},
        {"x": "周二", "type": "饮料", "y": 43}
      ]
    }
  ],
  "series": [
    {
      "type": "bar",
      "dataIndex": 0,
      "seriesField": "type",
      "xField": ["x", "type"],
      "yField": "y"
    },
    {
      "type": "line",
      "dataIndex": 1,
      "seriesField": "type",
      "xField": "x",
      "yField": "y"
    }
  ],
  "axes": [
    {"orient": "bottom", "type": "band"},
    {"orient": "left", "type": "linear"}
  ]
}
```
