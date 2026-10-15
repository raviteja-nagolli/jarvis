"""
app.py — JARVIS Flask application entry point.

All API routes are defined here. Business logic lives in agent/, ai/, tools/.
"""
from __future__ import annotations

import json
import logging
import os
import tempfile
import uuid
from pathlib import Path

from flask import Flask, jsonify, render_template, request, send_file, send_from_directory
from flask_cors import CORS

from config import config

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.DEBUG if config.DEBUG else logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# ── App factory ───────────────────────────────────────────────────────────────
app = Flask(__name__, template_folder="templates", static_folder="static")
CORS(app)
app.secret_key = config.SECRET_KEY
app.config["MAX_CONTENT_LENGTH"] = config.MAX_AUDIO_UPLOAD_MB * 1024 * 1024

# Initialise DB
config.ensure_instance_dir()
from database.db import init_db
init_db()

# Audio temp directory
_AUDIO_DIR = Path("instance/audio_tmp")
_AUDIO_DIR.mkdir(parents=True, exist_ok=True)


# ── Helpers ───────────────────────────────────────────────────────────────────

def ok(data: dict | list, status: int = 200):
    return jsonify({"ok": True, **data} if isinstance(data, dict) else {"ok": True, "data": data}), status


def err(message: str, status: int = 400, details: dict = None):
    body = {"ok": False, "error": message}
    if details:
        body["details"] = details
    return jsonify(body), status


def _parse_json_body() -> dict:
    """Parse JSON body; raise ValueError on failure."""
    body = request.get_json(silent=True)
    if body is None:
        raise ValueError("Request body must be valid JSON")
    return body


# ══════════════════════════════════════════════════════════════════════════════
# Root / Frontend Serving
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/")
def index():
    # Priority: root index.html, templates/index.html, static/index.html
    root_index = Path("index.html")
    if root_index.is_file():
        return send_file(str(root_index))

    tmpl_index = Path(app.template_folder) / "index.html"
    if tmpl_index.is_file():
        return render_template("index.html")

    static_index = Path(app.static_folder) / "index.html"
    if static_index.is_file():
        return send_from_directory(app.static_folder, "index.html")

    return ok({
        "name": "JARVIS Multilingual AI Execution Agent API",
        "status": "online",
        "version": "1.0.0",
        "endpoints": {
            "health": "/api/health",
            "config": "/api/config",
            "languages": "/api/languages",
            "runs": "/api/runs",
            "notes": "/api/notes",
            "tasks": "/api/tasks",
            "knowledge": "/api/knowledge/documents",
            "knowledge_status": "/api/knowledge/status",
            "knowledge_query": "/api/knowledge/query",
            "transcribe": "/api/voice/transcribe",
            "synthesize": "/api/voice/synthesize",
        },
        "docs": "Backend API is ready. Frontend is integrated."
    })


@app.get("/css/<path:filename>")
def serve_css(filename):
    css_dir = Path("css")
    if css_dir.is_dir() and (css_dir / filename).is_file():
        return send_from_directory("css", filename)
    static_css = Path(app.static_folder) / "css"
    if static_css.is_dir() and (static_css / filename).is_file():
        return send_from_directory(static_css, filename)
    return err("CSS file not found", 404)


@app.get("/js/<path:filename>")
def serve_js(filename):
    js_dir = Path("js")
    if js_dir.is_dir() and (js_dir / filename).is_file():
        return send_from_directory("js", filename)
    static_js = Path(app.static_folder) / "js"
    if static_js.is_dir() and (static_js / filename).is_file():
        return send_from_directory(static_js, filename)
    return err("JS file not found", 404)


# ══════════════════════════════════════════════════════════════════════════════
# Health & Config
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/api/health")
def health():
    return ok({
        "status": "ok",
        "integrations": config.integration_status(),
        "version": "1.0.0",
    })


