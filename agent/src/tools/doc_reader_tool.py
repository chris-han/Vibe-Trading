"""Document reader tool: PDF extraction with OCR fallback and progressive sampling."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .base import BaseTool

_MAX_CHARS = 15000  # truncation threshold
_MIN_TEXT_PER_PAGE = 50  # pages with fewer chars are treated as image pages and fall back to OCR
_AUTO_PROGRESSIVE_PAGE_THRESHOLD = 25
_DEFAULT_PROGRESSIVE_WINDOW_SIZE = 2
_DEFAULT_PROGRESSIVE_MAX_WINDOWS = 6
_ocr_engine = None

_HEADING_PATTERNS: tuple[tuple[str, str], ...] = (
    ("risk_factors", r"\brisk factors?\b"),
    ("md_and_a", r"management(?:'s)? discussion and analysis|md&a"),
    ("financial_statements", r"\bfinancial statements?\b|balance sheets?|income statements?|cash flows?"),
    ("forward_looking", r"forward-looking statements?"),
    ("liquidity", r"\bliquidity and capital resources\b"),
)

_BACKEND_DIR = Path(__file__).resolve().parents[2]
_UPLOADS_DIR = _BACKEND_DIR / "uploads"


def _get_ocr():
    """Lazily load the RapidOCR engine (first call takes ~1-2s)."""
    global _ocr_engine
    if _ocr_engine is None:
        from rapidocr_onnxruntime import RapidOCR
        _ocr_engine = RapidOCR()
    return _ocr_engine


def _ocr_page(doc, page_idx: int) -> str:
    """Render a PDF page to an image and run OCR on it.

    Args:
        doc: pypdfium2 PdfDocument object.
        page_idx: Zero-based page index.

    Returns:
        OCR-extracted text for the page.
    """
    import numpy as np

    page = doc[page_idx]
    bitmap = page.render(scale=300 / 72)
    img = bitmap.to_numpy()

    ocr = _get_ocr()
    result, _ = ocr(img)
    if not result:
        return ""
    # result is list of [bbox, text, confidence]
    lines = [item[1] for item in result]
    return "\n".join(lines)


def _extract_page_text(doc, page_idx: int) -> tuple[str, bool]:
    """Return page text and whether OCR was used."""
    page = doc[page_idx]
    text = page.get_textpage().get_text_range().strip()
    if len(text) >= _MIN_TEXT_PER_PAGE:
        return text, False

    ocr_text = _ocr_page(doc, page_idx)
    if ocr_text.strip():
        return ocr_text, True
    return text, False


def _extract_page_block(doc, page_idx: int) -> tuple[str, bool]:
    """Return a page block with marker and OCR state."""
    text, used_ocr = _extract_page_text(doc, page_idx)
    if not text:
        return "", used_ocr
    suffix = " [OCR]" if used_ocr else ""
    return f"--- Page {page_idx + 1}{suffix} ---\n{text}", used_ocr


def _extract_range(doc, start_idx: int, end_idx: int, total_pages: int) -> dict[str, Any]:
    """Extract a closed-open page range and return structured metadata."""
    texts: list[str] = []
    ocr_pages = 0
    heading_hits: dict[str, list[int]] = {name: [] for name, _ in _HEADING_PATTERNS}

    for i in range(start_idx, min(end_idx, total_pages)):
        block, used_ocr = _extract_page_block(doc, i)
        if not block:
            continue
        texts.append(block)
        if used_ocr:
            ocr_pages += 1
        lower = block.lower()
        for name, pattern in _HEADING_PATTERNS:
            if re.search(pattern, lower):
                heading_hits[name].append(i + 1)

    text = "\n\n".join(texts)
    return {
        "page_start": start_idx + 1,
        "page_end": min(end_idx, total_pages),
        "pages": f"{start_idx + 1}-{min(end_idx, total_pages)}",
        "page_count": max(0, min(end_idx, total_pages) - start_idx),
        "char_count": len(text),
        "ocr_pages": ocr_pages,
        "heading_hits": {k: v for k, v in heading_hits.items() if v},
        "text": text,
    }


def _build_progressive_windows(total_pages: int, window_size: int, max_windows: int) -> list[tuple[int, int]]:
    """Create page windows that sample the head, middle, and tail of a document."""
    if total_pages <= 0:
        return []

    window_size = max(1, window_size)
    max_windows = max(1, max_windows)

    if total_pages <= window_size * max_windows:
        starts = list(range(0, total_pages, window_size))
    else:
        last_start = max(total_pages - window_size, 0)
        starts = [0]
        if total_pages > window_size:
            starts.append(min(window_size, last_start))

        remaining = max_windows - len(starts) - 1
        if remaining > 0:
            for i in range(1, remaining + 1):
                frac = i / (remaining + 1)
                starts.append(int(round(frac * last_start)))
        starts.append(last_start)

    normalized = sorted(set(max(0, min(start, max(total_pages - window_size, 0))) for start in starts))
    windows = [(start, min(start + window_size, total_pages)) for start in normalized]
    return windows[:max_windows]


def _truncate_text(text: str, max_chars: int) -> tuple[str, bool]:
    """Truncate text at max_chars and report whether truncation happened."""
    if len(text) <= max_chars:
        return text, False
    return text[:max_chars] + f"\n\n... (truncated, total {len(text)} chars)", True


def _resolve_pdf_path(file_path: str) -> Path:
    """Resolve a PDF path against common workspace and upload locations.

    The tool receives either an absolute path or a path relative to the
    current workspace. For uploaded PDFs, users often refer to the original
    filename or a path under ``uploads/`` even when the runtime stores files
    under a session-scoped ``sessions/<session_id>/uploads`` directory.
    """
    raw_path = Path(file_path).expanduser()
    candidates: list[Path] = []

    if raw_path.is_absolute():
        candidates.append(raw_path)
    else:
        session_matches = sorted((_BACKEND_DIR / "sessions").glob(f"*/uploads/{raw_path.name}"))
        candidates.extend(
            [
                Path.cwd() / raw_path,
                Path.cwd() / "agent" / raw_path,
                Path.cwd() / "agent" / "uploads" / raw_path.name,
                Path.cwd() / "uploads" / raw_path.name,
                _BACKEND_DIR / raw_path,
                _UPLOADS_DIR / raw_path.name,
                *session_matches,
            ]
        )

    seen: set[str] = set()
    for candidate in candidates:
        try:
            resolved = candidate.resolve()
        except FileNotFoundError:
            resolved = candidate
        key = str(resolved)
        if key in seen:
            continue
        seen.add(key)
        if resolved.exists():
            return resolved

    return raw_path


def read_document(
    file_path: str,
    pages: str = "",
    mode: str = "full",
    window_size: int = _DEFAULT_PROGRESSIVE_WINDOW_SIZE,
    max_windows: int = _DEFAULT_PROGRESSIVE_MAX_WINDOWS,
) -> str:
    """Extract text from a PDF document, falling back to OCR for image pages.

    Args:
        file_path: Absolute path to the PDF file.
        pages: Page range (e.g. "1-10", "5", "1,3,5-8"); empty means all pages.
        mode: `full`, `progressive`, or `auto`.
        window_size: Pages per sampled window in progressive mode.
        max_windows: Max sampled windows in progressive mode.

    Returns:
        JSON-formatted result.
    """
    path = _resolve_pdf_path(file_path)
    if not path.exists():
        return json.dumps({"status": "error", "error": f"File not found: {file_path}"}, ensure_ascii=False)
    if path.suffix.lower() != ".pdf":
        return json.dumps({"status": "error", "error": f"Only PDF supported, got: {path.suffix}"}, ensure_ascii=False)

    try:
        import pypdfium2 as pdfium

        doc = pdfium.PdfDocument(str(path))
        total_pages = len(doc)
        normalized_mode = (mode or "full").strip().lower()
        if normalized_mode not in {"full", "progressive", "auto"}:
            doc.close()
            return json.dumps({"status": "error", "error": f"Unsupported mode: {mode}"}, ensure_ascii=False)

        if pages.strip():
            target_pages = _parse_pages(pages, total_pages)
            texts = []
            ocr_pages = 0
            for i in target_pages:
                if 0 <= i < total_pages:
                    block, used_ocr = _extract_page_block(doc, i)
                    if block:
                        texts.append(block)
                    if used_ocr:
                        ocr_pages += 1

            doc.close()
            full_text = "\n\n".join(texts)
            truncated_text, truncated = _truncate_text(full_text, _MAX_CHARS)
            return json.dumps({
                "status": "ok",
                "file": path.name,
                "mode": "full",
                "total_pages": total_pages,
                "pages_read": len(target_pages),
                "ocr_pages": ocr_pages,
                "char_count": len(full_text),
                "truncated": truncated,
                "text": truncated_text,
            }, ensure_ascii=False)

        effective_mode = normalized_mode
        if effective_mode == "auto":
            effective_mode = "progressive" if total_pages > _AUTO_PROGRESSIVE_PAGE_THRESHOLD else "full"

        if effective_mode == "full":
            texts = []
            ocr_pages = 0
            for i in range(total_pages):
                block, used_ocr = _extract_page_block(doc, i)
                if block:
                    texts.append(block)
                if used_ocr:
                    ocr_pages += 1

            doc.close()
            full_text = "\n\n".join(texts)
            truncated_text, truncated = _truncate_text(full_text, _MAX_CHARS)
            return json.dumps({
                "status": "ok",
                "file": path.name,
                "mode": "full",
                "total_pages": total_pages,
                "pages_read": total_pages,
                "ocr_pages": ocr_pages,
                "char_count": len(full_text),
                "truncated": truncated,
                "text": truncated_text,
            }, ensure_ascii=False)

        windows = _build_progressive_windows(total_pages, window_size=window_size, max_windows=max_windows)
        samples = [_extract_range(doc, start, end, total_pages) for start, end in windows]
        doc.close()

        combined_preview = "\n\n".join(
            f"=== Sample {sample['pages']} ===\n{sample['text']}" for sample in samples if sample["text"]
        )
        preview_text, preview_truncated = _truncate_text(combined_preview, _MAX_CHARS)

        section_hints: dict[str, list[str]] = {}
        for sample in samples:
            for key, hit_pages in sample["heading_hits"].items():
                section_hints.setdefault(key, [])
                section_hints[key].extend(str(page) for page in hit_pages)
        section_hints = {k: sorted(set(v), key=lambda x: int(x)) for k, v in section_hints.items()}

        return json.dumps({
            "status": "ok",
            "file": path.name,
            "mode": "progressive",
            "total_pages": total_pages,
            "pages_read": sum(sample["page_count"] for sample in samples),
            "sample_count": len(samples),
            "window_size": max(1, window_size),
            "char_count": sum(sample["char_count"] for sample in samples),
            "truncated": preview_truncated,
            "sample_ranges": [sample["pages"] for sample in samples],
            "section_hints": section_hints,
            "samples": samples,
            "text": preview_text,
        }, ensure_ascii=False)

    except Exception as exc:
        return json.dumps({"status": "error", "error": str(exc)}, ensure_ascii=False)


def _parse_pages(pages_str: str, total: int) -> list:
    """Parse a page-range string into a list of zero-based page indices.

    Args:
        pages_str: e.g. "1-10", "5", "1,3,5-8".
        total: Total number of pages in the document.

    Returns:
        Sorted list of zero-based page indices.
    """
    result = []
    for part in pages_str.split(","):
        part = part.strip()
        if "-" in part:
            start, end = part.split("-", 1)
            s = max(int(start.strip()) - 1, 0)
            e = min(int(end.strip()), total)
            result.extend(range(s, e))
        elif part.isdigit():
            result.append(int(part) - 1)
    return sorted(set(result))


class DocReaderTool(BaseTool):
    """PDF document reader tool."""

    name = "read_document"
    description = "Read a PDF document: extract text pages + OCR for image/scanned pages. Supports research papers, financial reports, etc. Accepts optional page ranges."
    parameters = {
        "type": "object",
        "properties": {
            "file_path": {"type": "string", "description": "Absolute path to the PDF file"},
            "pages": {"type": "string", "description": "Page range (e.g. '1-10', '5', '1,3,5-8'); leave empty for all pages", "default": ""},
            "mode": {
                "type": "string",
                "description": "Read mode: `full` reads the selected pages or whole PDF, `progressive` samples page windows across large PDFs, `auto` switches to progressive for long PDFs.",
                "default": "full",
                "enum": ["full", "progressive", "auto"],
            },
            "window_size": {
                "type": "integer",
                "description": "Pages per sampled window in progressive mode.",
                "default": _DEFAULT_PROGRESSIVE_WINDOW_SIZE,
                "minimum": 1,
            },
            "max_windows": {
                "type": "integer",
                "description": "Maximum sampled windows in progressive mode.",
                "default": _DEFAULT_PROGRESSIVE_MAX_WINDOWS,
                "minimum": 1,
            },
        },
        "required": ["file_path"],
    }
    repeatable = True

    def execute(self, **kwargs) -> str:
        """Read PDF document."""
        return read_document(
            kwargs["file_path"],
            kwargs.get("pages", ""),
            kwargs.get("mode", "full"),
            kwargs.get("window_size", _DEFAULT_PROGRESSIVE_WINDOW_SIZE),
            kwargs.get("max_windows", _DEFAULT_PROGRESSIVE_MAX_WINDOWS),
        )
