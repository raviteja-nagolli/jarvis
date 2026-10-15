"""
agent/executor.py — Executes a single approved step with retries and verification.

Keeps all DB writes on the calling thread's connection.
"""
from __future__ import annotations

import json
import logging
import time
from typing import Any

from agent.recovery import (
    ErrorCategory,
    classify_error,
    recovery_summary,
    retry_delay,
    should_retry,
)
from agent.schemas import StepStatus, VerificationResult
from agent.verifier import verify_step
from database import db
from tools.registry import call_tool, get_tool

logger = logging.getLogger(__name__)


class ExecutorError(Exception):
    pass


def execute_step(
    step_db_id: str,
    run_id: str,
    tool_name: str,
    arguments: dict,
    step_number: int,
) -> dict:
    """
    Execute a single step with bounded retries.
    Returns:
        {
            "status": StepStatus,
            "output": Any,
            "verification": dict,
            "attempts": int,
            "error": str | None,
            "error_category": str | None,
        }
    """
    from config import config

    tool_def = get_tool(tool_name)
    max_retries = tool_def.max_retries
    attempt = 0
    last_error: str = ""
    last_category: ErrorCategory = ErrorCategory.unrecoverable

    db.update_step(step_db_id, status="running")
    db.add_run_event(run_id, "step_started", f"Step {step_number}: {tool_name} started",
                     step_id=step_db_id)

    while True:
        attempt += 1
        db.update_step(step_db_id, attempts=attempt)

        try:
            output = call_tool(tool_name, arguments)
        except Exception as exc:
            last_error = str(exc)
            last_category = classify_error(exc)
            logger.warning(
                "Step %d tool '%s' attempt %d failed [%s]: %s",
                step_number, tool_name, attempt, last_category, exc
            )
            db.add_run_event(
                run_id, "step_error",
                f"Step {step_number} attempt {attempt} failed: {last_error}",
                step_id=step_db_id,
                details={"error_category": last_category, "attempt": attempt},
            )

            if should_retry(last_category, attempt, max_retries, tool_name):
                db.update_step(step_db_id, status="retrying", error=last_error)
                time.sleep(retry_delay(attempt))
                continue

            # No retry — record failure
            db.update_step(
                step_db_id,
                status="failed",
                error=last_error,
                verification_json=json.dumps({
                    "passed": False,
                    "method": "execution_failed",
                    "evidence": {"error_category": last_category},
                }),
            )
            return {
                "status": StepStatus.failed,
                "output": None,
                "verification": {"passed": False, "method": "execution_failed",
                                 "evidence": {"error_category": last_category}},
                "attempts": attempt,
                "error": last_error,
                "error_category": last_category,
            }

        # ── Tool call succeeded — now verify ──────────────────────────────────
        verification = verify_step(tool_name, output, arguments)

        if verification.passed:
            ver_dict = verification.model_dump()
            db.update_step(
                step_db_id,
                status="succeeded",
                output_json=json.dumps(output, ensure_ascii=False, default=str),
                verification_json=json.dumps(ver_dict, ensure_ascii=False),
                error=None,
            )
            db.add_run_event(
                run_id, "step_succeeded",
                f"Step {step_number}: {tool_name} succeeded",
                step_id=step_db_id,
                details={"output": output, "verification": ver_dict},
            )
            return {
                "status": StepStatus.succeeded,
                "output": output,
                "verification": ver_dict,
                "attempts": attempt,
                "error": None,
                "error_category": None,
            }
        else:
            # Verification failed
            last_error = f"Verification failed: {verification.error or 'check evidence'}"
            last_category = ErrorCategory.verification_failure
            logger.warning(
                "Step %d '%s' verification failed (attempt %d): %s",
                step_number, tool_name, attempt, verification
            )

            if should_retry(last_category, attempt, max_retries, tool_name):
                db.update_step(step_db_id, status="retrying", error=last_error)
                time.sleep(retry_delay(attempt))
                continue

            ver_dict = verification.model_dump()
            db.update_step(
                step_db_id,
                status="failed",
                output_json=json.dumps(output, ensure_ascii=False, default=str),
                verification_json=json.dumps(ver_dict, ensure_ascii=False),
                error=last_error,
            )
            return {
                "status": StepStatus.failed,
                "output": output,
                "verification": ver_dict,
                "attempts": attempt,
                "error": last_error,
                "error_category": last_category,
            }
