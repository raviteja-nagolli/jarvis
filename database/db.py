"""
database/db.py — SQLite connection and schema initialization.

Each call to get_connection() opens a fresh thread-local connection so that
background workers and request handlers can safely use the database in parallel.
"""
import json
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

from config import config

_local = threading.local()
_SCHEMA_PATH = Path(__file__).parent / "schema.sql"


def _utcnow() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def get_connection() -> sqlite3.Connection:
    """
    Return a SQLite connection for the current thread.
    Creates a new one if none exists.
    """
    conn = getattr(_local, "conn", None)
    if conn is None:
        db_path = Path(config.DATABASE_PATH)
        db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(db_path), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
        _local.conn = conn
    return conn


def close_connection() -> None:
    """Close the thread-local connection if open."""
    conn = getattr(_local, "conn", None)
    if conn:
        conn.close()
        _local.conn = None


def init_db() -> None:
    """Create tables from schema.sql if they do not already exist."""
    schema = _SCHEMA_PATH.read_text(encoding="utf-8")
    conn = get_connection()
    conn.executescript(schema)
    conn.commit()


# ── Generic helpers ───────────────────────────────────────────────────────────

def new_id() -> str:
    return str(uuid.uuid4())


def row_to_dict(row: sqlite3.Row | None) -> dict | None:
    if row is None:
        return None
    return dict(row)


def rows_to_list(rows) -> list[dict]:
    return [dict(r) for r in rows]


# ── Run CRUD ──────────────────────────────────────────────────────────────────

def create_run(user_request: str, input_language: str, response_language: str) -> str:
    run_id = new_id()
    conn = get_connection()
    conn.execute(
        """INSERT INTO runs (id, user_request, input_language, response_language, status, created_at)
           VALUES (?, ?, ?, ?, 'planned', ?)""",
        (run_id, user_request, input_language, response_language, _utcnow()),
    )
    conn.commit()
    return run_id


def update_run(run_id: str, **kwargs) -> None:
    if not kwargs:
        return
    now = _utcnow()
    conn = get_connection()
    for key, val in kwargs.items():
        if isinstance(val, (dict, list)):
            val = json.dumps(val, ensure_ascii=False)
        conn.execute(f"UPDATE runs SET {key} = ? WHERE id = ?", (val, run_id))
    conn.commit()


def get_run(run_id: str) -> dict | None:
    conn = get_connection()
    row = conn.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
    return row_to_dict(row)


def get_recent_runs(limit: int = 20) -> list[dict]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM runs ORDER BY created_at DESC LIMIT ?", (limit,)
    ).fetchall()
    return rows_to_list(rows)


# ── Step CRUD ─────────────────────────────────────────────────────────────────

def create_step(run_id: str, step_data: dict) -> str:
    step_id = new_id()
    now = _utcnow()
    conn = get_connection()
    conn.execute(
        """INSERT INTO steps
           (id, run_id, step_number, title, tool_name, arguments_json,
            dependencies_json, expected_result, status, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'planned', ?, ?)""",
        (
            step_id,
            run_id,
            step_data["step_number"],
            step_data["title"],
            step_data["tool_name"],
            json.dumps(step_data.get("arguments", {}), ensure_ascii=False),
            json.dumps(step_data.get("dependencies", []), ensure_ascii=False),
            step_data.get("expected_result", ""),
            now,
            now,
        ),
    )
    conn.commit()
    return step_id


def update_step(step_id: str, **kwargs) -> None:
    if not kwargs:
        return
    now = _utcnow()
    conn = get_connection()
    for key, val in kwargs.items():
        if isinstance(val, (dict, list)):
            val = json.dumps(val, ensure_ascii=False)
        conn.execute(f"UPDATE steps SET {key} = ?, updated_at = ? WHERE id = ?", (val, now, step_id))
    conn.commit()


def get_steps(run_id: str) -> list[dict]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM steps WHERE run_id = ? ORDER BY step_number", (run_id,)
    ).fetchall()
    return rows_to_list(rows)


# ── Notes CRUD ────────────────────────────────────────────────────────────────

