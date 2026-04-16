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

    def sanitize_chart_spec(self, spec: Dict[str, Any]) -> Dict[str, Any]:
        """Coerce common LLM-generated VChart spec mistakes into valid shapes."""
        normalized = dict(spec)
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
