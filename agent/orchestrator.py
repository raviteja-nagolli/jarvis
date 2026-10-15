"""
agent/orchestrator.py — Runs an approved plan end-to-end in a background thread.

Each worker thread opens its own DB connection. The thread pool is bounded
by MAX_CONCURRENT_RUNS. Cancellation is cooperative via a cancel flag.
"""
from __future__ import annotations

import json
import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Optional

from agent.executor import execute_step
from agent.schemas import ExecutionPlan, RunStatus, StepStatus
from ai.gemini_client import gemini_client
from config import config
from database import db

logger = logging.getLogger(__name__)

_pool = ThreadPoolExecutor(max_workers=config.MAX_CONCURRENT_RUNS, thread_name_prefix="jarvis-worker")
_cancel_flags: dict[str, threading.Event] = {}
_cancel_lock = threading.Lock()


# ── Public API ────────────────────────────────────────────────────────────────

def submit_run(run_id: str, plan: ExecutionPlan) -> None:
    """Submit an approved run to the worker pool."""
    cancel_event = threading.Event()
    with _cancel_lock:
        _cancel_flags[run_id] = cancel_event
    _pool.submit(_run_worker, run_id, plan, cancel_event)


def cancel_run(run_id: str) -> bool:
    """Signal a run to cancel. Returns True if a flag was found."""
    with _cancel_lock:
        event = _cancel_flags.get(run_id)
    if event:
        event.set()
        return True
    return False


# ── Worker ────────────────────────────────────────────────────────────────────

def _run_worker(run_id: str, plan: ExecutionPlan, cancel_event: threading.Event) -> None:
    """
    Runs all steps in dependency order. Each step waits for its prerequisites.
    Partial successes are preserved; dependent steps are blocked on failure.
    """
    # Worker uses its own thread-local DB connection
    now = db._utcnow()
    db.update_run(run_id, status="running", started_at=now)
    db.add_run_event(run_id, "run_started", "Execution started")

    # Map step_number → db step id
    step_id_map: dict[int, str] = {}
    # Map step_number → result dict
    step_results: dict[int, dict] = {}
    # Track which step_numbers have succeeded
    succeeded: set[int] = set()
    # Track which step_numbers failed
    failed: set[int] = set()

    # Load DB step records in order
    db_steps = db.get_steps(run_id)
    step_id_map = {s["step_number"]: s["id"] for s in db_steps}

    for plan_step in sorted(plan.steps, key=lambda s: s.step_number):
        if cancel_event.is_set():
            _mark_remaining_cancelled(run_id, step_id_map, step_results, plan.steps)
            break

        snum = plan_step.step_number
        step_db_id = step_id_map.get(snum)

        # Check dependencies
        deps = plan_step.dependencies
        blocking_deps = [d for d in deps if d in failed]
        if blocking_deps:
            logger.info("Step %d blocked by failed deps: %s", snum, blocking_deps)
            if step_db_id:
                db.update_step(step_db_id, status="blocked",
                               error=f"Blocked by failed steps: {blocking_deps}")
                db.add_run_event(run_id, "step_blocked",
                                 f"Step {snum} blocked by failed dependencies",
                                 step_id=step_db_id)
            step_results[snum] = {
                "status": StepStatus.blocked,
                "tool_name": plan_step.tool_name,
                "step_number": snum,
                "error": f"Blocked by failed steps: {blocking_deps}",
            }
            failed.add(snum)
            continue

        # Execute
        result = execute_step(
            step_db_id=step_db_id,
            run_id=run_id,
            tool_name=plan_step.tool_name,
            arguments=plan_step.arguments,
            step_number=snum,
        )
        result["tool_name"] = plan_step.tool_name
        result["step_number"] = snum
        step_results[snum] = result

        if result["status"] == StepStatus.succeeded:
            succeeded.add(snum)
        else:
            failed.add(snum)

    # ── Build final report ────────────────────────────────────────────────────
    _finalise_run(run_id, plan, step_results, succeeded, failed)

    with _cancel_lock:
        _cancel_flags.pop(run_id, None)


def _finalise_run(
    run_id: str,
    plan: ExecutionPlan,
    step_results: dict[int, dict],
    succeeded: set[int],
    failed: set[int],
) -> None:
    total = len(plan.steps)
    n_succeeded = len(succeeded)
    n_failed = len(failed)

    if n_failed == 0:
        status = RunStatus.succeeded
    elif n_succeeded == 0:
        status = RunStatus.failed
    else:
        status = RunStatus.partially_completed

    # Build step result list for the final response
    results_list = [
        {
            "step_number": r["step_number"],
            "tool_name": r["tool_name"],
            "status": r["status"],
            "output": r.get("output"),
            "error": r.get("error"),
            "verification": r.get("verification"),
        }
        for r in sorted(step_results.values(), key=lambda x: x["step_number"])
    ]

    # Generate final response text via Gemini
    try:
        final_text = gemini_client.generate_final_response(
            user_request=plan.original_request,
            step_results=results_list,
            response_language=plan.response_language,
        )
    except Exception as exc:
        logger.error("Final response generation failed: %s", exc)
        final_text = f"Execution {status}. {n_succeeded}/{total} steps succeeded."

    report = {
        "status": status,
        "summary": final_text,
        "steps_succeeded": n_succeeded,
        "steps_failed": n_failed,
        "steps_total": total,
        "step_results": results_list,
    }

    now = db._utcnow()
    db.update_run(
        run_id,
        status=status,
        final_report_json=report,
        completed_at=now,
    )
    db.add_run_event(run_id, "run_completed",
                     f"Run finished with status '{status}': {n_succeeded}/{total} steps succeeded")
    logger.info("Run %s finished: %s (%d/%d succeeded)", run_id, status, n_succeeded, total)


def _mark_remaining_cancelled(
    run_id: str,
    step_id_map: dict[int, str],
    step_results: dict[int, dict],
    all_steps,
) -> None:
    for step in all_steps:
        snum = step.step_number
        if snum not in step_results:
            step_db_id = step_id_map.get(snum)
            if step_db_id:
                db.update_step(step_db_id, status="cancelled")
    db.update_run(run_id, status="cancelled", completed_at=db._utcnow())
    db.add_run_event(run_id, "run_cancelled", "Run was cancelled by user")
