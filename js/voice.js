window.JarvisVoice = (() => {
  const MAX_DURATION_MS = 30_000;
  const MAX_UPLOAD_BYTES = 15 * 1024 * 1024;
  let recorder;
  let stream;
  let chunks = [];
  let stopTimer;

  function supportedMimeType() {
    if (!window.MediaRecorder) return "";
    return ["audio/webm;codecs=opus", "audio/webm", "audio/ogg;codecs=opus", "audio/mp4"]
      .find((type) => MediaRecorder.isTypeSupported(type)) || "";
  }

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
    if (recorder && recorder.state !== "inactive") recorder.stop();
    stream?.getTracks().forEach((track) => track.stop());
    stream = null;
    recorder = null;
    chunks = [];
  }

  return { start, stop, cancel };
})();