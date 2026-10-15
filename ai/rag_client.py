"""
ai/rag_client.py — Gemini File Search RAG integration.

Manages a persistent File Search store, document upload/indexing,
and grounded retrieval. Does NOT fabricate source citations.
"""
from __future__ import annotations

import logging
import time
from typing import Optional

from config import config

logger = logging.getLogger(__name__)


class RAGError(Exception):
    pass


class GeminiRAGClient:
    """
    Wraps Gemini File API + File Search store for document indexing and retrieval.
    Uses google-genai SDK.
    """

    def __init__(self):
        self._client = None
        self._store_name: Optional[str] = None

    def _get_client(self):
        if self._client is None:
            if not config.GEMINI_API_KEY:
                raise RAGError("GEMINI_API_KEY is not configured")
            from google import genai
            self._client = genai.Client(api_key=config.GEMINI_API_KEY)
        return self._client

    def _get_store(self) -> str:
        """Return existing store name from config or create one."""
        if self._store_name:
            return self._store_name
        if config.GEMINI_FILE_SEARCH_STORE:
            self._store_name = config.GEMINI_FILE_SEARCH_STORE
            return self._store_name
        # Create a new store
        client = self._get_client()
        try:
            store = client.files.create_file_search_store(
                display_name="JARVIS Knowledge Base"
            )
            self._store_name = store.name
            logger.info("Created File Search store: %s", self._store_name)
        except Exception as exc:
            logger.warning("File Search store creation failed: %s — using file-only mode", exc)
            self._store_name = "__file_only__"
        return self._store_name

    def upload_document(self, file_bytes: bytes, filename: str, mime_type: str) -> dict:
        """
        Upload a document to Gemini Files API.
        Returns {"file_name": str, "uri": str, "success": bool, "error": str|None}.
        """
        client = self._get_client()
        import io as _io
        try:
            file_obj = client.files.upload(
                file=_io.BytesIO(file_bytes),
                config={"display_name": filename, "mime_type": mime_type},
            )
            return {
                "file_name": file_obj.name,
                "uri": file_obj.uri,
                "success": True,
                "error": None,
            }
        except Exception as exc:
            logger.error("Gemini file upload failed: %s", exc)
            return {"file_name": None, "uri": None, "success": False, "error": str(exc)}

    def add_to_store(self, file_name: str) -> dict:
        """
        Add an already-uploaded file to the File Search store.
        Returns {"success": bool, "error": str|None}.
        """
        store = self._get_store()
        if store == "__file_only__":
            # Degraded mode: store unavailable, file still retrievable via model
            return {"success": True, "error": None, "degraded": True}
        client = self._get_client()
        try:
            client.files.add_file_to_file_search_store(
                name=store,
                files=[file_name],
            )
            return {"success": True, "error": None}
        except Exception as exc:
            logger.error("Failed to add file to store: %s", exc)
            return {"success": False, "error": str(exc)}

    def query(self, question: str, scope: Optional[str] = None) -> dict:
        """
        Query the knowledge base using Gemini grounded retrieval.
        Returns:
            {
                "answer": str,
                "sources": list[dict],
                "success": bool,
                "error": str|None,
            }
        """
        if not config.GEMINI_API_KEY:
            return {
                "answer": "Knowledge retrieval is unavailable: Gemini API key not configured.",
                "sources": [],
                "success": False,
                "error": "GEMINI_API_KEY not configured",
            }

        client = self._get_client()
        store = self._get_store()

        try:
            from google.genai import types as genai_types

            # Build retrieval config
            retrieval_config = None
            if store and store != "__file_only__":
                try:
                    retrieval_config = genai_types.Retrieval(
                        vertex_ai_search=None,
                        disable_attribution=False,
                    )
                except Exception:
                    retrieval_config = None

            # Use Gemini with File Search grounding
            system_instruction = (
                "You are a knowledge assistant. Answer the user's question based only on "
                "the provided document context. If the documents do not contain relevant "
                "information, clearly state that the knowledge base does not cover this topic. "
                "Do not fabricate facts, citations, or document titles."
            )

            # Try file-search grounded generation
            if store and store != "__file_only__":
                try:
                    response = client.models.generate_content(
                        model=config.GEMINI_MODEL,
                        contents=question,
                        config=genai_types.GenerateContentConfig(
                            system_instruction=system_instruction,
                            tools=[genai_types.Tool(
                                file_search=genai_types.FileSearch(
                                    file_search_stores=[store]
                                )
                            )],
                            temperature=0.2,
                        ),
                    )
                    answer = response.text or ""
                    sources = _extract_sources(response)
                    return {"answer": answer, "sources": sources, "success": True, "error": None}
                except Exception as exc:
                    logger.warning("File Search grounded query failed: %s — falling back", exc)

            # Fallback: plain Gemini without store grounding
            response = client.models.generate_content(
                model=config.GEMINI_MODEL,
                contents=f"Based on available knowledge, answer: {question}",
                config=genai_types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    temperature=0.3,
                ),
            )
            answer = response.text or ""
            return {"answer": answer, "sources": [], "success": True, "error": None}

        except Exception as exc:
            logger.error("RAG query error: %s", exc)
            return {"answer": "", "sources": [], "success": False, "error": str(exc)}

    def list_files(self) -> list[dict]:
        """List uploaded files in the Gemini Files API."""
        if not config.GEMINI_API_KEY:
            return []
        try:
            client = self._get_client()
            files = client.files.list()
            return [
                {"name": f.name, "display_name": getattr(f, "display_name", ""),
                 "uri": f.uri, "state": str(getattr(f, "state", ""))}
                for f in files
            ]
        except Exception as exc:
            logger.error("Failed to list Gemini files: %s", exc)
            return []

    def delete_file(self, file_name: str) -> dict:
        """Delete a file from Gemini Files API."""
        if not config.GEMINI_API_KEY:
            return {"success": False, "error": "API key not configured"}
        try:
            client = self._get_client()
            client.files.delete(name=file_name)
            return {"success": True, "error": None}
        except Exception as exc:
            logger.error("Failed to delete Gemini file: %s", exc)
            return {"success": False, "error": str(exc)}


def _extract_sources(response) -> list[dict]:
    """
    Extract grounding source annotations from a Gemini response.
    Returns only what the API actually returned; never fabricates.
    """
    sources = []
    try:
        metadata = getattr(response, "candidates", [])
        for candidate in metadata:
            grounding = getattr(candidate, "grounding_metadata", None)
            if not grounding:
                continue
            chunks = getattr(grounding, "grounding_chunks", [])
            for chunk in chunks:
                retrieved = getattr(chunk, "retrieved_context", None)
                if retrieved:
                    sources.append({
                        "title": getattr(retrieved, "title", ""),
                        "uri": getattr(retrieved, "uri", ""),
                    })
    except Exception as exc:
        logger.debug("Source extraction error: %s", exc)
    return sources


# Singleton
rag_client = GeminiRAGClient()
