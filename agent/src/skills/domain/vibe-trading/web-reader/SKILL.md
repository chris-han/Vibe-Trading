---
name: web-reader
description: Read web pages, articles, and document links by converting URLs into Markdown text. Use the `read_url` tool directly, without bash.
---
# Web Reading

## Purpose

Converts any URL into clean Markdown text, removing ads, navigation, styling, and other distractions. Suitable for:
- Reading API documentation (`tushare`, `OKX`, `yfinance`, and similar)
- Reading technical articles and blogs
- Retrieving research reports and announcements
- Reading GitHub README / Wiki pages

## Usage

If the exact source URL is not known yet, use the Hermes `web_search` tool first to find the canonical page, then call `read_url` on that result. Do not rely on provider-native search or model-browsing features when the app already exposes `web_search`.

**Call the `read_url` tool directly (do not use bash + requests, call the tool directly):**

```
read_url(url="https://tushare.pro/document/2?doc_id=27")
```

Returns JSON:
```json
{
  "status": "ok",
  "title": "Page title",
  "url": "Original URL",
  "content": "Page content in Markdown format",
  "length": 12345
}
```

## Notes

- Content longer than 8000 characters will be truncated, with the total length noted at the end
- Some websites may block Jina Reader (returning HTTP 451). In that case, fall back to bash + requests
- Dynamically rendered SPA pages may return only skeleton HTML
- Chinese content is supported normally

## Common Usage

### Find Then Read
```
web_search(query="latest FOMC meeting minutes Federal Reserve")
read_url(url="https://www.federalreserve.gov/monetarypolicy/fomcminutes20260318.htm")
```

### Read API Documentation
```
read_url(url="https://tushare.pro/document/2?doc_id=27")
```

### Read Technical Articles
```
read_url(url="https://blog.example.com/quantitative-trading-guide")
```

### Retrieve GitHub Project Information
```
read_url(url="https://github.com/PaddlePaddle/PaddleOCR")
```
