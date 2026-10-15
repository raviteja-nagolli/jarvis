"""
tools/notes_tool.py — Note creation and retrieval tool.
"""
from database import db


def create_note(title: str, content: str) -> dict:
    """Insert a note and return its ID."""
    title = title.strip()
    content = content.strip()
    if not title:
        raise ValueError("Note title must not be empty")
    if not content:
        raise ValueError("Note content must not be empty")
    if len(title) > 500:
        raise ValueError("Note title exceeds 500 characters")
    if len(content) > 50_000:
        raise ValueError("Note content exceeds 50 000 characters")

    note_id = db.create_note(title, content)
    return {"note_id": note_id, "title": title}


def get_notes(query: str = "") -> dict:
    """Retrieve notes, optionally filtered by a search query."""
    notes = db.get_notes(query=query)
    return {"notes": notes, "count": len(notes)}


def verify_note(note_id: str, expected_title: str = "", expected_content: str = "") -> dict:
    """
    Read-after-write verification: confirm the note exists and fields match.
    Returns a dict suitable for VerificationResult.
    """
    note = db.get_note(note_id)
    if note is None:
        return {
            "passed": False,
            "method": "read_after_write",
            "evidence": {"record_exists": False},
        }
    title_match = (not expected_title) or note["title"] == expected_title
    content_match = (not expected_content) or note["content"] == expected_content
    passed = title_match and content_match
    return {
        "passed": passed,
        "method": "read_after_write",
        "evidence": {
            "record_exists": True,
            "fields_match": passed,
            "title_match": title_match,
            "content_match": content_match,
            "stored_title": note["title"],
        },
    }
