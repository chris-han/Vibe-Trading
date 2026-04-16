"""Feishu Card 2.0 visualization adapter."""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from .base import BaseVisualizationAdapter


logger = logging.getLogger("feishu.visualization")


@dataclass(frozen=True)
class FeishuVisualizationAdapter(BaseVisualizationAdapter):
    stream_element_id: str = "vt_stream_body"
    chart_aspect_ratio: str = "4:3"
    max_chart_elements: int = 5

    _VCHART_FENCE_RE = re.compile(r"```(?:vchart|chart)\s*\n(.*?)\n\s*```", re.DOTALL)
    _SUPPORTED_CHART_TYPES = frozenset({
        "line",
        "area",
        "bar",
        "pie",
        "common",
        "funnel",
        "scatter",
        "radar",
        "linearProgress",
        "circularProgress",
        "wordCloud",
    })
    _LABELISH_KEYS = frozenset({"label", "outerLabel", "transformLabel"})

    @property
    def channel(self) -> str:
        return "feishu"

    @staticmethod
    def _infer_common_series_type(data_id: str, index: int) -> str:
        lowered = data_id.lower()
        if "line" in lowered:
            return "line"
        if "area" in lowered:
            return "area"
        if "scatter" in lowered:
            return "scatter"
        if "pie" in lowered:
            return "pie"
        if "bar" in lowered or "column" in lowered:
            return "bar"
        return "bar" if index == 0 else "line"

    @staticmethod
    def _common_axis_defaults(axes: Any) -> List[Dict[str, Any]]:
        normalized_axes: List[Dict[str, Any]] = []
        seen_orients: set[str] = set()

        if isinstance(axes, list):
            for axis in axes:
                if not isinstance(axis, dict):
                    continue
                axis_dict = dict(axis)
                orient = axis_dict.get("orient")
                if axis_dict.get("type") is None:
                    if orient == "bottom":
                        axis_dict["type"] = "band"
                    elif orient in {"left", "right"}:
                        axis_dict["type"] = "linear"
                if isinstance(orient, str):
                    seen_orients.add(orient)
                normalized_axes.append(axis_dict)

        if "bottom" not in seen_orients:
            normalized_axes.append({"orient": "bottom", "type": "band"})
        if not ({"left", "right"} & seen_orients):
            normalized_axes.append({"orient": "left", "type": "linear"})

        return normalized_axes

    @staticmethod
    def _infer_common_y_field(
        dataset: Any,
        *,
        x_field: Any,
        y_fields: Any,
        index: int,
        series_field: Any,
    ) -> str:
        if isinstance(y_fields, list) and index < len(y_fields) and isinstance(y_fields[index], str):
            return y_fields[index]
        if isinstance(y_fields, str):
            return y_fields

        values = dataset.get("values") if isinstance(dataset, dict) else None
        first_value = values[0] if isinstance(values, list) and values else {}
        if isinstance(first_value, dict):
            excluded_fields = set()
            if isinstance(x_field, str):
                excluded_fields.add(x_field)
            elif isinstance(x_field, list):
                excluded_fields.update(field for field in x_field if isinstance(field, str))
            if isinstance(series_field, str):
                excluded_fields.add(series_field)
            return next((key for key in first_value.keys() if key not in excluded_fields), "value")

        return "value"

    def sanitize_chart_spec(self, spec: Dict[str, Any]) -> Dict[str, Any]:
        """Coerce common LLM-generated VChart spec mistakes into valid shapes."""
        normalized = dict(spec)

        if normalized.get("type") == "radar":
            if normalized.get("xField") and not normalized.get("categoryField"):
                normalized["categoryField"] = normalized.pop("xField")
            if normalized.get("yField") and not normalized.get("valueField"):
                normalized["valueField"] = normalized.pop("yField")

        if normalized.get("type") == "wordCloud":
            if normalized.get("categoryField") and not normalized.get("nameField"):
                normalized["nameField"] = normalized.pop("categoryField")
            if normalized.get("seriesField") and not normalized.get("nameField"):
                normalized["nameField"] = normalized.pop("seriesField")

        if normalized.get("type") == "circularProgress" and not normalized.get("categoryField"):
            normalized["categoryField"] = "_label"
            data = normalized.get("data")
            if isinstance(data, list):
                for dataset in data:
                    if not isinstance(dataset, dict):
                        continue
                    values = dataset.get("values")
                    if isinstance(values, list):
                        dataset["values"] = [
                            {"_label": "progress", **value} if isinstance(value, dict) else value
                            for value in values
                        ]

        if normalized.get("type") == "pie" and normalized.get("isDonut") is True:
            normalized.setdefault("innerRadius", 0.5)
            normalized.setdefault("outerRadius", 0.8)

        if normalized.get("type") == "pie":
            pie = normalized.get("pie")
            if not isinstance(pie, dict):
                pie = {}
            style = pie.get("style")
            if not isinstance(style, dict):
                style = {}
            style.setdefault("fillOpacity", 1)
            style.setdefault("opacity", 1)
            pie["style"] = style
            normalized["pie"] = pie

        if normalized.get("type") == "common":
            data = normalized.get("data")
            if isinstance(data, dict) and isinstance(data.get("values"), list):
                normalized["data"] = [{"id": "source", "values": data["values"]}]
                data = normalized["data"]

            if isinstance(data, list):
                dataset_id_to_index: Dict[str, int] = {}
                for index, dataset in enumerate(data):
                    if isinstance(dataset, dict) and isinstance(dataset.get("id"), str):
                        dataset_id_to_index[str(dataset["id"])] = index

                if isinstance(normalized.get("series"), list):
                    x_field = normalized.get("xField")
                    y_fields = normalized.get("yField")
                    top_level_series_field = normalized.get("seriesField")
                    rewritten_series: List[Dict[str, Any]] = []
                    for index, series_item in enumerate(normalized["series"]):
                        if not isinstance(series_item, dict):
                            continue
                        series_dict = dict(series_item)
                        data_id = series_dict.pop("dataId", None)
                        if "dataIndex" not in series_dict:
                            if isinstance(data_id, str) and data_id in dataset_id_to_index:
                                series_dict["dataIndex"] = dataset_id_to_index[data_id]
                            else:
                                series_dict["dataIndex"] = min(index, max(len(data) - 1, 0))

                        if "xField" not in series_dict and isinstance(x_field, (str, list)):
                            series_dict["xField"] = x_field
                        if "yField" not in series_dict:
                            dataset_index = series_dict.get("dataIndex")
                            dataset = (
                                data[dataset_index]
                                if isinstance(dataset_index, int) and 0 <= dataset_index < len(data)
                                else data[min(index, max(len(data) - 1, 0))]
                            )
                            series_dict["yField"] = self._infer_common_y_field(
                                dataset,
                                x_field=series_dict.get("xField", x_field),
                                y_fields=y_fields,
                                index=index,
                                series_field=series_dict.get("seriesField", top_level_series_field),
                            )
                        rewritten_series.append(series_dict)
                    normalized["series"] = rewritten_series
                    if rewritten_series:
                        normalized["axes"] = self._common_axis_defaults(normalized.get("axes"))
                        normalized.pop("xField", None)
                        normalized.pop("yField", None)
                        normalized.pop("seriesField", None)
                else:
                    x_field = normalized.get("xField")
                    y_fields = normalized.get("yField")
                    if isinstance(x_field, (str, list)):
                        y_field_list = y_fields if isinstance(y_fields, list) else []
                        series = []
                        for index, dataset in enumerate(data):
                            if not isinstance(dataset, dict):
                                continue
                            data_id = str(dataset.get("id") or f"series_{index + 1}")
                            series.append({
                                "type": self._infer_common_series_type(data_id, index),
                                "dataIndex": index,
                                "xField": x_field,
                                "yField": self._infer_common_y_field(
                                    dataset,
                                    x_field=x_field,
                                    y_fields=y_field_list,
                                    index=index,
                                    series_field=normalized.get("seriesField"),
                                ),
                            })
                        if series:
                            normalized["series"] = series
                            normalized["axes"] = self._common_axis_defaults(normalized.get("axes"))
                            normalized.pop("xField", None)
                            normalized.pop("yField", None)
                            normalized.pop("seriesField", None)

        if "title" in normalized:
            title = normalized["title"]
            if isinstance(title, str):
                normalized["title"] = {"text": title, "visible": bool(title)}
            elif isinstance(title, dict) and "text" not in title and "value" in title:
                title_dict = dict(title)
                title_dict["text"] = title_dict.pop("value")
                normalized["title"] = title_dict
        self._normalize_label_text_stroke(normalized)
        return normalized

    def _normalize_label_text_stroke(self, node: Any) -> None:
        if isinstance(node, list):
            for item in node:
                self._normalize_label_text_stroke(item)
            return

        if not isinstance(node, dict):
            return

        for key, value in list(node.items()):
            if key in self._LABELISH_KEYS and isinstance(value, dict):
                self._strip_label_text_stroke(value)
            self._normalize_label_text_stroke(value)

    @staticmethod
    def _strip_label_text_stroke(label_config: Dict[str, Any]) -> None:
        style = label_config.get("style")
        if not isinstance(style, dict):
            style = {}
        style["textStrokeWidth"] = 0
        style["lineWidth"] = 0
        label_config["style"] = style

        text_style = label_config.get("textStyle")
        if isinstance(text_style, dict):
            text_style["textBorderWidth"] = 0
            text_style["textStrokeWidth"] = 0
            label_config["textStyle"] = text_style

        label_config["textBorderWidth"] = 0
        label_config["textStrokeWidth"] = 0

    def _is_supported_chart_spec(self, spec: Dict[str, Any]) -> bool:
        chart_type = spec.get("type")
        return isinstance(chart_type, str) and chart_type in self._SUPPORTED_CHART_TYPES

    def _renderability_reason(self, spec: Dict[str, Any]) -> Optional[str]:
        chart_type = spec.get("type")
        if not isinstance(chart_type, str) or chart_type not in self._SUPPORTED_CHART_TYPES:
            return "unsupported chart type"

        if chart_type == "common":
            data = spec.get("data")
            series = spec.get("series")
            if not isinstance(data, list) or not data:
                return "common chart requires a non-empty data array"
            if not isinstance(series, list) or not series:
                return "common chart requires a non-empty series array"

            data_len = len(data)
            for index, series_item in enumerate(series):
                if not isinstance(series_item, dict):
                    return f"common series {index + 1} is not an object"
                data_index = series_item.get("dataIndex")
                if not isinstance(data_index, int) or not (0 <= data_index < data_len):
                    return f"common series {index + 1} has invalid dataIndex"
                if not isinstance(series_item.get("type"), str):
                    return f"common series {index + 1} is missing type"
                if "xField" not in series_item or "yField" not in series_item:
                    return f"common series {index + 1} is missing xField or yField"

        return None

    @staticmethod
    def _extract_title_text(spec: Dict[str, Any]) -> str:
        title = spec.get("title")
        if isinstance(title, str):
            return title.strip()
        if isinstance(title, dict):
            text = title.get("text")
            if isinstance(text, str):
                return text.strip()
        return ""

    @staticmethod
    def _extract_table_rows(spec: Dict[str, Any]) -> List[Dict[str, Any]]:
        data = spec.get("data")
        datasets: List[Any]
        if isinstance(data, dict):
            datasets = [data]
        elif isinstance(data, list):
            datasets = data
        else:
            datasets = []

        rows: List[Dict[str, Any]] = []
        for dataset in datasets:
            if not isinstance(dataset, dict):
                continue
            values = dataset.get("values")
            if not isinstance(values, list):
                continue
            for value in values:
                if isinstance(value, dict):
                    rows.append(value)
        return rows

    @staticmethod
    def _to_markdown_table(rows: List[Dict[str, Any]], *, max_rows: int = 8) -> Optional[str]:
        if not rows:
            return None
        columns: List[str] = []
        for row in rows:
            for key in row.keys():
                if key not in columns:
                    columns.append(str(key))
        if not columns:
            return None

        header = "| " + " | ".join(columns) + " |"
        separator = "| " + " | ".join(["---"] * len(columns)) + " |"
        body = []
        for row in rows[:max_rows]:
            values = [str(row.get(column, "")) for column in columns]
            body.append("| " + " | ".join(values) + " |")
        return "\n".join([header, separator, *body])

    def _unsupported_chart_markdown(self, spec: Dict[str, Any], *, reason: str) -> str:
        chart_type = spec.get("type") if isinstance(spec.get("type"), str) else "unknown"
        title = self._extract_title_text(spec)
        heading = f"**{title}**\n\n" if title else ""
        summary = (
            f"{heading}_Chart omitted in Feishu: `{chart_type}` is not rendered as a card chart here "
            f"({reason})._"
        )
        table = self._to_markdown_table(self._extract_table_rows(spec))
        if table:
            return f"{summary}\n\n{table}"
        return summary

    def split_card_elements(
        self,
        text: str,
        *,
        aspect_ratio: Optional[str] = None,
        enforce_chart_limit: bool = True,
    ) -> List[Dict[str, Any]]:
        """Split markdown text into alternating markdown and chart card elements."""
        elements: List[Dict[str, Any]] = []
        last_end = 0
        effective_ratio = aspect_ratio or self.chart_aspect_ratio
        chart_count = 0
        for match in self._VCHART_FENCE_RE.finditer(text):
            prose = text[last_end:match.start()].strip()
            if prose:
                elements.append({"tag": "markdown", "content": prose})
            try:
                chart_spec = self.sanitize_chart_spec(json.loads(match.group(1).strip()))
                renderability_reason = self._renderability_reason(chart_spec)
                if renderability_reason is not None:
                    logger.info(
                        "[Feishu] Non-renderable chart spec %r downgraded to markdown: %s",
                        chart_spec.get("type"),
                        renderability_reason,
                    )
                    elements.append({
                        "tag": "markdown",
                        "content": self._unsupported_chart_markdown(
                            chart_spec,
                            reason=renderability_reason,
                        ),
                    })
                elif enforce_chart_limit and chart_count >= self.max_chart_elements:
                    logger.info(
                        "[Feishu] Chart count exceeded limit (%s); downgraded to markdown",
                        self.max_chart_elements,
                    )
                    elements.append({
                        "tag": "markdown",
                        "content": self._unsupported_chart_markdown(
                            chart_spec,
                            reason=f"card supports at most {self.max_chart_elements} charts",
                        ),
                    })
                else:
                    chart_count += 1
                    elements.append({
                        "tag": "chart",
                        "aspect_ratio": effective_ratio,
                        "chart_spec": chart_spec,
                    })
            except Exception:
                logger.warning("[Feishu] vchart block JSON parse failed — rendering as code block")
                elements.append({"tag": "markdown", "content": match.group(0)})
            last_end = match.end()
        trailing = text[last_end:].strip()
        if trailing:
            elements.append({"tag": "markdown", "content": trailing})
        if not elements:
            elements.append({"tag": "markdown", "content": " "})
        return elements

    def chunk_card_elements(
        self,
        elements: List[Dict[str, Any]],
        *,
        max_chart_elements: Optional[int] = None,
    ) -> List[List[Dict[str, Any]]]:
        """Split parsed card elements so each chart renders on its own Feishu card."""
        if max_chart_elements is not None and max_chart_elements <= 0:
            return [elements] if elements else [[{"tag": "markdown", "content": " "}]]
        if not elements:
            return [[{"tag": "markdown", "content": " "}]]

        batches: List[List[Dict[str, Any]]] = []
        leading_markdown: List[Dict[str, Any]] = []
        inter_chart_markdown: List[Dict[str, Any]] = []
        current_batch: Optional[List[Dict[str, Any]]] = None

        for element in elements:
            if element.get("tag") != "chart":
                if current_batch is None:
                    leading_markdown.append(element)
                else:
                    inter_chart_markdown.append(element)
                continue

            if current_batch is not None:
                batches.append(current_batch)
                current_batch = inter_chart_markdown.copy()
                inter_chart_markdown = []
            else:
                current_batch = leading_markdown.copy()
                leading_markdown = []

            current_batch.append(element)

        if current_batch is not None:
            if inter_chart_markdown:
                current_batch.extend(inter_chart_markdown)
            batches.append(current_batch)
        elif leading_markdown:
            batches.append(leading_markdown)

        return batches or [[{"tag": "markdown", "content": " "}]]

    def build_card_payload_from_elements(
        self,
        title: str,
        elements: List[Dict[str, Any]],
        *,
        template: str = "blue",
    ) -> str:
        card: Dict[str, Any] = {
            "schema": "2.0",
            "config": {"width_mode": "fill"},
            "header": {
                "title": {"tag": "plain_text", "content": title},
                "template": template,
            },
            "body": {"elements": elements},
        }
        return json.dumps(card, ensure_ascii=False)

    def build_card_payload(
        self,
        title: str,
        markdown_body: str,
        *,
        template: str = "blue",
        actions: Optional[List[Dict[str, Any]]] = None,
    ) -> str:
        elements = self.split_card_elements(markdown_body)
        if actions:
            elements.append({"tag": "action", "actions": actions})
        return self.build_card_payload_from_elements(title, elements, template=template)

    def build_streaming_card_payload(self, title: str, markdown_body: str) -> str:
        card: Dict[str, Any] = {
            "schema": "2.0",
            "config": {
                "width_mode": "fill",
                "update_multi": True,
                "streaming_mode": True,
                "summary": {"content": "[Generating...]"},
                "streaming_config": {
                    "print_frequency_ms": {"default": 70, "android": 70, "ios": 70, "pc": 70},
                    "print_step": {"default": 1, "android": 1, "ios": 1, "pc": 1},
                    "print_strategy": "fast",
                },
            },
            "header": {
                "title": {"tag": "plain_text", "content": title},
                "template": "blue",
            },
            "body": {
                "elements": [
                    {
                        "tag": "markdown",
                        "content": markdown_body,
                        "element_id": self.stream_element_id,
                    }
                ]
            },
        }
        return json.dumps(card, ensure_ascii=False)

    def render_stream_body(self, text: str, *, status: Optional[str] = None, error: Optional[str] = None) -> str:
        rendered_text = str(text or "").strip()
        rendered_status = str(status or "").strip()
        rendered_error = str(error or "").strip()

        parts: List[str] = []
        if rendered_text:
            parts.append(rendered_text)
        elif rendered_status:
            parts.append(f"_{rendered_status}_")
        else:
            parts.append("_Thinking..._")

        if rendered_error:
            parts.extend(["", "---", "", f"**Error:** {rendered_error}"])

        return "\n".join(parts)

    def has_chart_elements(self, text: str) -> bool:
        return bool(self._VCHART_FENCE_RE.search(text))

    def strip_chart_fences(self, text: str) -> str:
        return self._VCHART_FENCE_RE.sub("", text).strip()