@app.get("/api/config")
def api_config():
    from ai.language_manager import all_languages
    langs = all_languages()
    lang_list = [
        {
            "code": l["locale"],
            "name": l["display_name"],
            "locale": l["locale"],
            "speech_to_text": l["stt_available"] and bool(config.SARVAM_API_KEY),
            "text_to_speech": l["tts_available"] and bool(config.SARVAM_API_KEY),
        }
        for l in langs
    ]
    return ok({
        "api": {
            "status": "online",
            "version": "1.0.0",
        },
        "voice": {
            "speech_to_text": bool(config.SARVAM_API_KEY),
            "text_to_speech": bool(config.SARVAM_API_KEY),
            "status": "Ready" if config.SARVAM_API_KEY else "Not configured",
            "stt_model": config.SARVAM_STT_MODEL,
            "tts_model": config.SARVAM_TTS_MODEL,
        },
        "rag": {
            "available": bool(config.GEMINI_API_KEY),
            "status": "Ready" if config.GEMINI_API_KEY else "Not configured",
        },
        "languages": lang_list,
        "default_language": config.DEFAULT_LANGUAGE,
    })


# ══════════════════════════════════════════════════════════════════════════════
# Languages
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/api/languages")
def get_languages():
    from ai.language_manager import all_languages
    return ok({"languages": all_languages()})


# ══════════════════════════════════════════════════════════════════════════════
# ══════════════════════════════════════════════════════════════════════════════
# Voice — Transcription
# ══════════════════════════════════════════════════════════════════════════════

@app.post("/api/voice/transcribe")
def transcribe():
    if not config.SARVAM_API_KEY:
        return err("Sarvam API key not configured", 503)

    if "audio" not in request.files:
        return err("Multipart field 'audio' is required")

    audio_file = request.files["audio"]
    language_code = (
        request.form.get("language_code")
        or request.form.get("input_language")
        or "unknown"
    )

    audio_bytes = audio_file.read()
    if len(audio_bytes) == 0:
        return err("Audio file is empty")

    max_bytes = config.MAX_AUDIO_UPLOAD_MB * 1024 * 1024
    if len(audio_bytes) > max_bytes:
        return err(f"Audio exceeds {config.MAX_AUDIO_UPLOAD_MB} MB limit")

    content_type = audio_file.content_type or "audio/webm"

    from ai.sarvam_voice import transcribe_audio
    result = transcribe_audio(
        audio_bytes=audio_bytes,
        content_type=content_type,
        language_code=language_code,
    )

    if result["success"]:
        return ok({
            "transcript": result["transcript"],
            "language": result["language_code"],
            "language_code": result["language_code"],
            "request_id": result.get("request_id"),
        })
    return err(result["error"] or "Transcription failed", 502)


# ══════════════════════════════════════════════════════════════════════════════
# Voice — Text-to-speech / Synthesize
# ══════════════════════════════════════════════════════════════════════════════

@app.post("/api/voice/speak")
@app.post("/api/voice/synthesize")
def speak():
    if not config.SARVAM_API_KEY:
        return err("Sarvam API key not configured", 503)

    try:
        body = _parse_json_body()
    except ValueError as exc:
        return err(str(exc))

    text = (body.get("text") or "").strip()
    if not text:
        return err("'text' field is required")

    language_code = body.get("language_code") or body.get("language") or config.DEFAULT_LANGUAGE
    speaker = body.get("speaker")

    from ai.sarvam_voice import synthesize_speech
    result = synthesize_speech(text=text, language_code=language_code, speaker=speaker)

    if not result["success"]:
        return err(result["error"] or "Speech synthesis failed", 502)

    # Save to temp file and serve
    audio_bytes = result["audio_bytes"]
    fname = f"{uuid.uuid4()}.wav"
    fpath = _AUDIO_DIR / fname
    fpath.write_bytes(audio_bytes)

    return send_file(str(fpath), mimetype="audio/wav", as_attachment=False)


# ══════════════════════════════════════════════════════════════════════════════
# Agent Runs
# ══════════════════════════════════════════════════════════════════════════════

