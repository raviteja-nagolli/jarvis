window.JarvisVoice = (() => {
  const MAX_DURATION_MS = 30_000;
  const MAX_UPLOAD_BYTES = 15 * 1024 * 1024;
  let recorder = null;
  let stream = null;
  let chunks = [];
  let stopTimer = null;

  // Web Speech API interfaces
  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition || null;
  let recognitionInstance = null;

  function hasSpeechRecognition() {
    return Boolean(SpeechRecognition);
  }

  function supportedMimeType() {
    if (!window.MediaRecorder) return "";
    return ["audio/webm;codecs=opus", "audio/webm", "audio/ogg;codecs=opus", "audio/mp4"]
      .find((type) => MediaRecorder.isTypeSupported(type)) || "";
  }

  // ── Native Browser Speech Recognition (Instant & Ideal for English) ────────
  function startRecognition({ language = "en-IN", onInterim, onFinal, onError, onEnd, onStart }) {
    if (!SpeechRecognition) {
      throw new Error("Speech recognition is not supported in this browser. Please use Chrome, Edge, or enable microphone permissions.");
    }
    if (recognitionInstance) {
      try { recognitionInstance.abort(); } catch (_) {}
      recognitionInstance = null;
    }

    const recognition = new SpeechRecognition();
    recognition.lang = language;
    recognition.continuous = false;
    recognition.interimResults = true;
    recognition.maxAlternatives = 1;

    let accumulatedFinal = "";

    recognition.onstart = () => {
      if (onStart) onStart();
    };

    recognition.onresult = (event) => {
      let interim = "";
      for (let i = event.resultIndex; i < event.results.length; i++) {
        const item = event.results[i];
        const transcript = item[0]?.transcript || "";
        if (item.isFinal) {
          accumulatedFinal += (accumulatedFinal ? " " : "") + transcript.trim();
        } else {
          interim += transcript;
        }
      }
      if (onInterim && interim) onInterim(interim);
      if (onFinal && accumulatedFinal) onFinal(accumulatedFinal);
    };

    recognition.onerror = (event) => {
      // "no-speech" or "aborted" are non-fatal user events
      if (event.error === "no-speech") {
        if (onError) onError("No speech detected. Please speak clearly into the microphone.");
      } else if (event.error !== "aborted") {
        if (onError) onError(`Speech recognition error: ${event.error}`);
      }
    };

    recognition.onend = () => {
      recognitionInstance = null;
      if (onEnd) onEnd(accumulatedFinal.trim());
    };

    recognitionInstance = recognition;
    recognition.start();
    return recognition;
  }

  function stopRecognition() {
    if (recognitionInstance) {
      try { recognitionInstance.stop(); } catch (_) {}
      recognitionInstance = null;
    }
  }

  // ── Browser Speech Synthesis (High Quality Native TTS) ─────────────────────
  function speak(text, language = "en-IN") {
    if (!window.speechSynthesis) return false;
    window.speechSynthesis.cancel();
    if (!text || !text.trim()) return false;

    // Clean markdown stars, hashes, etc. for speech
    const cleanText = text
      .replace(/[*#`_~]/g, "")
      .replace(/\[([^\]]+)\]\([^)]+\)/g, "$1")
      .trim();

    const utterance = new SpeechSynthesisUtterance(cleanText);
    utterance.lang = language;
    utterance.rate = 1.0;
    utterance.pitch = 1.0;

    // Pick best matching English or local voice if available
    const voices = window.speechSynthesis.getVoices();
    if (voices && voices.length > 0) {
      const match = voices.find((v) => v.lang === language || v.lang.startsWith(language.split("-")[0]))
        || voices.find((v) => v.lang.includes("en"));
      if (match) utterance.voice = match;
    }

    window.speechSynthesis.speak(utterance);
    return true;
  }

  function stopSpeaking() {
    if (window.speechSynthesis) {
      window.speechSynthesis.cancel();
    }
  }

  // ── MediaRecorder (Fallback & Indic audio recording for Sarvam API) ────────
  async function start(onStatus, onLimit) {
    if (!navigator.mediaDevices?.getUserMedia || !window.MediaRecorder) {
      throw new Error("Microphone recording is not supported by this browser.");
    }
    const mimeType = supportedMimeType();
    if (!mimeType) throw new Error("This browser does not offer a supported recording format.");
    stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    chunks = [];
    recorder = new MediaRecorder(stream, { mimeType });
    recorder.addEventListener("dataavailable", (event) => {
      if (event.data.size) chunks.push(event.data);
    });
    recorder.addEventListener("start", () => onStatus("Recording · 30 second limit"));
    recorder.start(250);
    stopTimer = window.setTimeout(() => onLimit(), MAX_DURATION_MS);
  }

  function stop() {
    if (!recorder || recorder.state === "inactive") return Promise.resolve(null);
    window.clearTimeout(stopTimer);
    return new Promise((resolve, reject) => {
      recorder.addEventListener("stop", () => {
        stream?.getTracks().forEach((track) => track.stop());
        stream = null;
        const blob = new Blob(chunks, { type: recorder.mimeType });
        recorder = null;
        chunks = [];
        if (!blob.size) return resolve(null);
        if (blob.size > MAX_UPLOAD_BYTES) return reject(new Error("Recording exceeds the 15 MB upload limit."));
        resolve(blob);
      }, { once: true });
      recorder.stop();
    });
  }

  function cancel() {
    window.clearTimeout(stopTimer);
    stopRecognition();
    stopSpeaking();
    if (recorder && recorder.state !== "inactive") recorder.stop();
    stream?.getTracks().forEach((track) => track.stop());
    stream = null;
    recorder = null;
    chunks = [];
  }

  return {
    hasSpeechRecognition,
    startRecognition,
    stopRecognition,
    speak,
    stopSpeaking,
    start,
    stop,
    cancel,
  };
})();