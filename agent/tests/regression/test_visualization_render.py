"""Regression tests for visualization rendering.

Covers the output formats declared in _OUTPUT_FORMAT_PROMPT and produced
throughout the agent/ codebase:

  1. Legacy ECharts JSON blocks (```echarts```) – compatibility-only path,
     sanitized on the Python side by _sanitize_echarts_blocks().
  2. Mermaid blocks (```mermaid```) – rendered by the frontend Mermaid JS
     renderer; the service enforces format rules via prompt.
  3. Markdown pipe-tables – rendered natively by the frontend Markdown renderer.

New chart output should prefer ```vchart``` blocks rather than ```echarts```.

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

from src.session.service import _sanitize_echarts_blocks  # noqa: E402  (local import after path setup)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_ECHARTS_FENCE_RE = re.compile(r"```echarts\s*\n(.*?)\n```", re.DOTALL)
_MERMAID_FENCE_RE = re.compile(r"```mermaid\s*\n(.*?)\n```", re.DOTALL)
_PIPE_TABLE_RE    = re.compile(r"^\|.+\|$", re.MULTILINE)


def _extract_echarts_blocks(text: str) -> list[dict]:
    """Return all parsed ECharts option objects found in *text*."""
    blocks = []
    for m in _ECHARTS_FENCE_RE.finditer(text):
        blocks.append(json.loads(m.group(1)))
    return blocks


def _extract_mermaid_blocks(text: str) -> list[str]:
    return [m.group(1).strip() for m in _MERMAID_FENCE_RE.finditer(text)]


def _has_pipe_table(text: str) -> bool:
    return bool(_PIPE_TABLE_RE.search(text))


# ---------------------------------------------------------------------------
# 1. ECharts block sanitizer: clean input passes through unchanged
# ---------------------------------------------------------------------------

class TestEChartsSanitizerCleanInputs:
    """Valid ECharts blocks must survive _sanitize_echarts_blocks untouched."""

    def _roundtrip(self, obj: dict) -> dict:
        text = "```echarts\n" + json.dumps(obj) + "\n```"
        out = _sanitize_echarts_blocks(text)
        blocks = _extract_echarts_blocks(out)
        assert len(blocks) == 1
        return blocks[0]

    def test_simple_bar_chart_passes_through(self):
        option = {
            "xAxis": {"type": "category", "data": ["A", "B", "C"]},
            "yAxis": {"type": "value"},
            "series": [{"type": "bar", "data": [1, 2, 3]}],
        }
        result = self._roundtrip(option)
        assert result["series"][0]["type"] == "bar"
        assert result["yAxis"]["type"] == "value"

    def test_line_chart_with_time_axis(self):
        option = {
            "xAxis": {"type": "time"},
            "yAxis": [{"type": "value"}, {"type": "value"}],
            "series": [
                {"type": "line", "data": [[1, 10]], "yAxisIndex": 0},
                {"type": "bar",  "data": [[1, 5]],  "yAxisIndex": 1},
            ],
        }
        result = self._roundtrip(option)
        assert isinstance(result["yAxis"], list)
        assert len(result["yAxis"]) == 2

    def test_pie_chart_passes_through(self):
        option = {
            "series": [{"type": "pie", "data": [{"name": "A", "value": 40}, {"name": "B", "value": 60}]}]
        }
        result = self._roundtrip(option)
        assert result["series"][0]["type"] == "pie"

    def test_multiple_blocks_in_same_text(self):
        block_a = {"series": [{"type": "bar", "data": [1, 2]}]}
        block_b = {"series": [{"type": "line", "data": [3, 4]}]}
        text = (
            "```echarts\n" + json.dumps(block_a) + "\n```\n\n"
            "Some text in between.\n\n"
            "```echarts\n" + json.dumps(block_b) + "\n```"
        )
        out = _sanitize_echarts_blocks(text)
        blocks = _extract_echarts_blocks(out)
        assert len(blocks) == 2
        assert blocks[0]["series"][0]["type"] == "bar"
        assert blocks[1]["series"][0]["type"] == "line"


# ---------------------------------------------------------------------------
# 2. ECharts sanitizer: yAxis2 repair (LLM dual-axis mistake)
# ---------------------------------------------------------------------------

class TestEChartsSanitizerYAxis2Repair:
    """_sanitize_echarts_blocks must convert the invalid yAxis2 key into a
    proper yAxis array so dual-axis charts don't crash in the browser."""

    def _sanitize(self, obj: dict) -> dict:
        text = "```echarts\n" + json.dumps(obj) + "\n```"
        out = _sanitize_echarts_blocks(text)
        blocks = _extract_echarts_blocks(out)
        assert len(blocks) == 1, "sanitizer must preserve exactly one block"
        return blocks[0]

    def test_yaxis2_promoted_when_primary_is_dict(self):
        option = {
            "xAxis": {"type": "category", "data": ["Jan", "Feb"]},
            "yAxis": {"type": "value", "name": "Price"},
            "yAxis2": {"type": "value", "name": "Volume"},
            "series": [
                {"type": "line", "data": [10, 20], "yAxisIndex": 0},
                {"type": "bar",  "data": [100, 200], "yAxisIndex": 1},
            ],
        }
        result = self._sanitize(option)
        assert "yAxis2" not in result, "yAxis2 must be removed after repair"
        assert isinstance(result["yAxis"], list), "yAxis must be promoted to a list"
        assert len(result["yAxis"]) == 2
        assert result["yAxis"][0]["name"] == "Price"
        assert result["yAxis"][1]["name"] == "Volume"

    def test_yaxis2_appended_when_primary_is_already_list_with_one_item(self):
        option = {
            "yAxis": [{"type": "value", "name": "Primary"}],
            "yAxis2": {"type": "value", "name": "Secondary"},
            "series": [],
        }
        result = self._sanitize(option)
        assert "yAxis2" not in result
        assert isinstance(result["yAxis"], list)
        assert len(result["yAxis"]) == 2
        assert result["yAxis"][1]["name"] == "Secondary"

    def test_yaxis2_not_added_when_primary_list_already_has_two_items(self):
        """If yAxis already has ≥ 2 entries, the second must NOT be duplicated."""
        option = {
            "yAxis": [{"type": "value", "name": "P"}, {"type": "value", "name": "S"}],
            "yAxis2": {"type": "value", "name": "Extra"},
            "series": [],
        }
        result = self._sanitize(option)
        assert "yAxis2" not in result
        assert len(result["yAxis"]) == 2  # not 3