@app.post("/api/runs")
@app.post("/api/runs/plan")
def create_run():
    try:
        body = _parse_json_body()
    except ValueError as exc:
        return err(str(exc))

    user_request = (body.get("request") or "").strip()
    if not user_request:
        return err("'request' field is required")

    input_language = body.get("input_language", config.DEFAULT_LANGUAGE)
    response_language = body.get("response_language", config.DEFAULT_LANGUAGE)

    from ai.language_manager import resolve_language
    input_language = resolve_language(input_language)
    response_language = resolve_language(response_language)

    from database.db import create_run as db_create_run, update_run, create_step
    run_id = db_create_run(user_request, input_language, response_language)

    # Optional: pre-fetch RAG context if request needs knowledge
    retrieved_context = ""
    try:
        from ai.gemini_client import gemini_client
        intent = gemini_client.interpret_request(user_request, input_language, response_language)
        if intent.get("needs_rag") and config.GEMINI_API_KEY:
            from ai.rag_client import rag_client
            rag_result = rag_client.query(user_request)
            if rag_result["success"] and rag_result["answer"]:
                retrieved_context = rag_result["answer"]
    except Exception as exc:
        logger.warning("Pre-planning RAG skipped: %s", exc)

    # Generate plan
    from agent.planner import generate_plan, PlannerError
    try:
        plan = generate_plan(
            user_request=user_request,
            run_id=run_id,
            input_language=input_language,
            response_language=response_language,
            retrieved_context=retrieved_context,
        )
    except PlannerError as exc:
        update_run(run_id, status="failed",
                   final_report_json=json.dumps({"error": str(exc)}))
        return err(f"Planning failed: {exc}", 422)

    # Persist plan and steps
    plan_dict = plan.model_dump()
    update_run(run_id, plan_json=plan_dict)

    for step in plan.steps:
        create_step(run_id, {
            "step_number": step.step_number,
            "title": step.title,
            "tool_name": step.tool_name,
            "arguments": step.arguments,
            "dependencies": step.dependencies,
            "expected_result": step.expected_result,
        })

    run_response = {
        **plan_dict,
        "run_id": run_id,
        "id": run_id,
        "status": "awaiting_approval",
        "summary": plan.summary,
        "title": plan.summary,
        "input_language": input_language,
        "response_language": response_language,
        "steps": plan_dict.get("steps", []),
    }
    return ok({"run_id": run_id, "id": run_id, "plan": run_response, "run": run_response}, 201)


@app.post("/api/runs/<run_id>/execute")
@app.post("/api/runs/<run_id>/approve")
def execute_run(run_id: str):
    from database.db import get_run
    run = get_run(run_id)
    if not run:
        return err("Run not found", 404)
    if run["status"] not in ("planned", "awaiting_approval", "pending"):
        return err(f"Run is not in 'planned' state (current: {run['status']})", 409)

    plan_json = run.get("plan_json")
    if not plan_json:
        return err("Run has no plan", 422)

    plan_data = json.loads(plan_json) if isinstance(plan_json, str) else plan_json

    from agent.schemas import ExecutionPlan
    from pydantic import ValidationError
    try:
        plan = ExecutionPlan(**plan_data)
    except ValidationError as exc:
        return err(f"Stored plan is invalid: {exc}", 422)

    from agent.orchestrator import submit_run
    submit_run(run_id, plan)

    run_dict = dict(run)
    run_dict["status"] = "running"
    run_dict["run_id"] = run_id
    run_dict["id"] = run_id
    if plan_data.get("steps"):
        run_dict["steps"] = plan_data.get("steps")

    return ok({"run_id": run_id, "status": "running", "run": run_dict})


@app.get("/api/runs/<run_id>")
def get_run_detail(run_id: str):
    from database.db import get_run, get_steps, get_run_events
    run = get_run(run_id)
    if not run:
        return err("Run not found", 404)

    run_dict = dict(run)
    # Parse JSON fields
    for field in ("plan_json", "final_report_json"):
        val = run_dict.get(field)
        if val and isinstance(val, str):
            try:
                run_dict[field] = json.loads(val)
            except Exception:
                pass

    steps = get_steps(run_id)
    formatted_steps = []
    for step in steps:
        step_dict = dict(step)
        for field in ("arguments_json", "dependencies_json", "output_json", "verification_json"):
            val = step_dict.get(field)
            if val and isinstance(val, str):
                try:
                    step_dict[field] = json.loads(val)
                except Exception:
                    pass
        step_dict["sequence"] = step_dict.get("step_number")
        step_dict["description"] = step_dict.get("expected_result")
        step_dict["result"] = step_dict.get("output_json")
        formatted_steps.append(step_dict)

    events = get_run_events(run_id)
    for ev in events:
        val = ev.get("details_json")
        if val and isinstance(val, str):
            try:
                ev["details_json"] = json.loads(val)
            except Exception:
                pass

    final_rep = run_dict.get("final_report_json")
    if isinstance(final_rep, dict):
        run_dict["summary"] = final_rep.get("summary") or run_dict.get("summary")
        run_dict["final_response"] = final_rep.get("summary")
        run_dict["response"] = final_rep.get("summary")

    run_dict["steps"] = formatted_steps
    run_dict["id"] = run_id
    run_dict["run_id"] = run_id

    return ok({"run": run_dict, "steps": formatted_steps, "events": events})


