from __future__ import annotations

import json

import requests

from src.tools import web_reader_tool


class _FakeResponse:
    def __init__(self, status_code: int, text: str):
        self.status_code = status_code
        self.text = text


def test_read_url_falls_back_to_direct_fetch_when_jina_times_out(monkeypatch):
    calls: list[tuple[str, dict | None, object]] = []

    def fake_get(url, headers=None, timeout=None):
        calls.append((url, headers, timeout))
        if url.startswith(web_reader_tool._JINA_PREFIX):
            raise requests.Timeout("jina timeout")
        return _FakeResponse(
            200,
            "<html><head><title>EDGAR Search Results</title></head><body>NVDA filings</body></html>",
        )

    monkeypatch.setattr(web_reader_tool.requests, "get", fake_get)

    result = json.loads(
        web_reader_tool.read_url(
            "https://www.sec.gov/cgi-bin/browse-edgar?CIK=NVDA&owner=exclude&action=getcompany"
        )
    )

    assert result["status"] == "ok"
    assert "EDGAR Search Results" in result["title"]
    assert "NVDA filings" in result["content"]
    assert len(calls) == 2
    assert calls[1][0].startswith("https://www.sec.gov/")
    assert calls[1][1]["User-Agent"]
