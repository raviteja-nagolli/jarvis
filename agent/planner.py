"""
agent/planner.py — Generates and validates the execution plan.
"""
from __future__ import annotations

import logging

from pydantic import ValidationError

from agent.schemas import ExecutionPlan
from ai.gemini_client import gemini_client, GeminiError
from tools.registry import all_tool_names

logger = logging.getLogger(__name__)


class PlannerError(Exception):
    pass


def generate_plan(
    user_request: str,
    run_id: str,
    input_language: str,
    response_language: str,
    retrieved_context: str = "",
) -> ExecutionPlan:
    """
    Ask Gemini to produce a plan, then validate it with Pydantic.
    Raises PlannerError on failure.
    """
    if not user_request.strip():
        raise PlannerError("User request must not be empty")

    known_tools = set(all_tool_names())

    try:
        raw_plan = gemini_client.generate_plan(
            user_request=user_request,
            run_id=run_id,
            input_language=input_language,
            response_language=response_language,
            retrieved_context=retrieved_context,
        )
    except Exception as exc:
        raise PlannerError(str(exc)) from exc

    # Validate tool names before Pydantic validation
    for step in raw_plan.get("steps", []):
        tool = step.get("tool_name", "")
        if tool not in known_tools:
            raise PlannerError(
                f"Plan contains unknown tool '{tool}'. "
                f"Allowed tools: {sorted(known_tools)}"
            )

    try:
        plan = ExecutionPlan(**raw_plan)
    except ValidationError as exc:
        errors = exc.errors()
        raise PlannerError(f"Plan validation failed: {errors}") from exc

    return plan
