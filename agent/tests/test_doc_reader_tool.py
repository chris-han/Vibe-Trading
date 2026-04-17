from pathlib import Path

from src.tools import doc_reader_tool


def test_resolve_pdf_path_finds_session_scoped_upload_by_filename(tmp_path, monkeypatch):
    backend_dir = tmp_path / "agent"
    session_pdf = backend_dir / "sessions" / "sess_123" / "uploads" / "report.pdf"
    session_pdf.parent.mkdir(parents=True, exist_ok=True)
    session_pdf.write_bytes(b"%PDF-1.4\n")

    monkeypatch.setattr(
        doc_reader_tool,
        "_get_document_search_roots",
        lambda: (backend_dir / "sessions", backend_dir / "uploads"),
    )

    resolved = doc_reader_tool._resolve_pdf_path("report.pdf")

    assert resolved == session_pdf.resolve()


def test_resolve_pdf_path_finds_session_scoped_upload_from_uploads_prefix(tmp_path, monkeypatch):
    backend_dir = tmp_path / "agent"
    session_pdf = backend_dir / "sessions" / "sess_456" / "uploads" / "filing.pdf"
    session_pdf.parent.mkdir(parents=True, exist_ok=True)
    session_pdf.write_bytes(b"%PDF-1.4\n")

    monkeypatch.setattr(
        doc_reader_tool,
        "_get_document_search_roots",
        lambda: (backend_dir / "sessions", backend_dir / "uploads"),
    )

    resolved = doc_reader_tool._resolve_pdf_path("uploads/filing.pdf")

    assert resolved == session_pdf.resolve()


def test_resolve_pdf_path_prefers_runtime_uploads_over_cwd(tmp_path, monkeypatch):
    backend_dir = tmp_path / "agent"
    uploaded_pdf = backend_dir / "uploads" / "earnings.pdf"
    cwd_pdf = tmp_path / "earnings.pdf"
    uploaded_pdf.parent.mkdir(parents=True, exist_ok=True)
    uploaded_pdf.write_bytes(b"%PDF-1.4\n")
    cwd_pdf.write_bytes(b"%PDF-1.4\n")

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        doc_reader_tool,
        "_get_document_search_roots",
        lambda: (backend_dir / "sessions", backend_dir / "uploads"),
    )

    resolved = doc_reader_tool._resolve_pdf_path("earnings.pdf")

    assert resolved == uploaded_pdf.resolve()