@app.get("/api/runs")
def list_runs():
    from database.db import get_recent_runs
    runs = get_recent_runs(limit=30)
    for r in runs:
        for f in ("plan_json", "final_report_json"):
            val = r.get(f)
            if val and isinstance(val, str):
                try:
                    r[f] = json.loads(val)
                except Exception:
                    pass
    return ok({"runs": runs})


@app.post("/api/runs/<run_id>/cancel")
def cancel_run(run_id: str):
    from database.db import get_run
    run = get_run(run_id)
    if not run:
        return err("Run not found", 404)

    from agent.orchestrator import cancel_run as orch_cancel
    flagged = orch_cancel(run_id)
    run_dict = dict(run)
    run_dict["status"] = "cancelled"
    run_dict["id"] = run_id
    run_dict["run_id"] = run_id
    return ok({"run_id": run_id, "cancel_requested": flagged, "run": run_dict})


# ══════════════════════════════════════════════════════════════════════════════
# Notes
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/api/notes")
def list_notes():
    from database.db import get_notes
    query = request.args.get("q", "")
    notes = get_notes(query=query)
    return ok({"notes": notes})


@app.post("/api/notes")
def api_create_note():
    try:
        body = _parse_json_body()
    except ValueError as exc:
        return err(str(exc))

    try:
        from tools.notes_tool import create_note
        result = create_note(
            title=body.get("title", ""),
            content=body.get("content", ""),
        )
        return ok(result, 201)
    except ValueError as exc:
        return err(str(exc))


# ══════════════════════════════════════════════════════════════════════════════
# Tasks
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/api/tasks")
def list_tasks_route():
    status = request.args.get("status", "")
    due_date = request.args.get("due_date", "")
    from tools.tasks_tool import list_tasks
    try:
        result = list_tasks(status=status, due_date=due_date)
        return ok(result)
    except ValueError as exc:
        return err(str(exc))


@app.post("/api/tasks")
def api_create_task():
    try:
        body = _parse_json_body()
    except ValueError as exc:
        return err(str(exc))

    try:
        from tools.tasks_tool import create_task
        result = create_task(
            title=body.get("title", ""),
            description=body.get("description", ""),
            due_date=body.get("due_date", ""),
            priority=body.get("priority", "medium"),
        )
        return ok(result, 201)
    except ValueError as exc:
        return err(str(exc))


@app.post("/api/tasks/<task_id>/complete")
def api_complete_task(task_id: str):
    from tools.tasks_tool import complete_task, verify_task_completed
    try:
        result = complete_task(task_id)
        verification = verify_task_completed(task_id)
        return ok({"task_id": task_id, "updated": result["updated"],
                   "verification": verification})
    except ValueError as exc:
        return err(str(exc), 404)


# ══════════════════════════════════════════════════════════════════════════════
# Knowledge / RAG
# ══════════════════════════════════════════════════════════════════════════════

_ALLOWED_MIME_TYPES = {
    "application/pdf": ".pdf",
    "text/plain": ".txt",
    "text/markdown": ".md",
    "text/x-markdown": ".md",
}


