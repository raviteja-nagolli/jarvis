"""
agent/recovery.py — Error classification and retry/recovery policy.
"""
from __future__ import annotations

import logging
from enum import Enum
from typing import Optional

logger = logging.getLogger(__name__)


class ErrorCategory(str, Enum):
    transient = "transient"          # Network, timeout, rate-limit — safe to retry
    invalid_arguments = "invalid_arguments"  # Don't retry identical args
    permission = "permission"        # Never retry without re-approval
    missing_record = "missing_record"
    verification_failure = "verification_failure"
    unsupported_operation = "unsupported_operation"
    unrecoverable = "unrecoverable"


def classify_error(exc: Exception) -> ErrorCategory:
    """Heuristically classify an exception into an error category."""
    msg = str(exc).lower()
    if any(k in msg for k in ("timeout", "connection", "network", "rate limit", "503", "502", "429")):
        return ErrorCategory.transient
    if any(k in msg for k in ("does not exist", "not found", "no such")):
        return ErrorCategory.missing_record
    if any(k in msg for k in ("permission", "unauthorized", "forbidden", "401", "403")):
        return ErrorCategory.permission
    if any(k in msg for k in ("invalid", "validation", "argument", "schema", "type")):
        return ErrorCategory.invalid_arguments
    if any(k in msg for k in ("unsupported", "not implemented")):
        return ErrorCategory.unsupported_operation
    return ErrorCategory.unrecoverable


def should_retry(
    category: ErrorCategory,
    attempt: int,
    max_retries: int,
    tool_name: str = "",
) -> bool:
    """
    Return True if the error is eligible for a retry given current attempt count.
    """
    if attempt >= max_retries:
        return False
    if category in (ErrorCategory.transient,):
        return True
    if category == ErrorCategory.verification_failure:
        # Only retry verification failures for idempotent tools
        from tools.registry import get_tool
        try:
            tool_def = get_tool(tool_name)
            return tool_def.idempotent and attempt < max_retries
        except KeyError:
            return False
    return False


def retry_delay(attempt: int) -> float:
    """Exponential backoff in seconds: 1s, 2s, 4s …"""
    return min(2 ** attempt, 8)


def recovery_summary(category: ErrorCategory, attempt: int, max_retries: int) -> str:
    if category == ErrorCategory.permission:
        return "Blocked: insufficient permissions. Re-approval required."
    if category == ErrorCategory.invalid_arguments:
        return "Stopped: invalid arguments. Correction required before retrying."
    if category == ErrorCategory.missing_record:
        return "Stopped: referenced record does not exist."
    if category == ErrorCategory.unsupported_operation:
        return "Stopped: operation is not supported."
    if attempt >= max_retries:
        return f"Retry limit reached after {attempt} attempt(s)."
    return f"Transient error on attempt {attempt}. Scheduling retry."
