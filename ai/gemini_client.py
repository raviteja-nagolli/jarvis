"""
ai/gemini_client.py — Gemini reasoning, planning, and tool-calling client.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Optional

from config import config

logger = logging.getLogger(__name__)


class GeminiError(Exception):
    pass


class GeminiClient:
    def __init__(self):
        self._client = None

    def _get_client(self):
        if self._client is None:
            if not config.GEMINI_API_KEY:
                raise GeminiError("GEMINI_API_KEY is not configured")
            from google import genai
            self._client = genai.Client(api_key=config.GEMINI_API_KEY)
        return self._client

    def generate_plan(
        self,
        user_request: str,
        run_id: str,
        input_language: str,
        response_language: str,
        retrieved_context: str = "",
    ) -> dict:
        """
        Ask Gemini to produce a structured JSON execution plan.
        Returns the raw plan dict (caller validates with Pydantic).
        """
        from ai.language_manager import language_instruction
        from tools.registry import all_tool_names

        client = self._get_client()

        tool_list = ", ".join(all_tool_names())
        lang_instr = language_instruction(response_language)
        context_block = (
            f"\n\nRelevant retrieved knowledge:\n{retrieved_context}\n"
            if retrieved_context else ""
        )

        system_prompt = f"""You are JARVIS, an AI execution agent. Your job is to create a structured JSON execution plan.

{lang_instr}

Available tools: {tool_list}

Tool Usage Guide:
- open_app(app_name): Launch desktop applications on host computer. app_name must be 'calculator', 'notes', 'notepad', 'task_manager', 'taskmgr', 'browser', or 'web'.
- open_web(url, query): Open a website URL or perform a web search on Google in the web browser.
- calculate(expression): Evaluate arithmetic expressions safely (+, -, *, /, **, %).
- create_note(title, content): Create and save a persistent note in JARVIS.
- get_notes(query): Retrieve saved notes, optionally searching by keyword.
- create_task(title, description, due_date, priority): Create a task/todo item.
- list_tasks(status, due_date): List existing tasks (status='pending', 'in_progress', 'completed').
- complete_task(task_id): Complete a task by its UUID.
- search_knowledge(query): Search uploaded RAG knowledge documents.

Rules:
- Maximum {config.MAX_AGENT_STEPS} steps.
- Only use tools from the available list.
- dependencies is a list of integer step_numbers this step must wait for (e.g. [1], never string step_ids).
- No circular dependencies.
- Return ONLY valid JSON. No markdown fences, no explanation.
- All user-facing text (title, action_description, summary, expected_result) in the response language.
- Tool names, arguments keys, step_id must stay in English.

Return JSON matching this schema exactly:
{{
  "run_id": "{run_id}",
  "summary": "<short plan summary in response language>",
  "original_request": "<verbatim user request>",
  "input_language": "{input_language}",
  "response_language": "{response_language}",
  "steps": [
    {{
      "step_id": "<unique snake_case id>",
      "step_number": 1,
      "title": "<human-readable title>",
      "action_description": "<what this step does>",
      "tool_name": "<tool_name>",
      "arguments": {{}},
      "dependencies": [],
      "expected_result": "<what success looks like>",
      "verification_strategy": "<how we verify>",
      "status": "planned",
      "attempts": 0
    }}
  ]
}}
{context_block}"""

        try:
            from google.genai import types as genai_types
            response = client.models.generate_content(
                model=config.GEMINI_MODEL,
                contents=user_request,
                config=genai_types.GenerateContentConfig(
                    system_instruction=system_prompt,
                    temperature=0.1,
                    max_output_tokens=4096,
                ),
            )
            raw = response.text or ""
            # Strip markdown fences if Gemini adds them anyway
            raw = raw.strip()
            if raw.startswith("```"):
                raw = raw.split("\n", 1)[1] if "\n" in raw else raw
                if raw.endswith("```"):
                    raw = raw.rsplit("```", 1)[0]
            return json.loads(raw)
        except json.JSONDecodeError as exc:
            raise GeminiError(f"Gemini returned invalid JSON plan: {exc}") from exc
        except Exception as exc:
            raise GeminiError(f"Plan generation failed: {exc}") from exc

    def generate_final_response(
        self,
        user_request: str,
        step_results: list[dict],
        response_language: str,
        retrieved_context: str = "",
    ) -> str:
        """
        Generate the final user-facing response based on actual step outcomes.
        """
        from ai.language_manager import language_instruction

        client = self._get_client()
        lang_instr = language_instruction(response_language)

        results_text = json.dumps(step_results, ensure_ascii=False, indent=2)
        context_block = (
            f"\nRetrieved knowledge:\n{retrieved_context}\n" if retrieved_context else ""
        )

        system_prompt = f"""You are JARVIS. Generate a clear, helpful final response to the user.
{lang_instr}

Base your response ONLY on the actual execution results below. Do not invent actions that were not performed.
If a step failed, acknowledge it honestly. Highlight what was accomplished.
{context_block}"""

        contents = f"""User request: {user_request}

Execution results:
{results_text}

Generate the final response now."""

        try:
            from google.genai import types as genai_types
            response = client.models.generate_content(
                model=config.GEMINI_MODEL,
                contents=contents,
                config=genai_types.GenerateContentConfig(
                    system_instruction=system_prompt,
                    temperature=0.4,
                    max_output_tokens=2048,
                ),
            )
            return response.text or "Execution complete."
        except Exception as exc:
            logger.error("Final response generation failed: %s", exc)
            return "Execution complete. See step results for details."

    def interpret_request(
        self,
        user_request: str,
        input_language: str,
        response_language: str,
    ) -> dict:
        """
        Quick intent analysis before planning.
        Returns {"goal", "needs_rag", "likely_tools", "constraints"}.
        """
        client = self._get_client()
        from tools.registry import all_tool_names

        tool_list = all_tool_names()

        prompt = f"""Analyze this user request and return JSON only:
{{
  "goal": "<one sentence>",
  "needs_rag": <true/false>,
  "likely_tools": ["<tool_name>"],
  "constraints": ["<constraint>"]
}}

Available tools: {tool_list}
Request: {user_request}"""

        try:
            from google.genai import types as genai_types
            response = client.models.generate_content(
                model=config.GEMINI_MODEL,
                contents=prompt,
                config=genai_types.GenerateContentConfig(temperature=0.0, max_output_tokens=512),
            )
            raw = (response.text or "{}").strip()
            if raw.startswith("```"):
                raw = raw.split("\n", 1)[1] if "\n" in raw else raw
                raw = raw.rsplit("```", 1)[0]
            return json.loads(raw)
        except Exception as exc:
            logger.warning("Intent analysis failed: %s", exc)
            return {"goal": user_request, "needs_rag": False, "likely_tools": [], "constraints": []}


# Singleton
gemini_client = GeminiClient()
