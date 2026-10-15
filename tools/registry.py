"""
tools/registry.py — Central tool registry.

Each tool declares its name, description, input schema, callable function,
permission scope, timeout, verification function, retry policy, and idempotency notes.
Only tools listed here can be invoked by the executor.
"""
from __future__ import annotations

import json
from typing import Any, Callable, Dict, Optional


class ToolDefinition:
    def __init__(
        self,
        name: str,
        description: str,
        input_schema: Dict[str, Any],
        fn: Callable,
        verify_fn: Optional[Callable] = None,
        permission: str = "standard",
        timeout_seconds: int = 10,
        max_retries: int = 2,
        idempotent: bool = False,
    ):
        self.name = name
        self.description = description
        self.input_schema = input_schema
        self.fn = fn
        self.verify_fn = verify_fn
        self.permission = permission
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries
        self.idempotent = idempotent

    def to_gemini_declaration(self) -> Dict[str, Any]:
        """Return the function declaration dict for Gemini function-calling."""
        return {
            "name": self.name,
            "description": self.description,
            "parameters": self.input_schema,
        }


# ── Import tool implementations ───────────────────────────────────────────────
from tools.notes_tool import create_note, get_notes, verify_note
from tools.tasks_tool import (
    create_task,
    list_tasks,
    complete_task,
    verify_task_created,
    verify_task_completed,
)
from tools.calculator_tool import calculate, verify_calculation
from tools.search_tool import search_knowledge
from tools.system_tool import open_app, verify_app_opened, open_web, verify_web_opened


# ── Registry ──────────────────────────────────────────────────────────────────

_REGISTRY: Dict[str, ToolDefinition] = {}


def _reg(tool: ToolDefinition) -> None:
    _REGISTRY[tool.name] = tool


_reg(ToolDefinition(
    name="search_knowledge",
    description=(
        "Retrieve relevant information from the RAG knowledge base. "
        "Use this when the user's request requires domain knowledge from uploaded documents."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "The question or topic to search for"},
            "scope": {"type": "string", "description": "Optional knowledge scope or collection"},
        },
        "required": ["query"],
    },
    fn=search_knowledge,
    verify_fn=None,
    permission="read",
    timeout_seconds=20,
    max_retries=2,
    idempotent=True,
))

_reg(ToolDefinition(
    name="create_note",
    description="Create and persist a new note with a title and content.",
    input_schema={
        "type": "object",
        "properties": {
            "title": {"type": "string", "description": "Note title"},
            "content": {"type": "string", "description": "Note body content"},
        },
        "required": ["title", "content"],
    },
    fn=create_note,
    verify_fn=verify_note,
    permission="write",
    timeout_seconds=10,
    max_retries=1,
    idempotent=False,
))

_reg(ToolDefinition(
    name="get_notes",
    description="Retrieve saved notes, optionally filtered by a search query.",
    input_schema={
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Optional search filter"},
        },
        "required": [],
    },
    fn=get_notes,
    verify_fn=None,
    permission="read",
    timeout_seconds=10,
    max_retries=2,
    idempotent=True,
))

_reg(ToolDefinition(
    name="create_task",
    description="Create a new task with title, optional description, due date, and priority.",
    input_schema={
        "type": "object",
        "properties": {
            "title": {"type": "string", "description": "Task title"},
            "description": {"type": "string", "description": "Optional task description"},
            "due_date": {"type": "string", "description": "Optional due date (YYYY-MM-DD)"},
            "priority": {
                "type": "string",
                "enum": ["low", "medium", "high"],
                "description": "Task priority",
            },
        },
        "required": ["title"],
    },
    fn=create_task,
    verify_fn=verify_task_created,
    permission="write",
    timeout_seconds=10,
    max_retries=1,
    idempotent=False,
))

