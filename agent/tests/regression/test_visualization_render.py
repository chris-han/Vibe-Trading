"""Regression tests for visualization rendering.

Covers the output formats declared in OUTPUT_FORMAT_PROMPT and produced
throughout the agent/ codebase:

  1. ECharts JSON blocks (```echarts```) – rendered by the frontend ECharts JS
      component for web UI rich content.
  2. VChart JSON blocks (```vchart```) – still accepted for Feishu/card rendering
      and legacy content; sanitized on the Python side by the Feishu visualization adapter.
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

from src.adapters.factory import get_feishu_visualization_adapter  # noqa: E402
from src.runtime_prompt_policy import OUTPUT_FORMAT_PROMPT  # noqa: E402


_FEISHU_ADAPTER = get_feishu_visualization_adapter()
_REPORT_GENERATE_SKILL = AGENT_ROOT / "src" / "skills" / "domain" / "vibe-trading" / "report-generate" / "SKILL.md"
_VALUATION_SKILL = AGENT_ROOT / "src" / "skills" / "domain" / "vibe-trading" / "valuation-model" / "SKILL.md"
_BULL_REPORT_SKILL = AGENT_ROOT / "src" / "skills" / "app-infra" / "research" / "bull-side-research" / "SKILL.md"
_BEAR_REPORT_SKILL = AGENT_ROOT / "src" / "skills" / "app-infra" / "research" / "bear-side-research" / "SKILL.md"
_WEB_OUTPUT_FORMAT_SKILL = AGENT_ROOT / "src" / "skills" / "domain" / "vibe-trading" / "output-format-web" / "SKILL.md"


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
        out = _FEISHU_ADAPTER.split_card_elements(text)
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
        out = _FEISHU_ADAPTER.split_card_elements(text)
        markdown = [item for item in out if item.get("tag") == "markdown"]
        assert markdown

    def test_radar_xy_fields_are_remapped_for_feishu(self):
        spec = {
            "type": "radar",
            "data": [{"id": "data", "values": [{"dimension": "A", "score": 1}]}],
            "xField": "dimension",
            "yField": "score",
        }
        result = self._roundtrip(spec)
        assert result["categoryField"] == "dimension"
        assert result["valueField"] == "score"
        assert "xField" not in result
        assert "yField" not in result

    def test_circular_progress_gets_synthetic_category_field_for_feishu(self):
        spec = {
            "type": "circularProgress",
            "data": [{"id": "data", "values": [{"value": 78}]}],
            "valueField": "value",
        }
        result = self._roundtrip(spec)
        assert result["categoryField"] == "_label"
        assert result["data"][0]["values"][0]["_label"] == "progress"

    def test_donut_gets_explicit_radii_for_feishu(self):
        spec = {
            "type": "pie",
            "data": [{"id": "data", "values": [{"region": "North", "value": 30}]}],
            "seriesField": "region",
            "valueField": "value",
            "isDonut": True,
        }
        result = self._roundtrip(spec)
        assert result["innerRadius"] == 0.5
        assert result["outerRadius"] == 0.8

    def test_wordcloud_seriesfield_is_promoted_to_namefield_for_feishu(self):
        spec = {
            "type": "wordCloud",
            "data": [{"id": "data", "values": [{"word": "AI", "weight": 80}]}],
            "seriesField": "word",
            "valueField": "weight",
        }
        result = self._roundtrip(spec)
        assert result["nameField"] == "word"
        assert "seriesField" not in result

    def test_label_text_stroke_is_removed_for_feishu_chart_labels(self):
        spec = {
            "type": "line",
            "data": {"values": [{"month": "Jan", "sales": 1}]},
            "xField": "month",
            "yField": "sales",
            "label": {
                "visible": True,
                "textBorderWidth": 4,
                "style": {"textStrokeWidth": 3, "lineWidth": 2},
                "textStyle": {"textBorderWidth": 5},
            },
        }
        result = self._roundtrip(spec)
        assert result["label"]["textBorderWidth"] == 0
        assert result["label"]["textStrokeWidth"] == 0
        assert result["label"]["style"]["textStrokeWidth"] == 0
        assert result["label"]["style"]["lineWidth"] == 0
        assert result["label"]["textStyle"]["textBorderWidth"] == 0

    def test_common_combo_shorthand_is_expanded_for_feishu(self):
        spec = {
            "type": "common",
            "data": [
                {"id": "bar", "values": [{"month": "Jan", "revenue": 120}]},
                {"id": "line", "values": [{"month": "Jan", "margin": 25}]},
            ],
            "xField": "month",
            "yField": ["revenue", "margin"],
            "seriesField": "type",
        }
        result = self._roundtrip(spec)
        assert result["series"] == [
            {"type": "bar", "dataIndex": 0, "xField": "month", "yField": "revenue"},
            {"type": "line", "dataIndex": 1, "xField": "month", "yField": "margin"},
        ]
        assert result["axes"] == [
            {"orient": "bottom", "type": "band"},
            {"orient": "left", "type": "linear"},
        ]
        assert "yField" not in result
        assert "seriesField" not in result

    def test_common_combo_data_id_is_rewritten_to_data_index_for_feishu(self):
        spec = {
            "type": "common",
            "data": [
                {"id": "bars", "values": [{"x": "Mon", "type": "Breakfast", "y": 15}]},
                {"id": "line", "values": [{"x": "Mon", "type": "Drink", "y": 22}]},
            ],
            "series": [
                {"type": "bar", "dataId": "bars", "xField": ["x", "type"], "yField": "y", "seriesField": "type"},
                {"type": "line", "dataId": "line", "xField": "x", "yField": "y", "seriesField": "type"},
            ],
            "axes": [{"orient": "bottom"}, {"orient": "left"}],
        }
        result = self._roundtrip(spec)
        assert result["series"] == [
            {"type": "bar", "dataIndex": 0, "xField": ["x", "type"], "yField": "y", "seriesField": "type"},
            {"type": "line", "dataIndex": 1, "xField": "x", "yField": "y", "seriesField": "type"},
        ]

    def test_common_combo_single_dataset_series_shorthand_is_normalized_for_feishu(self):
        spec = {
            "type": "common",
            "title": {"text": "销售目标追踪"},
            "data": {
                "values": [
                    {"month": "Jan", "sales": 42000, "target": 40000, "rate": 0.85},
                    {"month": "Feb", "sales": 38000, "target": 42000, "rate": 0.78},
                ]
            },
            "xField": "month",
            "series": [
                {"type": "bar", "yField": "sales", "name": "实际销售"},
                {"type": "line", "yField": "target", "name": "目标"},
                {"type": "line", "yField": "rate", "name": "完成率"},
            ],
        }

        result = self._roundtrip(spec)

        assert result["data"] == [
            {
                "id": "source",
                "values": [
                    {"month": "Jan", "sales": 42000, "target": 40000, "rate": 0.85},
                    {"month": "Feb", "sales": 38000, "target": 42000, "rate": 0.78},
                ],
            }
        ]
        assert result["series"] == [
            {"type": "bar", "yField": "sales", "name": "实际销售", "dataIndex": 0, "xField": "month"},
            {"type": "line", "yField": "target", "name": "目标", "dataIndex": 0, "xField": "month"},
            {"type": "line", "yField": "rate", "name": "完成率", "dataIndex": 0, "xField": "month"},
        ]
        assert result["axes"] == [
            {"orient": "bottom", "type": "band"},
            {"orient": "left", "type": "linear"},
        ]
        assert "xField" not in result

    def test_common_combo_with_invalid_data_index_is_downgraded_to_markdown(self):
        text = "```vchart\n" + json.dumps(
            {
                "type": "common",
                "title": {"text": "Broken Combo"},
                "data": [{"values": [{"x": "Mon", "y": 15}]}],
                "series": [{"type": "bar", "dataIndex": 9, "xField": "x", "yField": "y"}],
            }
        ) + "\n```"
        out = _FEISHU_ADAPTER.split_card_elements(text)

        charts = [item for item in out if item.get("tag") == "chart"]
        markdown = [item for item in out if item.get("tag") == "markdown"]

        assert not charts
        assert markdown
        assert "invalid dataIndex" in markdown[0]["content"]

    def test_chunk_card_elements_splits_many_charts_into_multiple_batches(self):
        blocks = []
        for index in range(6):
            blocks.append(
                "```vchart\n"
                + json.dumps(
                    {
                        "type": "line",
                        "title": {"text": f"Chart {index + 1}"},
                        "data": {"values": [{"x": "A", "y": index + 1}]},
                        "xField": "x",
                        "yField": "y",
                    }
                )
                + "\n```"
            )

        elements = _FEISHU_ADAPTER.split_card_elements("\n\n".join(blocks), enforce_chart_limit=False)
        batches = _FEISHU_ADAPTER.chunk_card_elements(elements)

        assert len(batches) == 6
        assert sum(1 for item in batches[0] if item.get("tag") == "chart") == 1
        assert sum(1 for item in batches[1] if item.get("tag") == "chart") == 1

    def test_chunk_card_elements_isolates_independent_chart_sections(self):
        blocks = []
        for index in range(3):
            blocks.append(
                f"## Chart {index + 1}\n\n说明 {index + 1}\n\n"
                + "```vchart\n"
                + json.dumps(
                    {
                        "type": "line",
                        "title": {"text": f"Chart {index + 1}"},
                        "data": {"values": [{"x": "A", "y": index + 1}]},
                        "xField": "x",
                        "yField": "y",
                    }
                )
                + "\n```"
            )

        elements = _FEISHU_ADAPTER.split_card_elements("\n\n".join(blocks), enforce_chart_limit=False)
        batches = _FEISHU_ADAPTER.chunk_card_elements(elements)

        assert len(batches) == 3
        for index, batch in enumerate(batches, start=1):
            assert sum(1 for item in batch if item.get("tag") == "chart") == 1
            assert any(item.get("tag") == "markdown" and f"Chart {index}" in item.get("content", "") for item in batch)

    def test_chunk_card_elements_attaches_shared_intro_to_first_chart_only(self):
        text = (
            "总览说明\n\n"
            "```vchart\n"
            + json.dumps(
                {
                    "type": "line",
                    "title": {"text": "Chart 1"},
                    "data": {"values": [{"x": "A", "y": 1}]},
                    "xField": "x",
                    "yField": "y",
                }
            )
            + "\n```\n\n"
            + "```vchart\n"
            + json.dumps(
                {
                    "type": "line",
                    "title": {"text": "Chart 2"},
                    "data": {"values": [{"x": "A", "y": 2}]},
                    "xField": "x",
                    "yField": "y",
                }
            )
            + "\n```"
        )

        elements = _FEISHU_ADAPTER.split_card_elements(text, enforce_chart_limit=False)
        batches = _FEISHU_ADAPTER.chunk_card_elements(elements)

        assert len(batches) == 2
        assert any(item.get("tag") == "markdown" and "总览说明" in item.get("content", "") for item in batches[0])
        assert not any(item.get("tag") == "markdown" and "总览说明" in item.get("content", "") for item in batches[1])

    def test_unsupported_chart_type_is_downgraded_to_markdown_table(self):
        text = "```vchart\n" + json.dumps(
            {
                "type": "candlestick",
                "title": "OHLC",
                "data": {
                    "values": [
                        {"date": "2026-04-15", "open": 100, "high": 110, "low": 95, "close": 108},
                        {"date": "2026-04-16", "open": 108, "high": 112, "low": 101, "close": 103},
                    ]
                },
            }
        ) + "\n```"
        out = _FEISHU_ADAPTER.split_card_elements(text)

        charts = [item for item in out if item.get("tag") == "chart"]
        markdown = [item for item in out if item.get("tag") == "markdown"]

        assert not charts
        assert markdown
        assert "candlestick" in markdown[0]["content"]
        assert "| date | open | high | low | close |" in markdown[0]["content"]

    def test_only_first_five_charts_render_as_chart_elements(self):
        blocks = []
        for index in range(6):
            blocks.append(
                "```vchart\n"
                + json.dumps(
                    {
                        "type": "line",
                        "title": f"Chart {index + 1}",
                        "data": {"values": [{"x": "A", "y": index + 1}]},
                        "xField": "x",
                        "yField": "y",
                    }
                )
                + "\n```"
            )
        out = _FEISHU_ADAPTER.split_card_elements("\n\n".join(blocks))

        charts = [item for item in out if item.get("tag") == "chart"]
        markdown = [item for item in out if item.get("tag") == "markdown"]

        assert len(charts) == 5
        assert markdown
        assert "Chart 6" in markdown[-1]["content"]
        assert "at most 5 charts" in markdown[-1]["content"]


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
        assert "Markdown pipe-tables" in OUTPUT_FORMAT_PROMPT

    def test_prompt_requires_mermaid_for_diagrams(self):
        p = OUTPUT_FORMAT_PROMPT
        assert "mermaid" in p.lower()
        assert "flowcharts" in p.lower() or "diagrams" in p.lower()

    def test_prompt_requires_echarts_for_web_charts(self):
        p = OUTPUT_FORMAT_PROMPT
        assert "echarts" in p.lower()
        assert "use echarts blocks for charts in the web ui." in p.lower()

    def test_prompt_requires_mermaid_fallback_for_uncertain_syntax(self):
        p = OUTPUT_FORMAT_PROMPT.lower()
        assert "unsupported or uncertain syntax" in p
        assert "fall back to markdown bullets or a markdown table" in p

    def test_prompt_forbids_ansi_art(self):
        p = OUTPUT_FORMAT_PROMPT
        assert "ANSI" in p or "ASCII" in p


class TestReportSkillActionPlanFormatting:
    def test_shared_report_skill_defaults_action_plans_to_markdown(self):
        text = _REPORT_GENERATE_SKILL.read_text(encoding="utf-8")
        assert "操作策略 / Action Plan" in text
        assert "Make Markdown the default for this section" in text

    def test_research_and_valuation_skills_require_markdown_action_plans(self):
        for skill_file in (_BULL_REPORT_SKILL, _BEAR_REPORT_SKILL, _VALUATION_SKILL):
            text = skill_file.read_text(encoding="utf-8")
            assert "操作策略 / Action Plan" in text
            assert "Markdown pipe-table" in text or "Markdown the default" in text

    def test_web_output_format_defaults_strategy_layouts_to_markdown(self):
        text = _WEB_OUTPUT_FORMAT_SKILL.read_text(encoding="utf-8")
        assert "recommendation, action-plan, and `操作策略` sections" in text
        assert "Markdown bullets or Markdown pipe-tables by default" in text
