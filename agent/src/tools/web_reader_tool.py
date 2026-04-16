"""Web reader tool with Jina-first fetching and a direct-request fallback."""

from __future__ import annotations

import json
import os
import re
from html import unescape
from urllib.parse import urlparse

import requests

from .base import BaseTool

_JINA_PREFIX = "https://r.jina.ai/"
_TIMEOUT = 30
_JINA_TIMEOUT = 12
_MAX_LENGTH = 8000
_DEFAULT_USER_AGENT = os.getenv(
    "WEB_READER_USER_AGENT",
    "Vibe Trading Research bot@example.com",
)


def _get_timeout_seconds() -> int:
    raw = (os.getenv("WEB_READER_TIMEOUT_SECONDS") or "").strip()
    if raw:
        try:
            return max(5, min(int(raw), 120))
        except ValueError:
            pass
    return _TIMEOUT


def _extract_title(text: str) -> str:
    for line in text.split("\n"):
        if line.startswith("Title:"):
            return line[6:].strip()

    match = re.search(r"<title[^>]*>(.*?)</title>", text, flags=re.IGNORECASE | re.DOTALL)
    if match:
        return unescape(match.group(1).strip())
    return ""


def _truncate_text(text: str) -> str:
    if len(text) <= _MAX_LENGTH:
        return text
    return text[:_MAX_LENGTH] + f"\n\n... (truncated, total {len(text)} chars)"


def _direct_headers(url: str) -> dict[str, str]:
    hostname = (urlparse(url).hostname or "").lower()
    headers = {
        "User-Agent": _DEFAULT_USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }
    if hostname.endswith("sec.gov"):
        headers["Accept-Encoding"] = "gzip, deflate"
    return headers


def _success_payload(url: str, text: str, source: str) -> str:
    return json.dumps(
        {
            "status": "ok",
            "title": _extract_title(text),
            "url": url,
            "content": _truncate_text(text),
            "length": len(text),
            "source": source,
        },
        ensure_ascii=False,
    )


def read_url(url: str) -> str:
    """Fetch web page content via Jina Reader, then fall back to a direct GET.

    Args:
        url: Target URL.

    Returns:
        JSON-formatted result containing title, content, and url.
    """
    timeout = _get_timeout_seconds()
    jina_timeout = min(timeout, _JINA_TIMEOUT)
    fallback_reason = ""

    try:
        resp = requests.get(
            f"{_JINA_PREFIX}{url}",
            headers={"Accept": "text/markdown"},
            timeout=jina_timeout,
        )
        if resp.status_code == 200:
            return _success_payload(url, resp.text, source="jina")
        fallback_reason = f"Jina Reader returned {resp.status_code}: {resp.text[:500]}"
    except requests.Timeout:
        fallback_reason = f"Jina Reader timed out ({jina_timeout}s)"
    except Exception as exc:
        fallback_reason = f"Jina Reader failed: {exc}"

    try:
        resp = requests.get(
            url,
            headers=_direct_headers(url),
            timeout=timeout,
        )
        if resp.status_code != 200:
            return json.dumps(
                {
                    "status": "error",
                    "error": f"{fallback_reason}; direct fetch returned {resp.status_code}: {resp.text[:500]}",
                },
                ensure_ascii=False,
            )
        return _success_payload(url, resp.text, source="direct")
    except requests.Timeout:
        return json.dumps(
            {
                "status": "error",
                "error": f"{fallback_reason}; direct fetch timed out ({timeout}s)",
            },
            ensure_ascii=False,
        )
    except Exception as exc:
        return json.dumps(
            {
                "status": "error",
                "error": f"{fallback_reason}; direct fetch failed: {exc}",
            },
            ensure_ascii=False,
        )


class WebReaderTool(BaseTool):
    """Web reader tool."""

    name = "read_url"
    description = "Fetch web page content: provide a URL and receive the page as Markdown text. Useful for reading docs, articles, API references, etc."
    parameters = {
        "type": "object",
        "properties": {
            "url": {"type": "string", "description": "URL of the web page to read"},
        },
        "required": ["url"],
    }
    repeatable = True

    def execute(self, **kwargs) -> str:
        """Fetch web page."""
        return read_url(kwargs["url"])