_reg(ToolDefinition(
    name="list_tasks",
    description="List tasks, optionally filtered by status and/or due date.",
    input_schema={
        "type": "object",
        "properties": {
            "status": {
                "type": "string",
                "enum": ["pending", "in_progress", "completed"],
                "description": "Filter by status",
            },
            "due_date": {"type": "string", "description": "Filter by due date (YYYY-MM-DD)"},
        },
        "required": [],
    },
    fn=list_tasks,
    verify_fn=None,
    permission="read",
    timeout_seconds=10,
    max_retries=2,
    idempotent=True,
))

_reg(ToolDefinition(
    name="complete_task",
    description="Mark an existing task as completed by its ID.",
    input_schema={
        "type": "object",
        "properties": {
            "task_id": {"type": "string", "description": "The UUID of the task to complete"},
        },
        "required": ["task_id"],
    },
    fn=complete_task,
    verify_fn=verify_task_completed,
    permission="write",
    timeout_seconds=10,
    max_retries=1,
    idempotent=True,
))

_reg(ToolDefinition(
    name="calculate",
    description=(
        "Evaluate a safe arithmetic expression. "
        "Supports +, -, *, /, **, %, and parentheses. "
        "Never pass Python code or function calls."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "expression": {
                "type": "string",
                "description": "A safe arithmetic expression, e.g. '(3 + 5) * 2'",
            },
        },
        "required": ["expression"],
    },
    fn=calculate,
    verify_fn=verify_calculation,
    permission="compute",
    timeout_seconds=5,
    max_retries=0,
    idempotent=True,
))

_reg(ToolDefinition(
    name="open_app",
    description=(
        "Launch a local desktop application on the host machine. "
        "Supported apps: 'calculator' (calc), 'notes' / 'notepad', "
        "'task_manager' / 'taskmgr' (Task Manager), and 'browser' / 'web'."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "app_name": {
                "type": "string",
                "description": "Name of the application to open: 'calculator', 'notes', 'notepad', 'task_manager', 'taskmgr', 'browser', 'web'",
            },
        },
        "required": ["app_name"],
    },
    fn=open_app,
    verify_fn=verify_app_opened,
    permission="system",
    timeout_seconds=10,
    max_retries=1,
    idempotent=True,
))

_reg(ToolDefinition(
    name="open_web",
    description=(
        "Open a webpage or perform a web search in the default web browser. "
        "Use this when the user asks to browse the web or search online."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "Optional direct URL to navigate to (e.g. 'https://github.com')",
            },
            "query": {
                "type": "string",
                "description": "Optional search query to look up on Google (e.g. 'latest tech news')",
            },
        },
        "required": [],
    },
    fn=open_web,
    verify_fn=verify_web_opened,
    permission="system",
    timeout_seconds=10,
    max_retries=1,
    idempotent=True,
))


# ── Public API ────────────────────────────────────────────────────────────────

def get_tool(name: str) -> ToolDefinition:
    """Return a tool by name. Raises KeyError for unknown tools."""
    if name not in _REGISTRY:
        raise KeyError(f"Unknown tool: '{name}'. Allowed: {list(_REGISTRY)}")
    return _REGISTRY[name]


def all_tools() -> list[ToolDefinition]:
    return list(_REGISTRY.values())


def all_tool_names() -> list[str]:
    return list(_REGISTRY.keys())


def gemini_tool_declarations() -> list[Dict[str, Any]]:
    """Return all tool declarations in Gemini function-calling format."""
    return [t.to_gemini_declaration() for t in _REGISTRY.values()]


def call_tool(name: str, arguments: Dict[str, Any]) -> Any:
    """
    Validate and call a registered tool with the given arguments.
    Raises KeyError for unknown tools, ValueError for invalid arguments.
    """
    tool = get_tool(name)  # raises KeyError if unknown
    # Basic argument validation against schema
    required = tool.input_schema.get("required", [])
    props = tool.input_schema.get("properties", {})
    for field in required:
        if field not in arguments:
            raise ValueError(f"Tool '{name}' requires argument '{field}'")
    # Strip unknown keys to avoid injection
    filtered = {k: v for k, v in arguments.items() if k in props}
    return tool.fn(**filtered)
