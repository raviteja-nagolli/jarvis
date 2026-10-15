(() => {
  const API_BASE = window.JARVIS_API_BASE || "";
  const ALLOWED_DOCUMENT_EXTENSIONS = new Set(["pdf", "txt", "md", "markdown"]);
  const MAX_DOCUMENT_BYTES = 20 * 1024 * 1024;
  const elements = Object.fromEntries([
    "request-input", "char-count", "plan-button", "request-error", "plan-section",
    "plan-summary", "plan-meta", "plan-steps", "plan-status", "plan-actions",
    "approve-button", "cancel-button", "replan-button", "execution-summary",
    "response-panel", "response-title", "response-copy", "response-sources",
    "voice-output", "response-audio", "voice-error", "input-language",
    "response-language", "auto-speak", "auto-approve-voice", "mic-button",
    "mic-label", "voice-convo-button", "voice-convo-label", "discard-recording",
    "recording-status", "language-hint", "document-input", "upload-feedback",
    "document-list", "document-total", "knowledge-count", "refresh-documents",
    "dropzone", "today-label", "topbar-status-text"
  ].map((id) => [id, document.getElementById(id)]));

  let currentRun = null;
  let recording = false;
  let speechRecognitionActive = false;
  let voiceConversationMode = false;
  let isBusy = false;
  let config = null;

  JarvisLanguages.populate(elements["input-language"], "en-IN");
  JarvisLanguages.populate(elements["response-language"], "en-IN");
  if (elements["today-label"]) {
    elements["today-label"].textContent = new Intl.DateTimeFormat("en", {
      weekday: "short",
      month: "short",
      day: "numeric"
    }).format(new Date()).toUpperCase();
  }

  function setBusy(value) {
    isBusy = value;
    if (elements["plan-button"]) elements["plan-button"].disabled = value;
    if (elements["approve-button"]) elements["approve-button"].disabled = value;
    if (elements["cancel-button"]) elements["cancel-button"].disabled = value;
    if (elements["mic-button"]) elements["mic-button"].disabled = value && !recording && !speechRecognitionActive;
    if (elements["voice-convo-button"]) elements["voice-convo-button"].disabled = value && !voiceConversationMode;
  }

  async function request(path, options = {}) {
    const response = await fetch(`${API_BASE}${path}`, {
      ...options,
      headers: {
        ...(options.body instanceof FormData ? {} : { "Content-Type": "application/json" }),
        ...options.headers
      }
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
    if (elements["request-error"]) {
      elements["request-error"].textContent = message;
      elements["request-error"].hidden = !message;
    }
  }

  function setCapability(name, value, detail) {
    const dot = document.getElementById(`${name}-dot`);
    const state = document.getElementById(`${name}-state`);
    if (!dot || !state) return;
    dot.classList.remove("muted", "offline");
    if (value === true) {
      state.textContent = detail || "Ready";
    } else if (value === false) {
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
      const hasVoice = Boolean(voice.speech_to_text || voice.text_to_speech)
        || JarvisVoice.hasSpeechRecognition()
        || Boolean(window.speechSynthesis);

      setCapability(
        "voice",
        hasVoice,
        hasVoice ? "Ready (English + Indic)" : "Not configured"
      );
      setCapability(
        "rag",
        Boolean(config.rag?.available),
        config.rag?.status || (config.rag?.available ? "Ready" : "Not configured")
      );

      if (elements["auto-speak"]) {
        elements["auto-speak"].disabled = false;
      }
      if (elements["language-hint"]) {
        elements["language-hint"].textContent =
          "English voice conversation & multilingual speech synthesis ready.";
      }
      const pulse = document.querySelector(".status-pulse");
      if (pulse) pulse.classList.add("online");
      if (elements["topbar-status-text"]) {
        elements["topbar-status-text"].textContent = "Backend connected";
      }
    } catch (error) {
      setCapability("api", false, "Offline");
      setCapability("voice", null);
      setCapability("rag", null);
      const pulse = document.querySelector(".status-pulse");
      if (pulse) pulse.classList.add("offline");
      if (elements["topbar-status-text"]) {
        elements["topbar-status-text"].textContent = "Backend unavailable";
      }
      if (elements["language-hint"]) {
        elements["language-hint"].textContent =
          "Backend connection required for execution, voice, and document indexing.";
      }
    }
  }

  function switchView(viewName) {
    document.querySelectorAll(".view").forEach((view) =>
      view.classList.toggle("active", view.id === `${viewName}-view`)
    );
    document.querySelectorAll(".nav-link").forEach((button) =>
      button.classList.toggle("active", button.dataset.view === viewName)
    );
    const breadcrumb = document.getElementById("breadcrumb-current");
    if (breadcrumb) {
      breadcrumb.textContent = viewName === "agent" ? "Agent" : "Knowledge";
    }
  }

  function normalizePlan(result) {
    return result.run || result.plan || result;
  }

  function renderPlan(plan) {
    currentRun = plan;
    if (elements["plan-section"]) elements["plan-section"].hidden = false;
    if (elements["response-panel"]) elements["response-panel"].hidden = true;
    if (elements["plan-summary"]) {
      elements["plan-summary"].textContent = plan.summary || plan.title || "Execution plan";
    }
    if (elements["plan-meta"]) {
      elements["plan-meta"].replaceChildren();
      [
        ["RUN", plan.run_id || plan.id],
        ["INPUT", plan.input_language],
        ["RESPONSE", plan.response_language]
      ].forEach(([label, value]) => {
        if (!value) return;
        const chip = document.createElement("span");
        chip.className = "meta-chip";
        chip.textContent = `${label} · ${value}`;
        elements["plan-meta"].append(chip);
      });
    }

    if (elements["plan-steps"]) {
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
        description.textContent =
          step.description || step.action_description || step.expected_result || "No additional detail provided.";
        main.append(title, description);
        const tool = document.createElement("span");
        tool.className = "step-tool";
        tool.textContent = step.tool_name || step.tool || "Tool";
        tool.title = tool.textContent;
        row.append(marker, main, tool);

        if (step.result || step.error) {
          const result = document.createElement("div");
          result.className = `step-result${step.error ? " error" : ""}`;
          result.textContent = step.error || stringify(step.result);
          row.append(result);
        } else if (
          step.status &&
          !["pending", "planned", "awaiting_approval"].includes(step.status.toLowerCase())
        ) {
          const status = document.createElement("span");
          status.className = "step-status";
          status.textContent = step.status.replaceAll("_", " ");
          row.append(status);
        }
        elements["plan-steps"].append(row);
      });
    }

    const approved = [
      "approved", "running", "in_progress", "completed", "succeeded", "failed", "partial"
    ].includes((plan.status || "").toLowerCase());

    if (elements["approve-button"]) elements["approve-button"].hidden = approved || plan.status === "cancelled";
    if (elements["cancel-button"]) elements["cancel-button"].hidden = approved || plan.status === "cancelled";
    if (elements["replan-button"]) elements["replan-button"].hidden = approved || plan.status === "cancelled";

    setPlanStatus(plan.status || "awaiting_approval");
    if (approved) renderOutcome(plan);
  }

  function stringify(value) {
    if (typeof value === "string") return value;
    try {
      return JSON.stringify(value);
    } catch {
      return String(value);
    }
  }

  function setPlanStatus(status) {
    if (!elements["plan-status"]) return;
    const normalized = String(status).toLowerCase().replaceAll("_", " ");
    elements["plan-status"].textContent = normalized.toUpperCase();
    elements["plan-status"].className = `plan-status${
      ["running", "in progress", "approved"].includes(normalized)
        ? " running"
        : ["failed", "partial"].includes(normalized)
        ? " failed"
        : ""
    }`;
  }

  function renderOutcome(run) {
    const status = String(run.status || "").toLowerCase();
    const summary = run.summary || run.message || run.final_response || run.response;
    if (elements["execution-summary"]) {
      elements["execution-summary"].hidden = false;
      elements["execution-summary"].classList.toggle(
        "failed",
        ["failed", "partial", "blocked"].includes(status)
      );
      elements["execution-summary"].textContent = summary
        ? stringify(summary)
        : `Run status: ${status.replaceAll("_", " ") || "unknown"}.`;
    }
    if (
      ["completed", "succeeded", "failed", "partial", "blocked"].includes(status) &&
      (run.final_response || run.response)
    ) {
      showResponse(run);
    }
  }

  function showResponse(run) {
    const responseText = run.final_response || run.response;
    const text = typeof responseText === "string" ? responseText : responseText.text || responseText.content;
    if (!text) return;
    if (elements["response-panel"]) elements["response-panel"].hidden = false;
    if (elements["response-copy"]) elements["response-copy"].textContent = text;
    if (elements["response-title"]) {
      elements["response-title"].textContent =
        run.status === "completed" || run.status === "succeeded"
          ? "Verified execution report"
          : "Execution report · incomplete";
    }
    if (elements["response-sources"]) {
      elements["response-sources"].replaceChildren();
      (run.sources || responseText.sources || []).forEach((source) => {
        const chip = document.createElement("span");
        chip.className = "source-chip";
        chip.textContent = source.title || source.name || source.document_name || "Source";
        elements["response-sources"].append(chip);
      });
    }

    if (elements["auto-speak"]?.checked || voiceConversationMode) {
      synthesizeResponse(text, run.response_language || elements["response-language"]?.value || "en-IN");
    }
  }

  async function synthesizeResponse(text, language) {
    if (elements["voice-output"]) elements["voice-output"].hidden = false;
    if (elements["voice-error"]) elements["voice-error"].textContent = "Speaking response…";

    // Attempt backend speech synthesis first (Sarvam)
    try {
      const response = await fetch(`${API_BASE}/api/voice/synthesize`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text, language })
      });

      if (!response.ok) {
        // Fallback directly to native browser speech synthesis
        if (JarvisVoice.speak(text, language)) {
          if (elements["voice-error"]) elements["voice-error"].textContent = "Spoken via native browser voice.";
          return;
        }
        const error = await response.json().catch(() => ({}));
        throw new Error(error.error || `Voice generation failed (${response.status}).`);
      }

      const type = response.headers.get("content-type") || "";
      let audioBlob;
      if (type.includes("application/json")) {
        const result = await response.json();
        if (result.audio_url) {
          if (elements["response-audio"]) {
            elements["response-audio"].src = result.audio_url;
            elements["response-audio"].play().catch(() => {});
          }
          if (elements["voice-error"]) elements["voice-error"].textContent = "";
          return;
        }
        const encoded = result.audio_base64 || result.audio;
        if (!encoded) {
          if (JarvisVoice.speak(text, language)) {
            if (elements["voice-error"]) elements["voice-error"].textContent = "Spoken via native browser voice.";
            return;
          }
          throw new Error("Voice service returned no playable audio.");
        }
        const bytes = Uint8Array.from(atob(encoded), (character) => character.charCodeAt(0));
        audioBlob = new Blob([bytes], { type: result.mime_type || "audio/wav" });
      } else {
        audioBlob = await response.blob();
      }

      if (elements["response-audio"]) {
        elements["response-audio"].src = URL.createObjectURL(audioBlob);
        elements["response-audio"].play().catch(() => {});
      }
      if (elements["voice-error"]) elements["voice-error"].textContent = "";
    } catch (error) {
      // Automatic seamless fallback to browser Web Speech Synthesis
      if (JarvisVoice.speak(text, language)) {
        if (elements["voice-error"]) elements["voice-error"].textContent = "Spoken via native browser voice.";
      } else if (elements["voice-error"]) {
        elements["voice-error"].textContent = error.message;
      }
    }
  }

  async function createPlan() {
    const text = (elements["request-input"]?.value || "").trim();
    if (!text) return showRequestError("Add a request before building a plan.");
    showRequestError("");
    setBusy(true);
    try {
      const result = await request("/api/runs/plan", {
        method: "POST",
        body: JSON.stringify({
          request: text,
          input_language: elements["input-language"]?.value || "en-IN",
          response_language: elements["response-language"]?.value || "en-IN",
          auto_speak: elements["auto-speak"]?.checked || voiceConversationMode
        })
      });
      const plan = normalizePlan(result);
      if (!(plan.run_id || plan.id) || !Array.isArray(plan.steps)) {
        throw new Error("The backend returned an invalid plan.");
      }
      if (elements["execution-summary"]) elements["execution-summary"].hidden = true;
      renderPlan(plan);
      if (elements["plan-section"]) {
        elements["plan-section"].scrollIntoView({ behavior: "smooth", block: "nearest" });
      }
      return plan;
    } catch (error) {
      showRequestError(error.message);
      throw error;
    } finally {
      setBusy(false);
    }
  }

  async function pollRun(runId) {
    for (let attempt = 0; attempt < 40; attempt += 1) {
      const run = await request(`/api/runs/${encodeURIComponent(runId)}`);
      const normalized = run.run || run;
      renderPlan(normalized);
      if (
        ["completed", "succeeded", "failed", "partial", "blocked", "cancelled"].includes(
          String(normalized.status).toLowerCase()
        )
      ) {
        return normalized;
      }
      await new Promise((resolve) => window.setTimeout(resolve, 1200));
    }
    throw new Error("Execution is still running. Refresh the run to check its latest status.");
  }

  async function approvePlan() {
    const runId = currentRun?.run_id || currentRun?.id;
    if (!runId) return;
    setBusy(true);
    setPlanStatus("running");
    if (elements["execution-summary"]) {
      elements["execution-summary"].hidden = false;
      elements["execution-summary"].textContent =
        "Approval sent. Executing steps and verifying results…";
    }
    try {
      const result = await request(`/api/runs/${encodeURIComponent(runId)}/approve`, {
        method: "POST",
        body: JSON.stringify({ approved: true })
      });
      const run = result.run || result;
      renderPlan(run);
      if (
        !["completed", "succeeded", "failed", "partial", "blocked", "cancelled"].includes(
          String(run.status).toLowerCase()
        )
      ) {
        await pollRun(runId);
      }
    } catch (error) {
      if (elements["execution-summary"]) {
        elements["execution-summary"].hidden = false;
        elements["execution-summary"].classList.add("failed");
        elements["execution-summary"].textContent = `Execution status could not be confirmed: ${error.message}`;
      }
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
      const result = await request(`/api/runs/${encodeURIComponent(runId)}/cancel`, {
        method: "POST",
        body: JSON.stringify({})
      });
      renderPlan(result.run || result);
    } catch (error) {
      showRequestError(`Could not cancel the plan: ${error.message}`);
    } finally {
      setBusy(false);
    }
  }

  // ── Voice Conversation & Speech Recognition ─────────────────────────────────

  function startEnglishRecognition(isConvoMode = false) {
    if (!JarvisVoice.hasSpeechRecognition()) {
      showRequestError("Browser speech recognition is not supported in this browser. Falling back to audio recording.");
      return startAudioRecording();
    }

    speechRecognitionActive = true;
    if (elements["mic-button"]) {
      elements["mic-button"].classList.add("recording");
    }
    if (elements["mic-label"]) elements["mic-label"].textContent = "Stop";
    if (elements["discard-recording"]) elements["discard-recording"].hidden = false;

    JarvisVoice.startRecognition({
      language: elements["input-language"]?.value || "en-IN",
      onStart: () => {
        if (elements["recording-status"]) {
          elements["recording-status"].textContent = "🎙️ Listening... Speak naturally in English (e.g. 'Open calculator', 'What is 50 times 4')";
        }
      },
      onInterim: (text) => {
        if (elements["request-input"]) {
          elements["request-input"].value = text;
          if (elements["char-count"]) elements["char-count"].textContent = `${text.length} / 4000`;
        }
      },
      onFinal: (text) => {
        if (elements["request-input"]) {
          elements["request-input"].value = text;
          if (elements["char-count"]) elements["char-count"].textContent = `${text.length} / 4000`;
        }
      },
      onError: (errMsg) => {
        if (elements["recording-status"]) {
          elements["recording-status"].textContent = errMsg;
        }
        speechRecognitionActive = false;
        if (elements["mic-button"]) elements["mic-button"].classList.remove("recording");
        if (elements["mic-label"]) elements["mic-label"].textContent = "Speak";
      },
      onEnd: async (finalText) => {
        speechRecognitionActive = false;
        if (elements["mic-button"]) elements["mic-button"].classList.remove("recording");
        if (elements["mic-label"]) elements["mic-label"].textContent = "Speak";
        if (elements["discard-recording"]) elements["discard-recording"].hidden = true;

        const captured = (finalText || elements["request-input"]?.value || "").trim();
        if (!captured) {
          if (elements["recording-status"]) {
            elements["recording-status"].textContent = "No speech detected. Click Speak or Voice Convo to try again.";
          }
          if (isConvoMode) stopVoiceConversation();
          return;
        }

        if (elements["request-input"]) elements["request-input"].value = captured;
        if (elements["recording-status"]) {
          elements["recording-status"].textContent = `Recognized: "${captured}". Building plan…`;
        }

        // In Voice Conversation mode or auto-approve mode: auto-build plan and auto-execute!
        if (isConvoMode || elements["auto-approve-voice"]?.checked) {
          try {
            const plan = await createPlan();
            if (plan && (plan.run_id || plan.id)) {
              if (elements["recording-status"]) {
                elements["recording-status"].textContent = `Executing plan for: "${captured}"…`;
              }
              await approvePlan();
            }
          } catch (err) {
            if (elements["recording-status"]) {
              elements["recording-status"].textContent = `Execution error: ${err.message}`;
            }
          } finally {
            if (isConvoMode) {
              if (elements["voice-convo-label"]) elements["voice-convo-label"].textContent = "Voice Convo";
              if (elements["voice-convo-button"]) elements["voice-convo-button"].classList.remove("active");
              voiceConversationMode = false;
            }
          }
        }
      }
    });
  }

  function toggleVoiceConversation() {
    if (voiceConversationMode) {
      stopVoiceConversation();
      return;
    }
    voiceConversationMode = true;
    if (elements["voice-convo-button"]) elements["voice-convo-button"].classList.add("active");
    if (elements["voice-convo-label"]) elements["voice-convo-label"].textContent = "Listening…";
    if (elements["auto-speak"]) elements["auto-speak"].checked = true;
    if (elements["input-language"]) elements["input-language"].value = "en-IN";
    if (elements["response-language"]) elements["response-language"].value = "en-IN";

    // Play quick audio greeting / prompt
    JarvisVoice.speak("Listening. What can I do for you?");
    setTimeout(() => {
      startEnglishRecognition(true);
    }, 1200);
  }

  function stopVoiceConversation() {
    voiceConversationMode = false;
    if (elements["voice-convo-button"]) elements["voice-convo-button"].classList.remove("active");
    if (elements["voice-convo-label"]) elements["voice-convo-label"].textContent = "Voice Convo";
    JarvisVoice.stopRecognition();
    speechRecognitionActive = false;
    if (elements["mic-button"]) elements["mic-button"].classList.remove("recording");
    if (elements["mic-label"]) elements["mic-label"].textContent = "Speak";
    if (elements["discard-recording"]) elements["discard-recording"].hidden = true;
    if (elements["recording-status"]) elements["recording-status"].textContent = "Voice conversation ended.";
  }

  async function startAudioRecording() {
    try {
      await JarvisVoice.start(
        (message) => {
          if (elements["recording-status"]) elements["recording-status"].textContent = message;
        },
        () => {
          if (recording) toggleRecording();
        }
      );
      recording = true;
      if (elements["mic-label"]) elements["mic-label"].textContent = "Stop";
      if (elements["mic-button"]) {
        elements["mic-button"].classList.add("recording");
        elements["mic-button"].setAttribute("aria-label", "Stop voice recording");
      }
      if (elements["discard-recording"]) elements["discard-recording"].hidden = false;
    } catch (error) {
      if (elements["recording-status"]) elements["recording-status"].textContent = error.message;
    }
  }

  async function toggleRecording() {
    if (speechRecognitionActive) {
      JarvisVoice.stopRecognition();
      speechRecognitionActive = false;
      if (elements["mic-button"]) elements["mic-button"].classList.remove("recording");
      if (elements["mic-label"]) elements["mic-label"].textContent = "Speak";
      if (elements["discard-recording"]) elements["discard-recording"].hidden = true;
      return;
    }

    if (recording) {
      if (elements["mic-label"]) elements["mic-label"].textContent = "Processing";
      if (elements["mic-button"]) elements["mic-button"].classList.remove("recording");
      try {
        const blob = await JarvisVoice.stop();
        recording = false;
        if (elements["discard-recording"]) elements["discard-recording"].hidden = true;
        if (elements["mic-button"]) elements["mic-button"].setAttribute("aria-label", "Record voice request");
        if (!blob) {
          if (elements["recording-status"]) elements["recording-status"].textContent = "No audio captured.";
          if (elements["mic-label"]) elements["mic-label"].textContent = "Speak";
          return;
        }
        if (elements["recording-status"]) elements["recording-status"].textContent = "Sending audio for transcription…";
        const form = new FormData();
        form.append("audio", blob, `request.${blob.type.includes("ogg") ? "ogg" : blob.type.includes("mp4") ? "mp4" : "webm"}`);
        form.append("input_language", elements["input-language"]?.value || "en-IN");
        const result = await request("/api/voice/transcribe", { method: "POST", body: form });
        if (!result.transcript) throw new Error("Speech service returned no transcript.");
        if (elements["request-input"]) {
          elements["request-input"].value = result.transcript;
          if (elements["char-count"]) elements["char-count"].textContent = `${result.transcript.length} / 4000`;
        }
        if (elements["recording-status"]) {
          elements["recording-status"].textContent = `Recognized · ${result.language || "audio"}. Transcript ready.`;
        }
      } catch (error) {
        if (elements["recording-status"]) elements["recording-status"].textContent = error.message;
      } finally {
        if (elements["mic-label"]) elements["mic-label"].textContent = "Speak";
      }
      return;
    }

    // Default to real-time Web Speech recognition for English!
    const isEnglish = (elements["input-language"]?.value || "").startsWith("en");
    if (isEnglish && JarvisVoice.hasSpeechRecognition()) {
      startEnglishRecognition(false);
      return;
    }

    // Fallback to MediaRecorder for Indic languages via Sarvam STT
    await startAudioRecording();
  }

  // ── Document Library ────────────────────────────────────────────────────────

  async function loadDocuments() {
    try {
      const result = await request("/api/knowledge/documents");
      const documents = result.documents || [];
      if (elements["document-total"]) elements["document-total"].textContent = String(documents.length);
      if (elements["knowledge-count"]) elements["knowledge-count"].textContent = String(documents.length);
      if (elements["document-list"]) {
        elements["document-list"].replaceChildren();
        if (!documents.length) {
          const empty = document.createElement("div");
          empty.className = "empty-documents";
          empty.innerHTML =
            '<span class="empty-mark">▤</span><strong>Your library is clear.</strong><span>Uploaded knowledge will appear here with its indexing status.</span>';
          elements["document-list"].append(empty);
          return;
        }
        documents.forEach((documentRecord) => {
          const row = document.createElement("article");
          row.className = "document-row";
          const mark = document.createElement("span");
          mark.className = "file-mark";
          mark.textContent = (documentRecord.mime_type || documentRecord.filename || "FILE")
            .split(/[./]/)
            .pop()
            .slice(0, 4)
            .toUpperCase();
          const main = document.createElement("div");
          main.className = "document-main";
          const title = document.createElement("strong");
          title.textContent = documentRecord.title || documentRecord.filename || "Untitled document";
          const info = document.createElement("small");
          info.textContent = documentRecord.updated_at || documentRecord.created_at || "Added to library";
          main.append(title, info);
          const status = document.createElement("span");
          const state = String(documentRecord.status || documentRecord.indexing_status || "unknown").toLowerCase();
          status.className = `document-status${
            state === "ready" || state === "indexed" ? " ready" : state === "failed" || state === "error" ? " failed" : ""
          }`;
          status.textContent = state.replaceAll("_", " ");
          row.append(mark, main, status);
          elements["document-list"].append(row);
        });
      }
    } catch (error) {
      if (elements["document-list"]) {
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
  }

  async function uploadDocument(file) {
    if (!file) return;
    const extension = file.name.split(".").pop().toLowerCase();
    if (!ALLOWED_DOCUMENT_EXTENSIONS.has(extension)) {
      if (elements["upload-feedback"]) {
        elements["upload-feedback"].className = "upload-feedback error";
        elements["upload-feedback"].textContent = "Unsupported format. Choose a PDF, TXT, or Markdown document.";
      }
      return;
    }
    if (file.size > MAX_DOCUMENT_BYTES) {
      if (elements["upload-feedback"]) {
        elements["upload-feedback"].className = "upload-feedback error";
        elements["upload-feedback"].textContent = "This document exceeds the 20 MB upload limit.";
      }
      return;
    }
    if (elements["upload-feedback"]) {
      elements["upload-feedback"].className = "upload-feedback";
      elements["upload-feedback"].textContent = `Uploading ${file.name}…`;
    }
    const form = new FormData();
    form.append("file", file);
    try {
      const result = await request("/api/knowledge/documents", { method: "POST", body: form });
      const documentRecord = result.document || result;
      if (elements["upload-feedback"]) {
        elements["upload-feedback"].textContent = `${documentRecord.title || file.name} · ${
          documentRecord.status || documentRecord.indexing_status || "received"
        }. Ready status will appear after indexing completes.`;
      }
      await loadDocuments();
    } catch (error) {
      if (elements["upload-feedback"]) {
        elements["upload-feedback"].className = "upload-feedback error";
        elements["upload-feedback"].textContent = error.message;
      }
    } finally {
      if (elements["document-input"]) elements["document-input"].value = "";
    }
  }

  // ── Event Listeners ─────────────────────────────────────────────────────────

  document.querySelectorAll(".nav-link").forEach((button) =>
    button.addEventListener("click", () => switchView(button.dataset.view))
  );

  if (elements["request-input"]) {
    elements["request-input"].addEventListener("input", () => {
      if (elements["char-count"]) {
        elements["char-count"].textContent = `${elements["request-input"].value.length} / 4000`;
      }
    });
  }

  if (elements["plan-button"]) elements["plan-button"].addEventListener("click", createPlan);
  if (elements["approve-button"]) elements["approve-button"].addEventListener("click", approvePlan);
  if (elements["cancel-button"]) elements["cancel-button"].addEventListener("click", cancelPlan);
  if (elements["replan-button"]) {
    elements["replan-button"].addEventListener("click", () => {
      if (elements["plan-section"]) elements["plan-section"].hidden = true;
      if (elements["request-input"]) elements["request-input"].focus();
    });
  }

  if (elements["mic-button"]) elements["mic-button"].addEventListener("click", toggleRecording);
  if (elements["voice-convo-button"]) elements["voice-convo-button"].addEventListener("click", toggleVoiceConversation);

  if (elements["discard-recording"]) {
    elements["discard-recording"].addEventListener("click", () => {
      JarvisVoice.cancel();
      recording = false;
      speechRecognitionActive = false;
      voiceConversationMode = false;
      if (elements["mic-button"]) {
        elements["mic-button"].classList.remove("recording");
        elements["mic-button"].setAttribute("aria-label", "Record voice request");
      }
      if (elements["mic-label"]) elements["mic-label"].textContent = "Speak";
      if (elements["voice-convo-button"]) {
        elements["voice-convo-button"].classList.remove("active");
      }
      if (elements["voice-convo-label"]) elements["voice-convo-label"].textContent = "Voice Convo";
      elements["discard-recording"].hidden = true;
      if (elements["recording-status"]) elements["recording-status"].textContent = "Recording discarded.";
    });
  }

  if (elements["document-input"]) {
    elements["document-input"].addEventListener("change", (event) => uploadDocument(event.target.files[0]));
  }
  if (elements["refresh-documents"]) {
    elements["refresh-documents"].addEventListener("click", loadDocuments);
  }

  if (elements["response-language"]) {
    elements["response-language"].addEventListener("change", () => {
      const lang = elements["response-language"].value;
      if (elements["language-hint"]) {
        elements["language-hint"].textContent = lang.startsWith("en")
          ? "English voice conversation & speech synthesis ready."
          : "Spoken output is available for this language via Sarvam AI.";
      }
    });
  }

  if (elements.dropzone) {
    elements.dropzone.addEventListener("dragover", (event) => {
      event.preventDefault();
      elements.dropzone.classList.add("dragover");
    });
    elements.dropzone.addEventListener("dragleave", () => elements.dropzone.classList.remove("dragover"));
    elements.dropzone.addEventListener("drop", (event) => {
      event.preventDefault();
      elements.dropzone.classList.remove("dragover");
      uploadDocument(event.dataTransfer.files[0]);
    });
  }

  // Initial load
  loadConfig();
  loadDocuments();
})();