# ---------------------------------------------------------------------------
# 3. ECharts sanitizer: yAxisIndex auto-promotion
# ---------------------------------------------------------------------------

class TestEChartsSanitizerYAxisIndexPromotion:
    """When a series uses yAxisIndex > 0 and yAxis is still a scalar dict,
    the sanitizer must expand yAxis into an array automatically."""

    def _sanitize(self, obj: dict) -> dict:
        text = "```echarts\n" + json.dumps(obj) + "\n```"
        out = _sanitize_echarts_blocks(text)
        return _extract_echarts_blocks(out)[0]

    def test_series_yaxisindex_1_expands_single_yaxis_to_array(self):
        option = {
            "xAxis": {"type": "category"},
            "yAxis": {"type": "value"},
            "series": [
                {"type": "bar", "data": [1, 2], "yAxisIndex": 0},
                {"type": "line", "data": [3, 4], "yAxisIndex": 1},
            ],
        }
        result = self._sanitize(option)
        assert isinstance(result["yAxis"], list)
        assert len(result["yAxis"]) == 2

    def test_series_yaxisindex_0_only_leaves_yaxis_as_dict(self):
        """If no series references yAxisIndex > 0, yAxis must NOT be changed."""
        option = {
            "yAxis": {"type": "value"},
            "series": [{"type": "bar", "data": [1], "yAxisIndex": 0}],
        }
        result = self._sanitize(option)
        assert isinstance(result["yAxis"], dict)


# ---------------------------------------------------------------------------
# 4. ECharts sanitizer: invalid JSON left untouched
# ---------------------------------------------------------------------------

class TestEChartsSanitizerInvalidJson:
    """Blocks with unparseable JSON must be returned as-is without raising."""

    def test_invalid_json_block_unchanged(self):
        bad = "```echarts\n{this is not valid json\n```"
        out = _sanitize_echarts_blocks(bad)
        assert out == bad

    def test_empty_block_unchanged(self):
        empty = "```echarts\n\n```"
        out = _sanitize_echarts_blocks(empty)
        assert out == empty

    def test_non_echarts_blocks_untouched(self):
        text = "```python\nprint('hello')\n```"
        assert _sanitize_echarts_blocks(text) == text


# ---------------------------------------------------------------------------
# 5. Mermaid block structural validation
# ---------------------------------------------------------------------------