@app.post("/api/knowledge/upload")
@app.post("/api/knowledge/documents")
def upload_knowledge():
    if not config.GEMINI_API_KEY:
        return err("Gemini API key not configured — RAG unavailable", 503)

    if "file" not in request.files:
        return err("Multipart field 'file' is required")

    f = request.files["file"]
    mime = f.content_type or "application/octet-stream"
    clean_mime = mime.split(";")[0].strip()

    ext = Path(f.filename or "").suffix.lower()
    if clean_mime not in _ALLOWED_MIME_TYPES:
        if ext in (".pdf", ".txt", ".md", ".markdown"):
            clean_mime = "application/pdf" if ext == ".pdf" else "text/markdown" if ext in (".md", ".markdown") else "text/plain"
        else:
            return err(
                f"Unsupported file type '{clean_mime}'. "
                f"Allowed: {list(_ALLOWED_MIME_TYPES)}"
            )

    file_bytes = f.read()
    if len(file_bytes) == 0:
        return err("Uploaded file is empty")
    if len(file_bytes) > 20 * 1024 * 1024:
        return err("File exceeds 20 MB limit")

    display_name = f.filename or "document"

    from database.db import create_knowledge_doc, update_knowledge_doc
    doc_id = create_knowledge_doc(filename=f.filename, display_name=display_name)

    # Upload to Gemini Files API
    from ai.rag_client import rag_client
    upload_result = rag_client.upload_document(file_bytes, display_name, clean_mime)

    if not upload_result["success"]:
        update_knowledge_doc(doc_id, status="failed", error=upload_result["error"])
        return err(f"Upload failed: {upload_result['error']}", 502)

    file_name = upload_result["file_name"]
    update_knowledge_doc(doc_id,
                         file_search_document_id=file_name,
                         status="indexing")

    # Add to File Search store
    store_result = rag_client.add_to_store(file_name)
    if store_result.get("success"):
        now = __import__("database.db", fromlist=["_utcnow"])._utcnow()
        update_knowledge_doc(doc_id, status="ready", indexed_at=now)
    else:
        update_knowledge_doc(doc_id, status="failed",
                             error=store_result.get("error", "Store indexing failed"))
        return err(f"Indexing failed: {store_result.get('error')}", 502)

    doc_info = {"id": doc_id, "doc_id": doc_id, "title": display_name, "display_name": display_name, "status": "ready"}
    return ok({"doc_id": doc_id, "display_name": display_name, "title": display_name, "status": "ready", "document": doc_info}, 201)


@app.get("/api/knowledge/documents")
def list_knowledge_docs():
    from database.db import get_knowledge_docs
    docs = get_knowledge_docs()
    formatted = []
    for d in docs:
        d_dict = dict(d)
        d_dict["title"] = d_dict.get("display_name") or d_dict.get("filename")
        d_dict["id"] = d_dict.get("doc_id")
        formatted.append(d_dict)
    return ok({"documents": formatted})


@app.get("/api/knowledge/status")
def knowledge_status():
    if not config.GEMINI_API_KEY:
        return ok({"available": False, "reason": "GEMINI_API_KEY not configured"})
    try:
        from ai.rag_client import rag_client
        files = rag_client.list_files()
        return ok({"available": True, "indexed_file_count": len(files)})
    except Exception as exc:
        return ok({"available": False, "reason": str(exc)})


@app.delete("/api/knowledge/documents/<doc_id>")
def delete_knowledge_doc(doc_id: str):
    from database.db import get_knowledge_doc, update_knowledge_doc
    doc = get_knowledge_doc(doc_id)
    if not doc:
        return err("Document not found", 404)

    file_name = doc.get("file_search_document_id")
    if file_name and config.GEMINI_API_KEY:
        from ai.rag_client import rag_client
        del_result = rag_client.delete_file(file_name)
        if not del_result["success"]:
            logger.warning("Gemini file delete failed: %s", del_result["error"])

    update_knowledge_doc(doc_id, status="deleted")
    return ok({"doc_id": doc_id, "deleted": True})


@app.post("/api/knowledge/query")
def query_knowledge():
    try:
        body = _parse_json_body()
    except ValueError as exc:
        return err(str(exc))

    question = (body.get("question") or "").strip()
    if not question:
        return err("'question' field is required")

    if not config.GEMINI_API_KEY:
        return err("Gemini API key not configured", 503)

    from ai.rag_client import rag_client
    result = rag_client.query(question, scope=body.get("scope"))
    if result["success"]:
        return ok({"answer": result["answer"], "sources": result["sources"]})
    return err(result["error"] or "Query failed", 502)


# ══════════════════════════════════════════════════════════════════════════════
# Error handlers
# ══════════════════════════════════════════════════════════════════════════════

@app.errorhandler(404)
def not_found(_e):
    return err("Endpoint not found", 404)


@app.errorhandler(405)
def method_not_allowed(_e):
    return err("Method not allowed", 405)


@app.errorhandler(413)
def too_large(_e):
    return err(f"Payload too large (max {config.MAX_AUDIO_UPLOAD_MB} MB)", 413)


@app.errorhandler(500)
def internal_error(e):
    logger.exception("Unhandled exception")
    return err("Internal server error", 500)


# ── Main ──────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=config.DEBUG)
