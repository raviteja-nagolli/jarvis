-- schema.sql — JARVIS SQLite schema
-- Enable foreign keys in every connection (must also be done at runtime).

PRAGMA foreign_keys = ON;

-- ── Execution runs ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS runs (
    id               TEXT PRIMARY KEY,
    user_request     TEXT NOT NULL,
    input_language   TEXT NOT NULL DEFAULT 'en-IN',
    response_language TEXT NOT NULL DEFAULT 'en-IN',
    plan_json        TEXT,
    status           TEXT NOT NULL DEFAULT 'planned',
    final_report_json TEXT,
    created_at       TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    started_at       TEXT,
    completed_at     TEXT
);

-- ── Execution steps ───────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS steps (
    id               TEXT PRIMARY KEY,
    run_id           TEXT NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
    step_number      INTEGER NOT NULL,
    title            TEXT NOT NULL,
    tool_name        TEXT NOT NULL,
    arguments_json   TEXT,
    dependencies_json TEXT,
    expected_result  TEXT,
    status           TEXT NOT NULL DEFAULT 'planned',
    attempts         INTEGER NOT NULL DEFAULT 0,
    output_json      TEXT,
    error            TEXT,
    verification_json TEXT,
    created_at       TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    updated_at       TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

-- ── Notes ─────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS notes (
    id         TEXT PRIMARY KEY,
    title      TEXT NOT NULL,
    content    TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

-- ── Tasks ─────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS tasks (
    id          TEXT PRIMARY KEY,
    title       TEXT NOT NULL,
    description TEXT,
    due_date    TEXT,
    priority    TEXT NOT NULL DEFAULT 'medium',
    status      TEXT NOT NULL DEFAULT 'pending',
    created_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    updated_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

-- ── Knowledge documents ───────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS knowledge_docs (
    id                       TEXT PRIMARY KEY,
    filename                 TEXT NOT NULL,
    display_name             TEXT NOT NULL,
    file_search_document_id  TEXT,
    file_search_store_id     TEXT,
    status                   TEXT NOT NULL DEFAULT 'uploading',
    error                    TEXT,
    created_at               TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    indexed_at               TEXT
);

-- ── Run events (execution timeline) ──────────────────────────────────────────
CREATE TABLE IF NOT EXISTS run_events (
    id          TEXT PRIMARY KEY,
    run_id      TEXT NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
    step_id     TEXT REFERENCES steps(id) ON DELETE SET NULL,
    event_type  TEXT NOT NULL,
    message     TEXT NOT NULL,
    details_json TEXT,
    created_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);
