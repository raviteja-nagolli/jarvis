# JARVIS Frontend

Static HTML, CSS, and vanilla JavaScript frontend. No frontend build step is required. Serve this directory from the Flask application or a local static server. For a separate frontend origin, configure Flask CORS for that origin and set `window.JARVIS_API_BASE` before loading `js/app.js` to the backend URL. The default API base is the current origin.

## Flask API contract

All JSON endpoints return an object. Errors should use an appropriate HTTP error status and `{ "error": "Human-readable explanation" }`. The UI does not treat an accepted upload or an unverified tool result as success.

| Method | Path | Request | Response shape |
| --- | --- | --- | --- |
| GET | `/api/config` | — | `{ "voice": { "speech_to_text": true, "text_to_speech": true, "status": "Ready" }, "rag": { "available": true, "status": "Ready" }, "languages": [{ "code": "en-IN", "text_to_speech": true }] }` |
| POST | `/api/runs/plan` | `{ "request", "input_language", "response_language", "auto_speak" }` | `{ "run": { "run_id", "summary", "status": "awaiting_approval", "input_language", "response_language", "steps": [{ "sequence", "title", "description", "tool_name", "status" }] } }` |
| POST | `/api/runs/{run_id}/approve` | `{ "approved": true }` | `{ "run": { ...run fields, "status", "steps", "final_response", "sources" } }` |
| POST | `/api/runs/{run_id}/cancel` | `{}` | `{ "run": { ...run fields, "status": "cancelled" } }` |
| GET | `/api/runs/{run_id}` | — | `{ "run": { ...latest run and verified step results } }` |
| POST | `/api/voice/transcribe` | multipart fields `audio` and `input_language` | `{ "transcript", "language", "request_id" }` |
| POST | `/api/voice/synthesize` | `{ "text", "language" }` | Audio bytes with an audio content type, or `{ "audio_base64", "mime_type" }` / `{ "audio_url" }` |
| GET | `/api/knowledge/documents` | — | `{ "documents": [{ "title", "filename", "status", "created_at" }] }` |
| POST | `/api/knowledge/documents` | multipart field `file` | `{ "document": { "title", "filename", "status", "created_at" } }` |

Run status values should remain language-independent, for example `awaiting_approval`, `running`, `completed`, `failed`, `partial`, `blocked`, and `cancelled`. Include `final_response` only after execution has finished; include source names only when returned by retrieval. Document status should reflect actual indexing completion (`ready` or `indexed`), not merely upload acceptance.

The UI supports English, Kannada, Hindi, Tamil, and Telugu selection. Actual speech-recognition and speech-synthesis availability must come from backend configuration; text responses remain usable when TTS is unavailable. Browser recording is capped at 30 seconds and 15 MB; knowledge uploads are limited to PDF, TXT, and Markdown up to 20 MB.