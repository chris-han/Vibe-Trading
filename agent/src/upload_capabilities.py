from __future__ import annotations

from pathlib import Path


SUPPORTED_UPLOAD_DOCUMENT_TYPES: dict[str, str] = {
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    ".md": "text/markdown",
    ".txt": "text/plain",
    ".log": "text/plain",
    ".zip": "application/zip",
}


def supported_upload_document_types() -> dict[str, str]:
    return dict(SUPPORTED_UPLOAD_DOCUMENT_TYPES)


def supported_upload_extensions() -> tuple[str, ...]:
    return tuple(SUPPORTED_UPLOAD_DOCUMENT_TYPES.keys())


def build_upload_accept_string() -> str:
    return ",".join(supported_upload_extensions())


def format_supported_upload_extensions() -> str:
    return ", ".join(ext.lstrip(".").upper() for ext in supported_upload_extensions())


def is_supported_upload_filename(filename: str | None) -> bool:
    if not filename:
        return False
    return Path(filename).suffix.lower() in SUPPORTED_UPLOAD_DOCUMENT_TYPES


def get_upload_extension(filename: str | None) -> str | None:
    if not filename:
        return None
    extension = Path(filename).suffix.lower()
    if extension in SUPPORTED_UPLOAD_DOCUMENT_TYPES:
        return extension
    return None


def build_upload_capabilities_payload(max_upload_size_bytes: int) -> dict[str, object]:
    return {
        "allowed_extensions": list(supported_upload_extensions()),
        "accept": build_upload_accept_string(),
        "max_upload_size_bytes": max_upload_size_bytes,
        "max_upload_size_mb": max_upload_size_bytes // (1024 * 1024),
        "types_summary": format_supported_upload_extensions(),
    }