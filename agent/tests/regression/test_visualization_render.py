"""Regression tests for visualization rendering.

Covers the output formats declared in _OUTPUT_FORMAT_PROMPT and produced
throughout the agent/ codebase:

  1. ECharts JSON blocks (```echarts```) – rendered by the frontend ECharts JS
      component for web UI rich content.
  2. VChart JSON blocks (```vchart```) – still accepted for Feishu/card rendering
      and legacy content; sanitized on the Python side by api_server._sanitize_vchart_spec().
  3. Mermaid blocks (```mermaid```) – rendered by the frontend Mermaid JS
     renderer; the service enforces format rules via prompt.
  4. Markdown pipe-tables – rendered natively by the frontend Markdown renderer.

Tests are purely unit-level (no LLM calls, no network).
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

# Make sure the agent root is importable regardless of pytest invocation cwd.
AGENT_ROOT = Path(__file__).resolve().parents[2]
if str(AGENT_ROOT) not in sys.path:
    sys.path.insert(0, str(AGENT_ROOT))

from api_server import _feishu_split_card_elements, _sanitize_vchart_spec  # noqa: E402
from src.session.service import _OUTPUT_FORMAT_PROMPT  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_VCHART_FENCE_RE = re.compile(r"```vchart\s*\n(.*?)\n```", re.DOTALL)
_MERMAID_FENCE_RE = re.compile(r"```mermaid\s*\n(.*?)\n```", re.DOTALL)
_PIPE_TABLE_RE = re.compile(r"^\|.+\|$", re.MULTILINE)


def _extract_vchart_blocks(text: str) -> list[dict]:
    """Return all parsed VChart specs found in *text*."""
    blocks = []
    for m in _VCHART_FENCE_RE.finditer(text):
        blocks.append(json.loads(m.group(1)))
    return blocks


def _extract_mermaid_blocks(text: str) -> list[str]:
    return [m.group(1).strip() for m in _MERMAID_FENCE_RE.finditer(text)]


def _has_pipe_table(text: str) -> bool:
    return bool(_PIPE_TABLE_RE.search(text))


# ---------------------------------------------------------------------------
# 1. VChart sanitizer and fence parsing
# ---------------------------------------------------------------------------


class TestVChartSanitizer:
    def _roundtrip(self, obj: dict) -> dict:
        text = "```vchart\n" + json.dumps(obj) + "\n```"
        out = _feishu_split_card_elements(text)
        charts = [item for item in out if item.get("tag") == "chart"]
        assert len(charts) == 1
        return charts[0]["chart_spec"]

    def test_title_string_is_promoted_to_object(self):
        spec = {
            "type": "line",
            "data": {"values": [{"month": "Jan", "sales": 1}]},
            "xField": "month",
            "yField": "sales",
            "title": "Monthly Sales",
        }
        result = self._roundtrip(spec)
        assert isinstance(result["title"], dict)
        assert result["title"]["text"] == "Monthly Sales"
        assert result["title"]["visible"] is True

    def test_title_value_is_promoted_to_text(self):
        spec = {
            "type": "bar",
            "data": {"values": [{"month": "Jan", "sales": 1}]},
            "xField": "month",
            "yField": "sales",
            "title": {"value": "Monthly Sales"},
        }
        result = self._roundtrip(spec)
        assert result["title"]["text"] == "Monthly Sales"

    def test_valid_vchart_blocks_roundtrip(self):
        text = "```vchart\n" + json.dumps(
            {
                "type": "line",
                "data": {"values": [{"month": "Jan", "sales": 1}]},
                "xField": "month",
                "yField": "sales",
            }
        ) + "\n```"
        blocks = _extract_vchart_blocks(text)
        assert len(blocks) == 1
        assert blocks[0]["type"] == "line"

    def test_invalid_json_block_is_left_as_markdown(self):
        text = "```vchart\n{this is not valid json\n```"
        out = _feishu_split_card_elements(text)
        markdown = [item for item in out if item.get("tag") == "markdown"]
        assert markdown


# ---------------------------------------------------------------------------
# 2. Mermaid block structural validation
# ---------------------------------------------------------------------------


class TestMermaidBlockFormat:
    """Mermaid blocks emitted by the agent must follow the prompt rules."""

    VALID_DIAGRAM_TYPES = {
        "graph", "flowchart", "sequenceDiagram", "classDiagram",
        "stateDiagram", "erDiagram", "gantt", "pie", "journey",
        "gitGraph", "quadrantChart", "mindmap", "timeline",
        "xychart-beta", "block-beta",
    }

    def _assert_valid_mermaid(self, text: str) -> None:
        blocks = _extract_mermaid_blocks(text)
        assert blocks, "Expected at least one mermaid block"
        for block in blocks:
            first_token = block.split()[0]
            assert first_token in self.VALID_DIAGRAM_TYPES, (
                f"Unknown Mermaid diagram type '{first_token}'"
            )
            assert not re.search(r"^\s*#{1,6}\s", block, re.MULTILINE), (
                "Mermaid block must not contain markdown heading markers"
            )
            assert not re.search(r"^\s*[-*+]\s", block, re.MULTILINE), (
                "Mermaid block must not contain markdown list markers"
            )

    def test_valid_flowchart_td(self):
        text = "```mermaid\nflowchart TD\n  A --> B\n  B --> C\n```"
        self._assert_valid_mermaid(text)

    def test_valid_sequence_diagram(self):
        text = (
            "```mermaid\n"
            "sequenceDiagram\n"
            "  participant A\n"
            "  participant B\n"
            "  A->>B: Hello\n"
            "```"
        )
        self._assert_valid_mermaid(text)

    def test_invalid_mermaid_heading_inside_block(self):
        block = "```mermaid\nflowchart TD\n  ## Not a heading in mermaid\n  A --> B\n```"
        blocks = _extract_mermaid_blocks(block)
        assert blocks
        has_heading = bool(re.search(r"^\s*#{1,6}\s", blocks[0], re.MULTILINE))
        assert has_heading, "Should detect the invalid heading marker"


# ---------------------------------------------------------------------------
# 3. Markdown pipe-table structural validation
# ---------------------------------------------------------------------------


class TestMarkdownPipeTable:
    """The output format prompt requires Markdown tables for tabular data."""

    def test_valid_pipe_table_detected(self):
        table = (
            "| Asset  | Weight | Return |\n"
            "|--------|--------|--------|\n"
            "| SPY    | 60%    | +2.5%  |\n"
            "| TLT    | 30%    | -0.3%  |\n"
            "| GLD    | 10%    | +1.1%  |\n"
        )
        assert _has_pipe_table(table)

    def test_pipe_table_without_separator_row_still_detected(self):
        table = "| Key | Value |\n| Sharpe | 1.42 |\n"
        assert _has_pipe_table(table)

    def test_no_bare_plain_code_block_for_key_value_data(self):
        bad_output = "```\nSharpe: 1.42\nReturn: 12%\n```"
        plain_fence_re = re.compile(r"^```\s*\n", re.MULTILINE)
        assert plain_fence_re.search(bad_output), "sanity: bad_output has a plain fence"
        good_output = "| Metric | Value |\n|--------|-------|\n| Sharpe | 1.42  |\n"
        assert not plain_fence_re.search(good_output)


# ---------------------------------------------------------------------------
# 4. Output format prompt content guard
# ---------------------------------------------------------------------------


class TestOutputFormatPrompt:
    def test_prompt_requires_markdown_tables(self):
        assert "Markdown pipe-tables" in _OUTPUT_FORMAT_PROMPT

    def test_prompt_requires_mermaid_for_diagrams(self):
        p = _OUTPUT_FORMAT_PROMPT
        assert "mermaid" in p.lower()
        assert "flowcharts" in p.lower() or "diagrams" in p.lower()

    def test_prompt_requires_echarts_for_web_charts(self):
        p = _OUTPUT_FORMAT_PROMPT
        assert "echarts" in p.lower()
        assert "use echarts blocks for charts in the web ui." in p.lower()

    def test_prompt_forbids_ansi_art(self):
        p = _OUTPUT_FORMAT_PROMPT
        assert "ANSI" in p or "ASCII" in p
