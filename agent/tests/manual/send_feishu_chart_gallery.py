"""Send the verified 13-chart Feishu Card v2 smoke gallery.

This is a manual integration harness, not a pytest test. It sends three
interactive cards to a Feishu chat because Feishu recommends a maximum of five
chart components per card. The payload shape matches the gallery that was
verified in the live Feishu web client.

Usage:
    python agent/tests/manual/send_feishu_chart_gallery.py
    python agent/tests/manual/send_feishu_chart_gallery.py --chat-id oc_xxx
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List

from dotenv import load_dotenv


AGENT_ROOT = Path(__file__).resolve().parents[2]
if str(AGENT_ROOT) not in sys.path:
    sys.path.insert(0, str(AGENT_ROOT))

load_dotenv(AGENT_ROOT / ".env")

import api_server  # noqa: E402


@dataclass(frozen=True)
class ChartCase:
    label: str
    chart_type: str
    spec: Dict[str, Any]


def _line_values() -> List[Dict[str, Any]]:
    return [
        {"time": "02:00", "value": 8},
        {"time": "04:00", "value": 9},
        {"time": "06:00", "value": 11},
        {"time": "08:00", "value": 14},
        {"time": "10:00", "value": 16},
        {"time": "12:00", "value": 17},
        {"time": "14:00", "value": 17},
        {"time": "16:00", "value": 16},
        {"time": "18:00", "value": 15},
    ]


def _bar_values() -> List[Dict[str, Any]]:
    return [
        {"type": "Autoc", "year": "1930", "value": 129},
        {"type": "Autoc", "year": "1940", "value": 133},
        {"type": "Autoc", "year": "1950", "value": 130},
        {"type": "Autoc", "year": "1960", "value": 126},
        {"type": "Democ", "year": "1930", "value": 22},
        {"type": "Democ", "year": "1940", "value": 13},
        {"type": "Democ", "year": "1950", "value": 25},
        {"type": "Democ", "year": "1960", "value": 29},
    ]


def _horizontal_bar_values() -> List[Dict[str, Any]]:
    return [
        {"name": "Apple", "value": 214480},
        {"name": "Google", "value": 155506},
        {"name": "Amazon", "value": 100764},
        {"name": "Microsoft", "value": 92715},
        {"name": "Samsung", "value": 59890},
    ]


def _pie_values() -> List[Dict[str, Any]]:
    return [
        {"type": "S1", "value": 340},
        {"type": "S2", "value": 170},
        {"type": "S3", "value": 150},
        {"type": "S4", "value": 120},
        {"type": "S5", "value": 100},
    ]


def _donut_values() -> List[Dict[str, Any]]:
    return [
        {"type": "oxygen", "value": 46.60},
        {"type": "silicon", "value": 27.72},
        {"type": "aluminum", "value": 8.13},
        {"type": "iron", "value": 5.00},
        {"type": "calcium", "value": 3.63},
        {"type": "potassium", "value": 2.59},
        {"type": "others", "value": 3.50},
    ]


def _combo_bar_values() -> List[Dict[str, Any]]:
    return [
        {"x": "周一", "type": "早餐", "y": 15},
        {"x": "周一", "type": "午餐", "y": 25},
        {"x": "周二", "type": "早餐", "y": 12},
        {"x": "周二", "type": "午餐", "y": 30},
        {"x": "周三", "type": "早餐", "y": 15},
        {"x": "周三", "type": "午餐", "y": 24},
    ]


def _combo_line_values() -> List[Dict[str, Any]]:
    return [
        {"x": "周一", "type": "饮料", "y": 22},
        {"x": "周二", "type": "饮料", "y": 43},
        {"x": "周三", "type": "饮料", "y": 33},
        {"x": "周四", "type": "饮料", "y": 22},
        {"x": "周五", "type": "饮料", "y": 10},
    ]


def _funnel_values() -> List[Dict[str, Any]]:
    return [
        {"name": "Sent", "value": 5676},
        {"name": "Viewed", "value": 3872},
        {"name": "Clicked", "value": 1668},
        {"name": "Purchased", "value": 565},
    ]


def _scatter_values() -> List[Dict[str, Any]]:
    return [
        {"name": "vw rabbit", "milesPerGallon": 29, "horsepower": 70},
        {"name": "honda civic", "milesPerGallon": 33, "horsepower": 53},
        {"name": "dodge aspen se", "milesPerGallon": 20, "horsepower": 100},
        {"name": "buick opel", "milesPerGallon": 30, "horsepower": 80},
        {"name": "chevrolet caprice", "milesPerGallon": 17.5, "horsepower": 145},
        {"name": "toyota corolla", "milesPerGallon": 32.2, "horsepower": 75},
    ]


def _radar_values() -> List[Dict[str, Any]]:
    return [
        {"key": "力量", "value": 5},
        {"key": "速度", "value": 5},
        {"key": "射程", "value": 3},
        {"key": "持续", "value": 5},
        {"key": "精密", "value": 5},
        {"key": "成长", "value": 5},
    ]


def _linear_progress_values() -> List[Dict[str, Any]]:
    return [
        {"type": "Tradition Industries", "value": 0.795, "text": "79.5%"},
        {"type": "Business Companies", "value": 0.25, "text": "25%"},
    ]


def _circular_progress_values() -> List[Dict[str, Any]]:
    return [
        {"type": "Industries", "value": 0.795, "text": "79.5%"},
        {"type": "Companies", "value": 0.25, "text": "25%"},
    ]


def _wordcloud_values() -> List[Dict[str, Any]]:
    return [
        {"challenge_name": "宅家dou剧场", "sum_count": 128},
        {"challenge_name": "我的观影报告", "sum_count": 103},
        {"challenge_name": "抖瓜小助手", "sum_count": 76},
        {"challenge_name": "搞笑", "sum_count": 70},
        {"challenge_name": "我要上热门", "sum_count": 69},
        {"challenge_name": "正能量", "sum_count": 52},
    ]


def build_chart_cases() -> List[ChartCase]:
    return [
        ChartCase(
            "1. Line",
            "line",
            {
                "type": "line",
                "title": {"text": "折线图"},
                "data": {"values": _line_values()},
                "xField": "time",
                "yField": "value",
            },
        ),
        ChartCase(
            "2. Area",
            "area",
            {
                "type": "area",
                "title": {"text": "面积图"},
                "data": {"values": _line_values()},
                "xField": "time",
                "yField": "value",
            },
        ),
        ChartCase(
            "3. Bar",
            "bar",
            {
                "type": "bar",
                "title": {"text": "柱状图"},
                "data": {"values": _bar_values()},
                "xField": ["year", "type"],
                "yField": "value",
                "seriesField": "type",
                "legends": {"visible": True, "orient": "bottom"},
            },
        ),
        ChartCase(
            "4. Horizontal Bar",
            "bar",
            {
                "type": "bar",
                "title": {"text": "条形图"},
                "data": {"values": _horizontal_bar_values()},
                "direction": "horizontal",
                "xField": "value",
                "yField": "name",
            },
        ),
        ChartCase(
            "5. Doughnut",
            "pie",
            {
                "type": "pie",
                "title": {"text": "环图"},
                "data": {"values": _donut_values()},
                "valueField": "value",
                "categoryField": "type",
                "outerRadius": 0.9,
                "innerRadius": 0.3,
                "label": {"visible": True},
                "legends": {"visible": True},
            },
        ),
        ChartCase(
            "6. Pie",
            "pie",
            {
                "type": "pie",
                "title": {"text": "饼图"},
                "data": {"values": _pie_values()},
                "valueField": "value",
                "categoryField": "type",
                "outerRadius": 0.9,
                "legends": {"visible": True, "orient": "right"},
                "padding": {"left": 10, "top": 10, "bottom": 5, "right": 0},
                "label": {"visible": True},
            },
        ),
        ChartCase(
            "7. Common Combo",
            "common",
            {
                "type": "common",
                "title": {"text": "组合图"},
                "data": [
                    {"id": "combo_bar", "values": _combo_bar_values()},
                    {"id": "combo_line", "values": _combo_line_values()},
                ],
                "series": [
                    {
                        "type": "bar",
                        "dataIndex": 0,
                        "label": {"visible": True},
                        "seriesField": "type",
                        "xField": ["x", "type"],
                        "yField": "y",
                    },
                    {
                        "type": "line",
                        "dataIndex": 1,
                        "label": {"visible": True},
                        "seriesField": "type",
                        "xField": "x",
                        "yField": "y",
                    },
                ],
                "axes": [{"orient": "bottom"}, {"orient": "left"}],
                "legends": {"visible": True, "orient": "bottom"},
            },
        ),
        ChartCase(
            "8. Funnel",
            "funnel",
            {
                "type": "funnel",
                "title": {"text": "漏斗图"},
                "data": {"values": _funnel_values()},
                "categoryField": "name",
                "valueField": "value",
                "isTransform": True,
                "label": {"visible": True},
                "transformLabel": {"visible": True},
                "outerLabel": {"visible": False},
            },
        ),
        ChartCase(
            "9. Scatter",
            "scatter",
            {
                "type": "scatter",
                "title": {"text": "散点图"},
                "data": {"values": _scatter_values()},
                "xField": "milesPerGallon",
                "yField": "horsepower",
                "axes": [
                    {"title": {"visible": True, "text": "Horse Power"}, "orient": "left", "range": {"min": 0}, "type": "linear"},
                    {"title": {"visible": True, "text": "Miles Per Gallon"}, "orient": "bottom", "range": {"min": 10}, "type": "linear"},
                ],
            },
        ),
        ChartCase(
            "10. Radar",
            "radar",
            {
                "type": "radar",
                "title": {"text": "雷达图"},
                "data": {"values": _radar_values()},
                "categoryField": "key",
                "valueField": "value",
                "area": {"visible": True},
                "outerRadius": 0.8,
                "axes": [{"orient": "radius", "label": {"visible": True, "style": {"textAlign": "center"}}}],
            },
        ),
        ChartCase(
            "11. Linear Progress",
            "linearProgress",
            {
                "type": "linearProgress",
                "title": {"text": "条形进度图"},
                "data": {"values": _linear_progress_values()},
                "direction": "horizontal",
                "xField": "value",
                "yField": "type",
                "seriesField": "type",
                "axes": [{"orient": "left", "domainLine": {"visible": False}}],
            },
        ),
        ChartCase(
            "12. Circular Progress",
            "circularProgress",
            {
                "type": "circularProgress",
                "title": {"text": "环形进度图"},
                "data": {"values": _circular_progress_values()},
                "valueField": "value",
                "categoryField": "type",
                "seriesField": "type",
                "radius": 0.7,
                "innerRadius": 0.4,
                "cornerRadius": 20,
                "progress": {"style": {"innerPadding": 5, "outerPadding": 5}},
                "indicator": {
                    "visible": True,
                    "trigger": "hover",
                    "title": {"visible": True, "field": "type", "autoLimit": True},
                    "content": [{"visible": True, "field": "text"}],
                },
                "legends": {"visible": True, "orient": "bottom", "title": {"visible": False}},
            },
        ),
        ChartCase(
            "13. Word Cloud",
            "wordCloud",
            {
                "type": "wordCloud",
                "title": {"text": "词云"},
                "data": {"values": _wordcloud_values()},
                "nameField": "challenge_name",
                "valueField": "sum_count",
                "seriesField": "challenge_name",
            },
        ),
    ]


def chunked(items: Iterable[ChartCase], size: int) -> List[List[ChartCase]]:
    items = list(items)
    return [items[index:index + size] for index in range(0, len(items), size)]


async def resolve_default_chat_id() -> str:
    data = await api_server._feishu_openapi_request("GET", "/open-apis/im/v1/chats?page_size=20", {})
    items = data.get("items") or []
    if not items:
        raise RuntimeError("No Feishu chats available to this app")
    return str(items[0].get("chat_id") or "")


async def send_gallery(chat_id: str) -> List[Dict[str, str]]:
    adapter = api_server._FEISHU_VISUALIZATION_ADAPTER
    batches = chunked(build_chart_cases(), 5)
    sent: List[Dict[str, str]] = []

    for batch_index, batch in enumerate(batches, start=1):
        elements: List[Dict[str, Any]] = [
            {
                "tag": "markdown",
                "content": (
                    f"**Feishu Chart Smoke Test {batch_index}/{len(batches)}**\n\n"
                    "Source: Feishu chart component documentation sample-style data.\n"
                    "Expected result: every labeled block below renders as a visual chart, not plain text."
                ),
            }
        ]

        for case in batch:
            elements.append({
                "tag": "markdown",
                "content": f"**{case.label}**\nExpected chart type: `{case.chart_type}`",
            })
            elements.append({
                "tag": "chart",
                "aspect_ratio": "4:3",
                "chart_spec": adapter.sanitize_chart_spec(case.spec),
            })

        create_data = await api_server._feishu_openapi_request(
            "POST",
            "/open-apis/cardkit/v1/cards",
            {
                "type": "card_json",
                "data": adapter.build_card_payload_from_elements(
                    f"Feishu Chart Gallery {batch_index}/{len(batches)}",
                    elements,
                    template="blue",
                ),
            },
        )
        card_id = str(create_data.get("card_id") or "")
        message_data = await api_server._feishu_openapi_request(
            "POST",
            "/open-apis/im/v1/messages?receive_id_type=chat_id",
            {
                "receive_id": chat_id,
                "msg_type": "interactive",
                "content": json.dumps({"type": "card", "data": {"card_id": card_id}}, ensure_ascii=False),
            },
        )
        sent.append(
            {
                "batch": str(batch_index),
                "card_id": card_id,
                "message_id": str(message_data.get("message_id") or ""),
            }
        )
    return sent


async def main() -> None:
    parser = argparse.ArgumentParser(description="Send the verified Feishu 13-chart smoke gallery")
    parser.add_argument("--chat-id", help="Explicit Feishu chat_id to send to")
    args = parser.parse_args()

    chat_id = args.chat_id or await resolve_default_chat_id()
    results = await send_gallery(chat_id)
    print(json.dumps({"chat_id": chat_id, "sent": results}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
