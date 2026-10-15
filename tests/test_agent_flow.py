"""
tests/test_agent_flow.py — Planning validation tests (no real API calls).
"""
import pytest
from unittest.mock import patch, MagicMock


VALID_PLAN = {
    "run_id": "test-run-001",
    "summary": "Test plan",
    "original_request": "Create a note",
    "input_language": "en-IN",
    "response_language": "en-IN",
    "steps": [
        {
            "step_id": "step_create_note",
            "step_number": 1,
            "title": "Create a note",
            "action_description": "Save the note to the database",
            "tool_name": "create_note",
            "arguments": {"title": "My Note", "content": "Body text"},
            "dependencies": [],
            "expected_result": "Note created",
            "verification_strategy": "read_after_write",
            "status": "planned",
            "attempts": 0,
        }
    ],
}


def test_valid_plan_accepted():
    from agent.schemas import ExecutionPlan
    plan = ExecutionPlan(**VALID_PLAN)
    assert len(plan.steps) == 1
    assert plan.steps[0].tool_name == "create_note"


def test_unknown_tool_rejected_in_planner():
    """Planner should raise PlannerError for unknown tools even before Pydantic."""
    from agent.planner import PlannerError, generate_plan
    from unittest.mock import patch

    bad_plan = dict(VALID_PLAN)
    bad_plan["steps"] = [
        {**VALID_PLAN["steps"][0], "tool_name": "delete_everything"}
    ]

    with patch("agent.planner.gemini_client") as mock_gc:
        mock_gc.generate_plan.return_value = bad_plan
        with pytest.raises(PlannerError, match="[Uu]nknown tool"):
            generate_plan("request", "run-id", "en-IN", "en-IN")


def test_excessive_steps_rejected():
    from agent.schemas import ExecutionPlan
    from pydantic import ValidationError

    step_template = VALID_PLAN["steps"][0]
    many_steps = [
        {**step_template, "step_id": f"step_{i}", "step_number": i}
        for i in range(1, 12)  # 11 steps, limit is 8
    ]
    plan_data = {**VALID_PLAN, "steps": many_steps}
    with pytest.raises(ValidationError, match="[Mm]aximum"):
        ExecutionPlan(**plan_data)


def test_invalid_json_string_rejected():
    from agent.planner import PlannerError, generate_plan
    from unittest.mock import patch

    with patch("agent.planner.gemini_client") as mock_gc:
        mock_gc.generate_plan.side_effect = Exception("invalid JSON")
        with pytest.raises(PlannerError):
            generate_plan("request", "run-id", "en-IN", "en-IN")


def test_cyclic_dependency_rejected():
    from agent.schemas import ExecutionPlan
    from pydantic import ValidationError

    cyclic_steps = [
        {**VALID_PLAN["steps"][0],
         "step_id": "step_a", "step_number": 1, "dependencies": [2]},
        {**VALID_PLAN["steps"][0],
         "step_id": "step_b", "step_number": 2, "dependencies": [1]},
    ]
    plan_data = {**VALID_PLAN, "steps": cyclic_steps}
    with pytest.raises(ValidationError, match="[Cc]ircular"):
        ExecutionPlan(**plan_data)


def test_malformed_dependency_rejected():
    from agent.schemas import ExecutionPlan
    from pydantic import ValidationError

    bad_dep_steps = [
        {**VALID_PLAN["steps"][0], "step_number": 1, "dependencies": [99]},
    ]
    plan_data = {**VALID_PLAN, "steps": bad_dep_steps}
    with pytest.raises(ValidationError):
        ExecutionPlan(**plan_data)


def test_approval_required_before_execution():
    """A run in 'planned' state requires explicit /execute call."""
    import os
    os.environ.setdefault("DATABASE_PATH", "instance/jarvis.db")
    from app import app as flask_app
    flask_app.config["TESTING"] = True

    # Create a run via mock plan
    with patch("agent.planner.gemini_client") as mock_gc:
        mock_gc.generate_plan.return_value = {**VALID_PLAN, "run_id": "will-be-replaced"}
        mock_gc.interpret_request.return_value = {"needs_rag": False}
        with flask_app.test_client() as client:
            resp = client.post("/api/runs", json={
                "request": "Create a note",
                "input_language": "en-IN",
                "response_language": "en-IN",
            })
            assert resp.status_code == 201
            run_id = resp.get_json()["run_id"]

            # Without calling /execute, run should still be 'planned'
            detail = client.get(f"/api/runs/{run_id}").get_json()
            assert detail["run"]["status"] == "planned"
