"""
agent/verifier.py — Step-result verification logic.

Each tool that mutates state has a corresponding verify_fn in the registry.
This module calls it and normalises the result into a VerificationResult dict.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from agent.schemas import VerificationResult

logger = logging.getLogger(__name__)


def verify_step(
    tool_name: str,
    tool_output: Any,
    arguments: dict,
) -> VerificationResult:
    """
    Run the tool's registered verification function.
    If none exists, return a lightweight output-presence check.
    """
    from tools.registry import get_tool

    try:
        tool_def = get_tool(tool_name)
    except KeyError:
        return VerificationResult(
            passed=False,
            method="unknown_tool",
            evidence={"error": f"Tool '{tool_name}' not in registry"},
        )

    verify_fn = tool_def.verify_fn

    if verify_fn is None:
        # Read-only tools: verify that output is non-empty
        has_output = tool_output is not None and tool_output != {} and tool_output != []
        return VerificationResult(
            passed=has_output,
            method="output_present",
            evidence={"has_output": has_output},
        )

    try:
        # Build verification arguments from tool output + original args
        ver_kwargs = _build_verify_kwargs(tool_name, tool_output, arguments)
        result_dict = verify_fn(**ver_kwargs)
        return VerificationResult(**result_dict)
    except Exception as exc:
        logger.error("Verification error for '%s': %s", tool_name, exc)
        return VerificationResult(
            passed=False,
            method="verification_exception",
            evidence={},
            error=str(exc),
        )


def _build_verify_kwargs(tool_name: str, output: Any, arguments: dict) -> dict:
    """Map tool output and arguments to verification function parameters."""
    if tool_name == "create_note":
        return {
            "note_id": output.get("note_id", "") if isinstance(output, dict) else "",
            "expected_title": arguments.get("title", ""),
            "expected_content": arguments.get("content", ""),
        }
    if tool_name == "create_task":
        return {
            "task_id": output.get("task_id", "") if isinstance(output, dict) else "",
            "expected_title": arguments.get("title", ""),
        }
    if tool_name == "complete_task":
        return {
            "task_id": arguments.get("task_id", ""),
        }
    if tool_name == "calculate":
        return {
            "expression": arguments.get("expression", ""),
            "expected_result": output.get("result") if isinstance(output, dict) else None,
        }
    if tool_name == "open_app":
        # verify_app_opened takes the result dict directly
        return {"result": output if isinstance(output, dict) else {}}
    if tool_name == "open_web":
        # verify_web_opened takes the result dict directly
        return {"result": output if isinstance(output, dict) else {}}
    return {}
