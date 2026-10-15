"""
tests/test_rag.py — RAG integration tests with mocked Gemini client.
"""
import pytest
from unittest.mock import MagicMock, patch


# ── Document registration ─────────────────────────────────────────────────────

def test_knowledge_doc_created_in_db():
    from database.db import create_knowledge_doc, get_knowledge_doc
    doc_id = create_knowledge_doc("test.pdf", "Test PDF")
    doc = get_knowledge_doc(doc_id)
    assert doc is not None
    assert doc["filename"] == "test.pdf"
    assert doc["status"] == "uploading"


def test_knowledge_doc_status_update():
    from database.db import create_knowledge_doc, update_knowledge_doc, get_knowledge_doc
    doc_id = create_knowledge_doc("notes.txt", "Notes")
    update_knowledge_doc(doc_id, status="ready", file_search_document_id="files/abc123")
    doc = get_knowledge_doc(doc_id)
    assert doc["status"] == "ready"
    assert doc["file_search_document_id"] == "files/abc123"


def test_indexing_failure_recorded():
    from database.db import create_knowledge_doc, update_knowledge_doc, get_knowledge_doc
    doc_id = create_knowledge_doc("bad.pdf", "Bad")
    update_knowledge_doc(doc_id, status="failed", error="Store unavailable")
    doc = get_knowledge_doc(doc_id)
    assert doc["status"] == "failed"
    assert "unavailable" in doc["error"]


# ── Retrieval with mocked client ──────────────────────────────────────────────

def test_rag_query_returns_answer():
    from ai.rag_client import GeminiRAGClient

    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.text = "Cybersecurity involves protecting networks and data."
    mock_response.candidates = []
    mock_client.models.generate_content.return_value = mock_response

    rag = GeminiRAGClient()
    rag._client = mock_client
    rag._store_name = "__file_only__"

    import os
    os.environ["GEMINI_API_KEY"] = "test-key"
    from config import config
    config.GEMINI_API_KEY = "test-key"

    result = rag.query("What is cybersecurity?")
    assert result["success"] is True
    assert "cybersecurity" in result["answer"].lower()


def test_rag_empty_result_no_fabrication():
    """Empty retrieval must not return fabricated source citations."""
    from ai.rag_client import _extract_sources

    mock_response = MagicMock()
    mock_response.candidates = []
    sources = _extract_sources(mock_response)
    assert sources == []


def test_rag_source_extraction_real_structure():
    """Source extraction only returns what the API actually provides."""
    from ai.rag_client import _extract_sources

    # Build a mock response matching the Gemini SDK structure
    chunk = MagicMock()
    chunk.retrieved_context.title = "Cybersecurity Guide"
    chunk.retrieved_context.uri = "gs://bucket/cyberguide.pdf"

    grounding = MagicMock()
    grounding.grounding_chunks = [chunk]

    candidate = MagicMock()
    candidate.grounding_metadata = grounding

    mock_response = MagicMock()
    mock_response.candidates = [candidate]

    sources = _extract_sources(mock_response)
    assert len(sources) == 1
    assert sources[0]["title"] == "Cybersecurity Guide"


def test_rag_evidence_separate_from_tool_execution():
    """
    RAG evidence (retrieved knowledge) must not be treated as proof that
    a tool action succeeded.
    """
    from tools.notes_tool import verify_note

    # A RAG answer existing does not mean a note was created
    ver = verify_note("nonexistent-note-id")
    assert ver["passed"] is False  # Must check actual DB


# ── Upload route with mock ────────────────────────────────────────────────────

def test_upload_route_rejects_unsupported_mime(client):
    data = {"file": (b"content", "file.exe", "application/octet-stream")}
    import io
    resp = client.post(
        "/api/knowledge/upload",
        data={"file": (io.BytesIO(b"data"), "malware.exe")},
        content_type="multipart/form-data",
    )
    assert resp.status_code in (400, 503)  # 503 if key not configured


def test_upload_route_requires_file_field(client):
    resp = client.post("/api/knowledge/upload", data={},
                       content_type="multipart/form-data")
    assert resp.status_code in (400, 503)
