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

    _VCHART_FENCE_RE = re.compile(r"```(?:vchart|chart)\s*\n(.*?)\n\s*```", re.DOTALL)

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

        if normalized.get("type") == "common" and not isinstance(normalized.get("series"), list):
            data = normalized.get("data")
            x_field = normalized.get("xField")
            y_fields = normalized.get("yField")
            if isinstance(data, list) and isinstance(x_field, str):
                y_field_list = y_fields if isinstance(y_fields, list) else []
                series: List[Dict[str, Any]] = []
                for index, dataset in enumerate(data):
                    if not isinstance(dataset, dict):
                        continue
                    data_id = str(dataset.get("id") or f"series_{index + 1}")
                    values = dataset.get("values")
                    first_value = values[0] if isinstance(values, list) and values else {}
                    inferred_y_field = None
                    if index < len(y_field_list) and isinstance(y_field_list[index], str):
                        inferred_y_field = y_field_list[index]
                    elif isinstance(first_value, dict):
                        inferred_y_field = next((k for k in first_value.keys() if k != x_field), "value")
                    else:
                        inferred_y_field = "value"
                    series.append({
                        "type": self._infer_common_series_type(data_id, index),
                        "dataId": data_id,
                        "xField": x_field,
                        "yField": inferred_y_field,
                    })
                if series:
                    normalized["series"] = series
                    if not isinstance(normalized.get("axes"), list) or not normalized.get("axes"):
                        normalized["axes"] = [
                            {"orient": "bottom", "type": "band"},
                            {"orient": "left", "type": "linear"},
                        ]
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
        return normalized

    def split_card_elements(self, text: str, *, aspect_ratio: Optional[str] = None) -> List[Dict[str, Any]]:
        """Split markdown text into alternating markdown and chart card elements."""
        elements: List[Dict[str, Any]] = []
        last_end = 0
        effective_ratio = aspect_ratio or self.chart_aspect_ratio
        for match in self._VCHART_FENCE_RE.finditer(text):
            prose = text[last_end:match.start()].strip()
            if prose:
                elements.append({"tag": "markdown", "content": prose})
            try:
                chart_spec = self.sanitize_chart_spec(json.loads(match.group(1).strip()))
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