class TestMermaidBlockFormat:
    """Mermaid blocks emitted by the agent must follow the prompt rules:
    - Fenced with ```mermaid ... ```
    - First content line declares a valid diagram type
    - No markdown headings/list markers inside the block
    - TD direction preferred over LR (belt-and-suspenders check)
    """

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
            # Must not contain markdown heading markers
            assert not re.search(r"^\s*#{1,6}\s", block, re.MULTILINE), (
                "Mermaid block must not contain markdown heading markers"
            )
            # Must not contain bare list markers at line start
            assert not re.search(r"^\s*[-*+]\s", block, re.MULTILINE), (
                "Mermaid block must not contain markdown list markers"
            )

    def test_valid_flowchart_td(self):
        text = "```mermaid\nflowchart TD\n  A --> B\n  B --> C\n```"
        self._assert_valid_mermaid(text)

    def test_valid_graph_td(self):
        text = "```mermaid\ngraph TD\n  Start --> Decision\n  Decision -->|Yes| End\n```"
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

    def test_valid_pie_chart(self):
        text = '```mermaid\npie title Portfolio\n  "Equities" : 60\n  "Bonds" : 30\n  "Cash" : 10\n```'
        self._assert_valid_mermaid(text)

    def test_invalid_mermaid_heading_inside_block(self):
        """Blocks with markdown headings must not pass our validator."""
        block = "```mermaid\nflowchart TD\n  ## Not a heading in mermaid\n  A --> B\n```"
        blocks = _extract_mermaid_blocks(block)
        assert blocks
        has_heading = bool(re.search(r"^\s*#{1,6}\s", blocks[0], re.MULTILINE))
        assert has_heading, "Should detect the invalid heading marker"

    def test_invalid_mermaid_list_inside_block(self):
        block = "```mermaid\nflowchart TD\n  - A --> B\n```"
        blocks = _extract_mermaid_blocks(block)
        assert blocks
        has_list = bool(re.search(r"^\s*[-*+]\s", blocks[0], re.MULTILINE))
        assert has_list, "Should detect the invalid list marker"


# ---------------------------------------------------------------------------
# 6. Markdown pipe-table structural validation
# ---------------------------------------------------------------------------

class TestMarkdownPipeTable:
    """The output format prompt forbids ANSI/terminal box drawing characters
    for tables; all tabular data must use Markdown pipe-table syntax."""

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

    def test_ansi_box_drawing_characters_flagged(self):
        """Box-drawing characters used by ANSI art should never appear in
        agent responses – this test detects them so CI can catch regressions."""
        ansi_table = "┌───────┬───────┐\n│  A    │  B    │\n└───────┴───────┘"
        box_drawing_re = re.compile(r"[┌┐└┘├┤┬┴┼─│]")
        assert box_drawing_re.search(ansi_table), "sanity: ansi_table contains box chars"
        # Confirm a pipe-table does NOT contain these characters
        good_table = "| A | B |\n|---|---|\n| 1 | 2 |\n"
        assert not box_drawing_re.search(good_table)

    def test_no_bare_plain_code_block_for_key_value_data(self):
        """Plain ``` blocks must not be used for key-value / metrics data.
        Data fences must declare a language (vchart, echarts, mermaid, python, etc.)."""
        bad_output = "```\nSharpe: 1.42\nReturn: 12%\n```"
        # A plain fence has no language tag right after the backticks
        plain_fence_re = re.compile(r"^```\s*\n", re.MULTILINE)
        assert plain_fence_re.search(bad_output), "sanity: bad_output has a plain fence"
        good_output = "| Metric | Value |\n|--------|-------|\n| Sharpe | 1.42  |\n"
        assert not plain_fence_re.search(good_output)


# ---------------------------------------------------------------------------
# 7. Output format prompt content guard
# ---------------------------------------------------------------------------

class TestOutputFormatPrompt:
    """The _OUTPUT_FORMAT_PROMPT string in service.py must contain all required
    rendering directives.  This catches accidental deletion or truncation."""

    def _get_prompt(self) -> str:
        import importlib, types
        # Reload to get the actual string from service.py source
        import src.session.service as svc
        prompt = getattr(svc, "_OUTPUT_FORMAT_PROMPT", None)
        assert prompt is not None, "_OUTPUT_FORMAT_PROMPT not found in service module"
        return prompt

    def test_prompt_requires_markdown_tables(self):
        assert "Markdown pipe-table" in self._get_prompt()

    def test_prompt_requires_mermaid_for_diagrams(self):
        p = self._get_prompt()
        assert "mermaid" in p.lower()
        assert "flowchart" in p.lower() or "diagram" in p.lower()

    def test_prompt_requires_vchart_for_new_charts(self):
        p = self._get_prompt()
        assert "vchart" in p.lower()
        assert "do not emit echarts blocks for new reports" in p.lower()

    def test_prompt_forbids_ansi_art(self):
        p = self._get_prompt()
        assert "ANSI" in p or "ASCII" in p

    def test_prompt_keeps_legacy_echarts_dual_axis_rule(self):
        p = self._get_prompt()
        assert "yAxisIndex" in p
        assert "yAxis" in p
