"""
tools/search_tool.py — Knowledge-base search tool (RAG via Gemini File Search).
"""
from typing import Optional


def search_knowledge(query: str, scope: Optional[str] = None) -> dict:
    """
    Search the RAG knowledge base.
    Delegated to rag_client at runtime; this module provides the tool interface.
    """
    from ai.rag_client import rag_client
    return rag_client.query(query, scope=scope)
