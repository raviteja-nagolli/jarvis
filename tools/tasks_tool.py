"""
tools/tasks_tool.py — Task management tool.
"""
from database import db


_VALID_PRIORITIES = {"low", "medium", "high"}
_VALID_STATUSES = {"pending", "in_progress", "completed"}


def create_task(title: str, description: str = "", due_date: str = "",
                priority: str = "medium") -> dict:
    title = title.strip()
    description = (description or "").strip()
    priority = priority.lower() if priority else "medium"

    if not title:
        raise ValueError("Task title must not be empty")
    if len(title) > 500:
        raise ValueError("Task title exceeds 500 characters")
    if priority not in _VALID_PRIORITIES:
        raise ValueError(f"Priority must be one of {_VALID_PRIORITIES}")

    task_id = db.create_task(title, description, due_date, priority)
    return {"task_id": task_id, "title": title, "priority": priority}


def list_tasks(status: str = "", due_date: str = "") -> dict:
    if status and status not in _VALID_STATUSES:
        raise ValueError(f"Status must be one of {_VALID_STATUSES}")
    tasks = db.get_tasks(status=status, due_date=due_date)
    return {"tasks": tasks, "count": len(tasks)}


def complete_task(task_id: str) -> dict:
    task = db.get_task(task_id)
    if task is None:
        raise ValueError(f"Task '{task_id}' does not exist")
    updated = db.complete_task(task_id)
    return {"task_id": task_id, "updated": updated}


def verify_task_created(task_id: str, expected_title: str = "") -> dict:
    task = db.get_task(task_id)
    if task is None:
        return {
            "passed": False,
            "method": "read_after_write",
            "evidence": {"record_exists": False},
        }
    title_match = (not expected_title) or task["title"] == expected_title
    return {
        "passed": title_match,
        "method": "read_after_write",
        "evidence": {
            "record_exists": True,
            "fields_match": title_match,
            "stored_title": task["title"],
            "stored_status": task["status"],
        },
    }


def verify_task_completed(task_id: str) -> dict:
    task = db.get_task(task_id)
    if task is None:
        return {
            "passed": False,
            "method": "read_after_write",
            "evidence": {"record_exists": False},
        }
    completed = task["status"] == "completed"
    return {
        "passed": completed,
        "method": "read_after_write",
        "evidence": {
            "record_exists": True,
            "status": task["status"],
            "is_completed": completed,
        },
    }
