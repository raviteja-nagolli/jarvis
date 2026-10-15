"""
tests/test_tools.py — Unit tests for notes, tasks, and calculator tools.
"""
import pytest


# ── Notes ─────────────────────────────────────────────────────────────────────

def test_create_note_success():
    from tools.notes_tool import create_note
    result = create_note("Test Note", "Some content here")
    assert "note_id" in result
    assert result["title"] == "Test Note"


def test_create_note_persists():
    from tools.notes_tool import create_note, verify_note
    result = create_note("Persistent", "Content")
    ver = verify_note(result["note_id"], expected_title="Persistent")
    assert ver["passed"] is True
    assert ver["evidence"]["record_exists"] is True


def test_create_note_empty_title_fails():
    from tools.notes_tool import create_note
    with pytest.raises(ValueError, match="title"):
        create_note("", "Content")


def test_create_note_empty_content_fails():
    from tools.notes_tool import create_note
    with pytest.raises(ValueError, match="content"):
        create_note("Title", "")


def test_get_notes_returns_saved():
    from tools.notes_tool import create_note, get_notes
    create_note("Findable Note", "unique_marker_xyz")
    result = get_notes(query="unique_marker_xyz")
    assert result["count"] >= 1
    assert any("unique_marker_xyz" in n["content"] for n in result["notes"])


def test_verify_note_wrong_title_fails():
    from tools.notes_tool import create_note, verify_note
    result = create_note("Actual Title", "Body")
    ver = verify_note(result["note_id"], expected_title="Wrong Title")
    assert ver["passed"] is False


def test_verify_note_missing_id_fails():
    from tools.notes_tool import verify_note
    ver = verify_note("nonexistent-id-0000")
    assert ver["passed"] is False
    assert ver["evidence"]["record_exists"] is False


# ── Tasks ─────────────────────────────────────────────────────────────────────

def test_create_task_success():
    from tools.tasks_tool import create_task
    result = create_task("Buy groceries", priority="low")
    assert "task_id" in result
    assert result["priority"] == "low"


def test_create_task_persists():
    from tools.tasks_tool import create_task, verify_task_created
    result = create_task("Verify me")
    ver = verify_task_created(result["task_id"], expected_title="Verify me")
    assert ver["passed"] is True


def test_create_task_empty_title_fails():
    from tools.tasks_tool import create_task
    with pytest.raises(ValueError, match="title"):
        create_task("")


def test_create_task_invalid_priority_fails():
    from tools.tasks_tool import create_task
    with pytest.raises(ValueError, match="Priority"):
        create_task("Task", priority="urgent")


def test_list_tasks_filters_by_status():
    from tools.tasks_tool import create_task, list_tasks, complete_task
    t = create_task("Filter me")
    complete_task(t["task_id"])
    result = list_tasks(status="completed")
    assert any(task["id"] == t["task_id"] for task in result["tasks"])


def test_complete_task_changes_status():
    from tools.tasks_tool import create_task, complete_task, verify_task_completed
    t = create_task("Complete me")
    complete_task(t["task_id"])
    ver = verify_task_completed(t["task_id"])
    assert ver["passed"] is True
    assert ver["evidence"]["status"] == "completed"


def test_complete_nonexistent_task_fails():
    from tools.tasks_tool import complete_task
    with pytest.raises(ValueError, match="does not exist"):
        complete_task("00000000-0000-0000-0000-000000000000")


# ── Calculator ────────────────────────────────────────────────────────────────

def test_calculate_addition():
    from tools.calculator_tool import calculate
    r = calculate("2 + 3")
    assert r["result"] == 5


def test_calculate_complex():
    from tools.calculator_tool import calculate
    r = calculate("(10 + 5) * 2 / 3")
    assert abs(r["result"] - 10.0) < 1e-9


def test_calculate_division_by_zero():
    from tools.calculator_tool import calculate
    with pytest.raises(ZeroDivisionError):
        calculate("1 / 0")


def test_calculate_rejects_function_call():
    from tools.calculator_tool import calculate
    with pytest.raises(ValueError):
        calculate("__import__('os').system('ls')")


def test_calculate_rejects_eval_bypass():
    from tools.calculator_tool import calculate
    with pytest.raises(ValueError):
        calculate("open('/etc/passwd').read()")


def test_calculate_empty_expression():
    from tools.calculator_tool import calculate
    with pytest.raises(ValueError, match="empty"):
        calculate("")


def test_calculate_large_exponent_rejected():
    from tools.calculator_tool import calculate
    with pytest.raises(ValueError, match="[Ee]xponent"):
        calculate("2 ** 1000")


# ── Registry ──────────────────────────────────────────────────────────────────

def test_unknown_tool_rejected():
    from tools.registry import call_tool
    with pytest.raises(KeyError, match="Unknown tool"):
        call_tool("rm_rf_everything", {})


def test_registry_has_required_tools():
    from tools.registry import all_tool_names
    names = all_tool_names()
    for required in ["create_note", "get_notes", "create_task",
                      "list_tasks", "complete_task", "calculate", "search_knowledge"]:
        assert required in names, f"Missing required tool: {required}"


def test_call_tool_missing_required_arg():
    from tools.registry import call_tool
    with pytest.raises(ValueError, match="requires argument"):
        call_tool("create_note", {"title": "No content"})
