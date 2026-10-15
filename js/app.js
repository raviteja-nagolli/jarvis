(() => {
  const API_BASE = window.JARVIS_API_BASE || "";
  const ALLOWED_DOCUMENT_EXTENSIONS = new Set(["pdf", "txt", "md", "markdown"]);
  const MAX_DOCUMENT_BYTES = 20 * 1024 * 1024;
  const elements = Object.fromEntries([
    "request-input", "char-count", "plan-button", "request-error", "plan-section", "plan-summary", "plan-meta", "plan-steps", "plan-status", "plan-actions", "approve-button", "cancel-button", "replan-button", "execution-summary", "response-panel", "response-title", "response-copy", "response-sources", "voice-output", "response-audio", "voice-error", "input-language", "response-language", "auto-speak", "mic-button", "mic-label", "discard-recording", "recording-status", "language-hint", "document-input", "upload-feedback", "document-list", "document-total", "knowledge-count", "refresh-documents", "dropzone", "today-label", "topbar-status-text"
  ].map((id) => [id, document.getElementById(id)]));
  let currentRun = null;
  let recording = false;
  let isBusy = false;
  let config = null;

  JarvisLanguages.populate(elements["input-language"], "en-IN");
  JarvisLanguages.populate(elements["response-language"], "en-IN");
  elements["today-label"].textContent = new Intl.DateTimeFormat("en", { weekday: "short", month: "short", day: "numeric" }).format(new Date()).toUpperCase();

  function setBusy(value) {
    isBusy = value;
    elements["plan-button"].disabled = value;
    elements["approve-button"].disabled = value;
    elements["cancel-button"].disabled = value;
    elements["mic-button"].disabled = value && !recording;
  }

  async function request(path, options = {}) {
    const response = await fetch(`${API_BASE}${path}`, {
      ...options,
      headers: { ...(options.body instanceof FormData ? {} : { "Content-Type": "application/json" }), ...options.headers }
    });
    const contentType = response.headers.get("content-type") || "";
    const result = contentType.includes("application/json") ? await response.json() : await response.text();
    if (!response.ok) {
      const message = typeof result === "object" ? result.error || result.message : result;
      const readableMessage = typeof message === "string" && !message.trimStart().startsWith("<") ? message : "";
      throw new Error(readableMessage || `Request failed (${response.status}).`);
    }
    return result;
  }

  function showRequestError(message) {
    elements["request-error"].textContent = message;
    elements["request-error"].hidden = !message;
  }

  function setCapability(name, value, detail) {
    const dot = document.getElementById(`${name}-dot`);
    const state = document.getElementById(`${name}-state`);
    dot.classList.remove("muted", "offline");
    if (value === true) state.textContent = detail || "Ready";
    else if (value === false) {
      dot.classList.add("offline");
      state.textContent = detail || "Unavailable";
    } else {
      dot.classList.add("muted");
      state.textContent = "Not configured";
    }
  }

  async function loadConfig() {
    try {
      config = await request("/api/config");
      setCapability("api", true, "Connected");
      const voice = config.voice || {};
      setCapability("voice", Boolean(voice.speech_to_text || voice.text_to_speech), voice.status || (voice.speech_to_text || voice.text_to_speech ? "Ready" : "Not configured"));
      setCapability("rag", Boolean(config.rag?.available), config.rag?.status || (config.rag?.available ? "Ready" : "Not configured"));
      const selected = JarvisLanguages.languages.find((language) => language.code === elements["response-language"].value);
      const canSpeak = selected && config.languages?.find((language) => language.code === selected.code)?.text_to_speech === true;
      elements["auto-speak"].disabled = !canSpeak;
      elements["language-hint"].textContent = canSpeak ? "Spoken output is available for this language." : "Text responses are always available. Voice output depends on configured language support.";
      document.querySelector(".status-pulse").classList.add("online");
      elements["topbar-status-text"].textContent = "Backend connected";
    } catch (error) {
      setCapability("api", false, "Offline");
      setCapability("voice", null);
      setCapability("rag", null);
      document.querySelector(".status-pulse").classList.add("offline");
      elements["topbar-status-text"].textContent = "Backend unavailable";
      elements["language-hint"].textContent = "Backend connection required for execution, voice, and document indexing.";
    }
  }

  function switchView(viewName) {
    document.querySelectorAll(".view").forEach((view) => view.classList.toggle("active", view.id === `${viewName}-view`));
    document.querySelectorAll(".nav-link").forEach((button) => button.classList.toggle("active", button.dataset.view === viewName));
    document.getElementById("breadcrumb-current").textContent = viewName === "agent" ? "Agent" : "Knowledge";
  }

  function normalizePlan(result) {
    return result.run || result.plan || result;
  }

  function renderPlan(plan) {
    currentRun = plan;
    elements["plan-section"].hidden = false;
    elements["response-panel"].hidden = true;
    elements["plan-summary"].textContent = plan.summary || plan.title || "Execution plan";
    elements["plan-meta"].replaceChildren();
    [["RUN", plan.run_id || plan.id], ["INPUT", plan.input_language], ["RESPONSE", plan.response_language]].forEach(([label, value]) => {
      if (!value) return;
      const chip = document.createElement("span");
      chip.className = "meta-chip";
      chip.textContent = `${label} · ${value}`;
      elements["plan-meta"].append(chip);
    });
    elements["plan-steps"].replaceChildren();
    (plan.steps || []).forEach((step, index) => {
      const row = document.createElement("article");
      row.className = "plan-step";
      const marker = document.createElement("span");
      marker.className = "step-marker";
      marker.textContent = String(step.sequence ?? index + 1).padStart(2, "0");
      const main = document.createElement("div");
      main.className = "step-main";
      const title = document.createElement("strong");
      title.textContent = step.title || step.action || `Step ${index + 1}`;
      const description = document.createElement("p");
      description.textContent = step.description || step.action_description || step.expected_result || "No additional detail provided.";
      main.append(title, description);
      const tool = document.createElement("span");
      tool.className = "step-tool";
      tool.textContent = step.tool_name || step.tool || "Knowledge";
      tool.title = tool.textContent;
      row.append(marker, main, tool);
      if (step.result || step.error) {
        const result = document.createElement("div");
        result.className = `step-result${step.error ? " error" : ""}`;
        result.textContent = step.error || stringify(step.result);
        row.append(result);
      } else if (step.status && !["pending", "planned", "awaiting_approval"].includes(step.status.toLowerCase())) {
        const status = document.createElement("span");
        status.className = "step-status";
        status.textContent = step.status.replaceAll("_", " ");
        row.append(status);
      }
      elements["plan-steps"].append(row);
    });
    const approved = ["approved", "running", "in_progress", "completed", "succeeded", "failed", "partial"].includes((plan.status || "").toLowerCase());
    elements["approve-button"].hidden = approved || plan.status === "cancelled";
    elements["cancel-button"].hidden = approved || plan.status === "cancelled";
    elements["replan-button"].hidden = approved || plan.status === "cancelled";
    setPlanStatus(plan.status || "awaiting_approval");
    if (approved) renderOutcome(plan);
  }

  function stringify(value) {
    if (typeof value === "string") return value;
    try { return JSON.stringify(value); } catch { return String(value); }
  }

  function setPlanStatus(status) {
    const normalized = String(status).toLowerCase().replaceAll("_", " ");
    elements["plan-status"].textContent = normalized.toUpperCase();
    elements["plan-status"].className = `plan-status${["running", "in progress", "approved"].includes(normalized) ? " running" : ["failed", "partial"].includes(normalized) ? " failed" : ""}`;
  }

  function renderOutcome(run) {
    const status = String(run.status || "").toLowerCase();
    const summary = run.summary || run.message || run.final_response || run.response;
    elements["execution-summary"].hidden = false;
    elements["execution-summary"].classList.toggle("failed", ["failed", "partial", "blocked"].includes(status));
    elements["execution-summary"].textContent = summary ? stringify(summary) : `Run status: ${status.replaceAll("_", " ") || "unknown"}.`;
    if (["completed", "succeeded", "failed", "partial", "blocked"].includes(status) && (run.final_response || run.response)) {
      showResponse(run);
    }
  }

  function showResponse(run) {
    const responseText = run.final_response || run.response;
    const text = typeof responseText === "string" ? responseText : responseText.text || responseText.content;
    if (!text) return;
    elements["response-panel"].hidden = false;
    elements["response-copy"].textContent = text;
    elements["response-title"].textContent = run.status === "completed" || run.status === "succeeded" ? "Verified execution report" : "Execution report · incomplete";
    elements["response-sources"].replaceChildren();
    (run.sources || responseText.sources || []).forEach((source) => {
      const chip = document.createElement("span");
      chip.className = "source-chip";
      chip.textContent = source.title || source.name || source.document_name || "Source";
      elements["response-sources"].append(chip);
    });
    if (elements["auto-speak"].checked) synthesizeResponse(text, run.response_language || elements["response-language"].value);
  }

  async function synthesizeResponse(text, language) {
    elements["voice-output"].hidden = false;
    elements["voice-error"].textContent = "Preparing spoken response…";
    try {
      const response = await fetch(`${API_BASE}/api/voice/synthesize`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text, language })
      });
      if (!response.ok) {
        const error = await response.json().catch(() => ({}));
        throw new Error(error.error || `Voice generation failed (${response.status}).`);
      }
      const type = response.headers.get("content-type") || "";
      let audioBlob;
      if (type.includes("application/json")) {
        const result = await response.json();
        if (result.audio_url) {
          elements["response-audio"].src = result.audio_url;
          elements["voice-error"].textContent = "";
          return;
        }
        const encoded = result.audio_base64 || result.audio;
        if (!encoded) throw new Error("Voice service returned no playable audio.");
        const bytes = Uint8Array.from(atob(encoded), (character) => character.charCodeAt(0));
        audioBlob = new Blob([bytes], { type: result.mime_type || "audio/wav" });
      } else {
        audioBlob = await response.blob();
      }
      elements["response-audio"].src = URL.createObjectURL(audioBlob);
      elements["voice-error"].textContent = "";
    } catch (error) {
      elements["voice-error"].textContent = error.message;
    }
  }

  async function createPlan() {
    const text = elements["request-input"].value.trim();
    if (!text) return showRequestError("Add a request before building a plan.");
    showRequestError("");
    setBusy(true);
    try {
      const result = await request("/api/runs/plan", {
        method: "POST",
        body: JSON.stringify({ request: text, input_language: elements["input-language"].value, response_language: elements["response-language"].value, auto_speak: elements["auto-speak"].checked })
      });
      const plan = normalizePlan(result);
      if (!(plan.run_id || plan.id) || !Array.isArray(plan.steps)) throw new Error("The backend returned an invalid plan.");
      elements["execution-summary"].hidden = true;
      renderPlan(plan);
      elements["plan-section"].scrollIntoView({ behavior: "smooth", block: "nearest" });
    } catch (error) {
      showRequestError(error.message);
    } finally {
      setBusy(false);
    }
  }

  async function pollRun(runId) {
    for (let attempt = 0; attempt < 40; attempt += 1) {
      const run = await request(`/api/runs/${encodeURIComponent(runId)}`);
      const normalized = run.run || run;
      renderPlan(normalized);
      if (["completed", "succeeded", "failed", "partial", "blocked", "cancelled"].includes(String(normalized.status).toLowerCase())) return;
      await new Promise((resolve) => window.setTimeout(resolve, 1500));
    }
    throw new Error("Execution is still running. Refresh the run to check its latest status.");
  }

  async function approvePlan() {
    const runId = currentRun?.run_id || currentRun?.id;
    if (!runId) return;
    setBusy(true);
    setPlanStatus("running");
    elements["execution-summary"].hidden = false;
    elements["execution-summary"].textContent = "Approval sent. Waiting for backend execution and verification…";
    try {
      const result = await request(`/api/runs/${encodeURIComponent(runId)}/approve`, { method: "POST", body: JSON.stringify({ approved: true }) });
      const run = result.run || result;
      renderPlan(run);
      if (!["completed", "succeeded", "failed", "partial", "blocked", "cancelled"].includes(String(run.status).toLowerCase())) await pollRun(runId);
    } catch (error) {
      elements["execution-summary"].hidden = false;
      elements["execution-summary"].classList.add("failed");
      elements["execution-summary"].textContent = `Execution status could not be confirmed: ${error.message}`;
      setPlanStatus("status unknown");
    } finally {
      setBusy(false);
    }
  }

  async function cancelPlan() {
    const runId = currentRun?.run_id || currentRun?.id;
    if (!runId) return;
    setBusy(true);
    try {
      const result = await request(`/api/runs/${encodeURIComponent(runId)}/cancel`, { method: "POST", body: JSON.stringify({}) });
      renderPlan(result.run || result);
    } catch (error) {
      showRequestError(`Could not cancel the plan: ${error.message}`);
    } finally {
      setBusy(false);
    }
  }

  async function toggleRecording() {
    if (recording) {
      elements["mic-label"].textContent = "Processing";
      elements["mic-button"].classList.remove("recording");
      try {
        const blob = await JarvisVoice.stop();
        recording = false;
        elements["discard-recording"].hidden = true;
        elements["mic-button"].setAttribute("aria-label", "Record voice request");
        if (!blob) {
          elements["recording-status"].textContent = "No audio captured.";
          elements["mic-label"].textContent = "Speak";
          return;
        }
        elements["recording-status"].textContent = "Sending audio for transcription…";
        const form = new FormData();
        form.append("audio", blob, `request.${blob.type.includes("ogg") ? "ogg" : blob.type.includes("mp4") ? "mp4" : "webm"}`);
        form.append("input_language", elements["input-language"].value);
        const result = await request("/api/voice/transcribe", { method: "POST", body: form });
        if (!result.transcript) throw new Error("Speech service returned no transcript.");
        elements["request-input"].value = result.transcript;
        elements["char-count"].textContent = `${result.transcript.length} / 4000`;
        if (result.language) elements["recording-status"].textContent = `Recognized · ${result.language}${result.request_id ? ` · ${result.request_id}` : ""}. Edit the transcript before planning.`;
        else elements["recording-status"].textContent = "Transcript ready. Review or edit it before planning.";
      } catch (error) {
        elements["recording-status"].textContent = error.message;
      } finally {
        elements["mic-label"].textContent = "Speak";
      }
      return;
    }
    try {
      await JarvisVoice.start(
        (message) => { elements["recording-status"].textContent = message; },
        () => { if (recording) toggleRecording(); }
      );
      recording = true;
      elements["mic-label"].textContent = "Stop";
      elements["mic-button"].classList.add("recording");
      elements["mic-button"].setAttribute("aria-label", "Stop voice recording");
      elements["discard-recording"].hidden = false;
    } catch (error) {
      elements["recording-status"].textContent = error.message;
    }
  }

  async function loadDocuments() {
    try {
      const result = await request("/api/knowledge/documents");
      const documents = result.documents || [];
      elements["document-total"].textContent = String(documents.length);
      elements["knowledge-count"].textContent = String(documents.length);
      elements["document-list"].replaceChildren();
      if (!documents.length) {
        const empty = document.createElement("div");
        empty.className = "empty-documents";
        empty.innerHTML = '<span class="empty-mark">▤</span><strong>Your library is clear.</strong><span>Uploaded knowledge will appear here with its indexing status.</span>';
        elements["document-list"].append(empty);
        return;
      }
      documents.forEach((documentRecord) => {
        const row = document.createElement("article");
        row.className = "document-row";
        const mark = document.createElement("span");
        mark.className = "file-mark";
        mark.textContent = (documentRecord.mime_type || documentRecord.filename || "FILE").split(/[./]/).pop().slice(0, 4).toUpperCase();
        const main = document.createElement("div");
        main.className = "document-main";
        const title = document.createElement("strong");
        title.textContent = documentRecord.title || documentRecord.filename || "Untitled document";
        const info = document.createElement("small");
        info.textContent = documentRecord.updated_at || documentRecord.created_at || "Added to library";
        main.append(title, info);
        const status = document.createElement("span");
        const state = String(documentRecord.status || documentRecord.indexing_status || "unknown").toLowerCase();
        status.className = `document-status${state === "ready" || state === "indexed" ? " ready" : state === "failed" || state === "error" ? " failed" : ""}`;
        status.textContent = state.replaceAll("_", " ");
        row.append(mark, main, status);
        elements["document-list"].append(row);
      });
    } catch (error) {
      elements["document-list"].replaceChildren();
      const message = document.createElement("div");
      message.className = "empty-documents";
      const title = document.createElement("strong");
      title.textContent = "Document service unavailable.";
      const detail = document.createElement("span");
      detail.textContent = error.message;
      message.append(title, detail);
      elements["document-list"].append(message);
    }
  }

  async function uploadDocument(file) {
    if (!file) return;
    const extension = file.name.split(".").pop().toLowerCase();
    if (!ALLOWED_DOCUMENT_EXTENSIONS.has(extension)) {
      elements["upload-feedback"].className = "upload-feedback error";
      elements["upload-feedback"].textContent = "Unsupported format. Choose a PDF, TXT, or Markdown document.";
      return;
    }
    if (file.size > MAX_DOCUMENT_BYTES) {
      elements["upload-feedback"].className = "upload-feedback error";
      elements["upload-feedback"].textContent = "This document exceeds the 20 MB upload limit.";
      return;
    }
    elements["upload-feedback"].className = "upload-feedback";
    elements["upload-feedback"].textContent = `Uploading ${file.name}…`;
    const form = new FormData();
    form.append("file", file);
    try {
      const result = await request("/api/knowledge/documents", { method: "POST", body: form });
      const documentRecord = result.document || result;
      elements["upload-feedback"].textContent = `${documentRecord.title || file.name} · ${documentRecord.status || documentRecord.indexing_status || "received"}. Ready status will appear after indexing completes.`;
      await loadDocuments();
    } catch (error) {
      elements["upload-feedback"].className = "upload-feedback error";
      elements["upload-feedback"].textContent = error.message;
    } finally {
      elements["document-input"].value = "";
    }
  }

  document.querySelectorAll(".nav-link").forEach((button) => button.addEventListener("click", () => switchView(button.dataset.view)));
  elements["request-input"].addEventListener("input", () => { elements["char-count"].textContent = `${elements["request-input"].value.length} / 4000`; });
  elements["plan-button"].addEventListener("click", createPlan);
  elements["approve-button"].addEventListener("click", approvePlan);
  elements["cancel-button"].addEventListener("click", cancelPlan);
  elements["replan-button"].addEventListener("click", () => { elements["plan-section"].hidden = true; elements["request-input"].focus(); });
  elements["mic-button"].addEventListener("click", toggleRecording);
  elements["discard-recording"].addEventListener("click", () => {
    JarvisVoice.cancel();
    recording = false;
    elements["mic-button"].classList.remove("recording");
    elements["mic-button"].setAttribute("aria-label", "Record voice request");
    elements["mic-label"].textContent = "Speak";
    elements["discard-recording"].hidden = true;
    elements["recording-status"].textContent = "Recording discarded.";
  });
  elements["document-input"].addEventListener("change", (event) => uploadDocument(event.target.files[0]));
  elements["refresh-documents"].addEventListener("click", loadDocuments);
  elements["response-language"].addEventListener("change", () => {
    const supported = config?.languages?.find((language) => language.code === elements["response-language"].value)?.text_to_speech === true;
    elements["auto-speak"].disabled = !supported;
    if (!supported) elements["auto-speak"].checked = false;
    elements["language-hint"].textContent = supported ? "Spoken output is available for this language." : "Text responses are always available. Voice output depends on configured language support.";
  });
  elements.dropzone.addEventListener("dragover", (event) => { event.preventDefault(); elements.dropzone.classList.add("dragover"); });
  elements.dropzone.addEventListener("dragleave", () => elements.dropzone.classList.remove("dragover"));
  elements.dropzone.addEventListener("drop", (event) => {
    event.preventDefault();
    elements.dropzone.classList.remove("dragover");
    uploadDocument(event.dataTransfer.files[0]);
  });

  loadConfig();
  loadDocuments();
})();