def create_note(title: str, content: str) -> str:
    note_id = new_id()
    now = _utcnow()
    conn = get_connection()
    conn.execute(
        "INSERT INTO notes (id, title, content, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
        (note_id, title, content, now, now),
    )
    conn.commit()
    return note_id


def get_note(note_id: str) -> dict | None:
    conn = get_connection()
    row = conn.execute("SELECT * FROM notes WHERE id = ?", (note_id,)).fetchone()
    return row_to_dict(row)


def get_notes(query: str = "") -> list[dict]:
    conn = get_connection()
    if query:
        rows = conn.execute(
            "SELECT * FROM notes WHERE title LIKE ? OR content LIKE ? ORDER BY created_at DESC",
            (f"%{query}%", f"%{query}%"),
        ).fetchall()
    else:
        rows = conn.execute("SELECT * FROM notes ORDER BY created_at DESC").fetchall()
    return rows_to_list(rows)


# ── Tasks CRUD ────────────────────────────────────────────────────────────────

def create_task(title: str, description: str = "", due_date: str = "", priority: str = "medium") -> str:
    task_id = new_id()
    now = _utcnow()
    conn = get_connection()
    conn.execute(
        """INSERT INTO tasks (id, title, description, due_date, priority, status, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, 'pending', ?, ?)""",
        (task_id, title, description, due_date, priority, now, now),
    )
    conn.commit()
    return task_id


def get_task(task_id: str) -> dict | None:
    conn = get_connection()
    row = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
    return row_to_dict(row)


def complete_task(task_id: str) -> bool:
    now = _utcnow()
    conn = get_connection()
    cursor = conn.execute(
        "UPDATE tasks SET status = 'completed', updated_at = ? WHERE id = ?",
        (now, task_id),
    )
    conn.commit()
    return cursor.rowcount > 0


def get_tasks(status: str = "", due_date: str = "") -> list[dict]:
    conn = get_connection()
    clauses, params = [], []
    if status:
        clauses.append("status = ?")
        params.append(status)
    if due_date:
        clauses.append("due_date = ?")
        params.append(due_date)
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    rows = conn.execute(
        f"SELECT * FROM tasks {where} ORDER BY created_at DESC", params
    ).fetchall()
    return rows_to_list(rows)


# ── Knowledge docs CRUD ───────────────────────────────────────────────────────

def create_knowledge_doc(filename: str, display_name: str) -> str:
    doc_id = new_id()
    now = _utcnow()
    conn = get_connection()
    conn.execute(
        """INSERT INTO knowledge_docs
           (id, filename, display_name, status, created_at)
           VALUES (?, ?, ?, 'uploading', ?)""",
        (doc_id, filename, display_name, now),
    )
    conn.commit()
    return doc_id


def update_knowledge_doc(doc_id: str, **kwargs) -> None:
    if not kwargs:
        return
    now = _utcnow()
    conn = get_connection()
    for key, val in kwargs.items():
        conn.execute(f"UPDATE knowledge_docs SET {key} = ? WHERE id = ?", (val, doc_id))
    conn.commit()


def get_knowledge_docs() -> list[dict]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM knowledge_docs ORDER BY created_at DESC"
    ).fetchall()
    return rows_to_list(rows)


def get_knowledge_doc(doc_id: str) -> dict | None:
    conn = get_connection()
    row = conn.execute("SELECT * FROM knowledge_docs WHERE id = ?", (doc_id,)).fetchone()
    return row_to_dict(row)


# ── Run events ────────────────────────────────────────────────────────────────

def add_run_event(run_id: str, event_type: str, message: str,
                  step_id: str = None, details: dict = None) -> str:
    event_id = new_id()
    now = _utcnow()
    conn = get_connection()
    conn.execute(
        """INSERT INTO run_events (id, run_id, step_id, event_type, message, details_json, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (event_id, run_id, step_id, event_type, message,
         json.dumps(details or {}, ensure_ascii=False), now),
    )
    conn.commit()
    return event_id


def get_run_events(run_id: str) -> list[dict]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM run_events WHERE run_id = ? ORDER BY created_at", (run_id,)
    ).fetchall()
    return rows_to_list(rows)
