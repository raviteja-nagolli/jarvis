"""
agent/schemas.py — Pydantic schemas for execution plans and step definitions.
"""
from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, field_validator, model_validator


class StepStatus(str, Enum):
    planned = "planned"
    running = "running"
    succeeded = "succeeded"
    retrying = "retrying"
    failed = "failed"
    blocked = "blocked"
    needs_confirmation = "needs_confirmation"
    cancelled = "cancelled"


class RunStatus(str, Enum):
    planned = "planned"
    running = "running"
    succeeded = "succeeded"
    partially_completed = "partially_completed"
    failed = "failed"
    cancelled = "cancelled"


class ExecutionStep(BaseModel):
    step_id: str
    step_number: int
    title: str
    action_description: str
    tool_name: str
    arguments: Dict[str, Any] = {}
    dependencies: List[int] = []   # step_numbers this step depends on
    expected_result: str = ""
    verification_strategy: str = ""
    status: StepStatus = StepStatus.planned
    attempts: int = 0


class ExecutionPlan(BaseModel):
    run_id: str
    summary: str
    original_request: str
    input_language: str
    response_language: str
    steps: List[ExecutionStep]

    @field_validator("steps", mode="before")
    @classmethod
    def normalize_step_dependencies(cls, steps):
        if not isinstance(steps, list):
            return steps
        id_to_num = {}
        for s in steps:
            if isinstance(s, dict):
                sid = s.get("step_id")
                snum = s.get("step_number")
                if sid is not None and snum is not None:
                    try:
                        id_to_num[str(sid)] = int(snum)
                    except (ValueError, TypeError):
                        pass
        for s in steps:
            if isinstance(s, dict) and "dependencies" in s:
                deps = s["dependencies"]
                if isinstance(deps, (int, str)):
                    deps = [deps]
                norm = []
                for d in deps or []:
                    if isinstance(d, int):
                        norm.append(d)
                    elif isinstance(d, str):
                        if d.isdigit():
                            norm.append(int(d))
                        elif d in id_to_num:
                            norm.append(id_to_num[d])
                s["dependencies"] = norm
        return steps

    @field_validator("steps")
    @classmethod
    def validate_steps(cls, steps: List[ExecutionStep]) -> List[ExecutionStep]:
        from config import config

        if len(steps) > config.MAX_AGENT_STEPS:
            raise ValueError(
                f"Plan has {len(steps)} steps, maximum is {config.MAX_AGENT_STEPS}"
            )
        if not steps:
            raise ValueError("Plan must contain at least one step")
        return steps

    @model_validator(mode="after")
    def check_no_cyclic_dependencies(self) -> "ExecutionPlan":
        step_nums = {s.step_number for s in self.steps}
        # Build adjacency
        adj: dict[int, set[int]] = {s.step_number: set(s.dependencies) for s in self.steps}
        # Validate referenced deps exist
        for sn, deps in adj.items():
            for dep in deps:
                if dep not in step_nums:
                    raise ValueError(
                        f"Step {sn} depends on step {dep} which does not exist"
                    )
        # DFS cycle detection
        visited: set[int] = set()
        in_stack: set[int] = set()

        def dfs(node: int) -> bool:
            visited.add(node)
            in_stack.add(node)
            for neighbor in adj.get(node, set()):
                if neighbor not in visited:
                    if dfs(neighbor):
                        return True
                elif neighbor in in_stack:
                    return True
            in_stack.discard(node)
            return False

        for sn in step_nums:
            if sn not in visited:
                if dfs(sn):
                    raise ValueError("Circular dependency detected in execution plan")
        return self


class VerificationResult(BaseModel):
    passed: bool
    method: str
    evidence: Dict[str, Any] = {}
    error: Optional[str] = None


class StepResult(BaseModel):
    step_id: str
    tool_name: str
    status: StepStatus
    attempts: int
    output: Any = None
    verification: Optional[VerificationResult] = None
    error: Optional[str] = None


class FinalReport(BaseModel):
    run_id: str
    status: RunStatus
    summary: str
    steps: List[StepResult]
    evidence: Dict[str, Any] = {}
    partial_results: Dict[str, Any] = {}
