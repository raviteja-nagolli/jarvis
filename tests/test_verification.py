"""
tests/test_verification.py — Verification and recovery unit tests.
"""
import pytest


# ── Verification ──────────────────────────────────────────────────────────────

def test_note_verification_passes_on_correct_write():
    from tools.notes_tool import create_note, verify_note
    result = create_note("VTest", "VContent")
    ver = verify_note(result["note_id"], expected_title="VTest", expected_content="VContent")
    assert ver["passed"] is True


def test_note_verification_fails_on_wrong_content():
    from tools.notes_tool import create_note, verify_note
    result = create_note("VTest2", "CorrectContent")
    ver = verify_note(result["note_id"], expected_content="WrongContent")
    assert ver["passed"] is False


def test_note_verification_fails_for_missing_record():
    from tools.notes_tool import verify_note
    ver = verify_note("does-not-exist-at-all")
    assert ver["passed"] is False
    assert ver["evidence"]["record_exists"] is False


def test_task_not_marked_completed_before_status_checked():
    from tools.tasks_tool import create_task, verify_task_completed
    t = create_task("Status check task")
    ver = verify_task_completed(t["task_id"])
    # Should not be completed because we haven't called complete_task
    assert ver["passed"] is False
    assert ver["evidence"]["status"] == "pending"


def test_verification_failure_stays_false():
    """A failed verification cannot silently become success."""
    from tools.notes_tool import verify_note
    ver = verify_note("fake-id-xxxx")
    # No mutation should flip this
    assert ver["passed"] is False


# ── Recovery ──────────────────────────────────────────────────────────────────

def test_transient_error_is_retriable():
    from agent.recovery import ErrorCategory, should_retry
    assert should_retry(ErrorCategory.transient, attempt=1, max_retries=2) is True


def test_transient_error_stops_at_limit():
    from agent.recovery import ErrorCategory, should_retry
    assert should_retry(ErrorCategory.transient, attempt=2, max_retries=2) is False


def test_permission_error_never_retried():
    from agent.recovery import ErrorCategory, should_retry
    assert should_retry(ErrorCategory.permission, attempt=0, max_retries=10) is False


def test_invalid_args_never_retried():
    from agent.recovery import ErrorCategory, should_retry
    assert should_retry(ErrorCategory.invalid_arguments, attempt=0, max_retries=5) is False


def test_error_classification_transient():
    from agent.recovery import classify_error, ErrorCategory
    exc = Exception("connection timeout")
    assert classify_error(exc) == ErrorCategory.transient


def test_error_classification_missing():
    from agent.recovery import classify_error, ErrorCategory
    exc = Exception("task does not exist")
    assert classify_error(exc) == ErrorCategory.missing_record


def test_error_classification_invalid():
    from agent.recovery import classify_error, ErrorCategory
    exc = ValueError("invalid argument type")
    assert classify_error(exc) == ErrorCategory.invalid_arguments


# ── Duplicate prevention ───────────────────────────────────────────────────────

def test_notes_not_duplicated_on_reraise():
    """Creating the same note twice should produce two distinct records, not overwrite."""
    from tools.notes_tool import create_note, get_notes
    create_note("Dup Title", "Dup Content")
    create_note("Dup Title", "Dup Content")
    result = get_notes(query="Dup Title")
    # Both exist as separate records
    assert result["count"] >= 2


def test_partial_results_preserved_after_step_failure():
    """
    Simulate: step 1 succeeds (create_note), step 2 fails (bad tool call).
    Step 1's note must still be retrievable.
    """
    from tools.notes_tool import create_note, verify_note

    note_result = create_note("Partial Success Note", "This was created before failure")
    note_id = note_result["note_id"]

    # Simulate a later failure — does not affect the note
    try:
        from tools.registry import call_tool
        call_tool("nonexistent_tool", {})
    except KeyError:
        pass

    ver = verify_note(note_id)
    assert ver["passed"] is True
    assert ver["evidence"]["record_exists"] is True
