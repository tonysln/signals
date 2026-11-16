const $ = (id) => document.getElementById(id);
const form = $("form"), inputs = $("inputs"), mode = $("mode"), image = $("image");
const resize = $("resize"), preview = $("preview"), dims = $("dims");
const go = $("go"), status = $("status"), log = $("log");
const result = $("result"), player = $("player"), audio = $("audio");
const download = $("download"), kind = $("kind");

let previewUrl = null;
let wavUrl = null;
let busy = false;

// Drop any previous output so nothing on screen belongs to old settings.
function clearResult() {
  result.hidden = true;
  audio.pause();
  audio.removeAttribute("src");
  audio.load();
  download.removeAttribute("href");
  if (wavUrl) { URL.revokeObjectURL(wavUrl); wavUrl = null; }
  status.textContent = "";
  status.className = "";
  log.replaceChildren();
  log.hidden = true;
}

function setStatus(text, cls = "") {
  status.textContent = text;
  status.className = cls;
}

function addLog(text, cls = "") {
  const li = document.createElement("li");
  li.textContent = text;
  if (cls) li.className = cls;
  log.append(li);
  log.hidden = false;
  log.scrollTop = log.scrollHeight;
}

// Image size vs. what the selected mode needs.
function updateDims() {
  const opt = mode.selectedOptions[0];
  if (!image.files[0] || !preview.naturalWidth || !opt) { dims.textContent = ""; return; }
  const w = preview.naturalWidth, h = preview.naturalHeight;
  const mw = +opt.dataset.w, mh = +opt.dataset.h;
  let note = "fits";
  dims.className = "hint";
  if (w !== mw || h !== mh) {
    if (resize.checked) note = `will be resized to ${mw}×${mh}`;
    else {
      note = w < mw || h < mh ? `too small, needs ${mw}×${mh}` : `needs ${mw}×${mh}`;
      dims.className = "hint warn";
    }
  }
  dims.textContent = `${w}×${h} — ${note}`;
}

function updatePreview() {
  if (previewUrl) { URL.revokeObjectURL(previewUrl); previewUrl = null; }
  preview.removeAttribute("src");
  preview.hidden = true;
  dims.textContent = "";
  const file = image.files[0];
  if (!file) return;
  previewUrl = URL.createObjectURL(file);
  preview.src = previewUrl;
}

preview.addEventListener("load", () => { preview.hidden = false; updateDims(); });
preview.addEventListener("error", () => {
  // e.g. BMP variants the browser can't show; the encoder may still read it
  preview.hidden = true;
  dims.textContent = "No Preview";
  dims.className = "hint";
});

image.addEventListener("change", updatePreview);
form.addEventListener("change", () => { if (!busy) clearResult(); updateDims(); });

// Browsers may restore form fields from history; resync everything.
window.addEventListener("pageshow", () => { clearResult(); updatePreview(); });

// Reads newline-delimited JSON events from the response body.
async function* events(res) {
  const reader = res.body.pipeThrough(new TextDecoderStream()).getReader();
  let buf = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buf += value;
    let i;
    while ((i = buf.indexOf("\n")) >= 0) {
      const line = buf.slice(0, i).trim();
      buf = buf.slice(i + 1);
      if (line) yield JSON.parse(line);
    }
  }
}

form.addEventListener("submit", async (e) => {
  e.preventDefault();
  if (busy) return;

  // Collect before disabling: disabled fields are left out of FormData.
  const data = new FormData(form);
  data.append("encoding", mode.selectedOptions[0].dataset.encoding);

  clearResult();
  busy = true;
  go.disabled = true;
  inputs.disabled = true;
  setStatus("Uploading...");

  try {
    const res = await fetch("/encode", { method: "POST", body: data });
    if (!res.ok) throw new Error(await res.text());

    let job = null;
    for await (const ev of events(res)) {
      if (ev.msg) { setStatus(ev.msg); addLog(ev.msg); }
      if (ev.warn) addLog(ev.warn, "warn");
      if (ev.error) throw new Error(ev.error);
      if (ev.done) job = ev;
    }
    if (!job) throw new Error("Encoder stopped unexpectedly.");

    setStatus("Fetching output...");
    const out = await fetch(`/result/${job.done}`, { cache: "no-store" });
    if (!out.ok) throw new Error("Output is no longer available.");
    wavUrl = URL.createObjectURL(await out.blob());

    player.hidden = job.raw;
    if (!job.raw) audio.src = wavUrl;
    kind.textContent = job.raw ? "Raw S16 Mono" : "WAV";
    download.href = wavUrl;
    download.download = job.name;
    download.textContent = job.name;
    result.hidden = false;
    setStatus("Done.", "ok");
    addLog("Done.");
  } catch (err) {
    setStatus(err.message || "Encoding failed.", "err");
  } finally {
    busy = false;
    go.disabled = false;
    inputs.disabled = false;
  }
});
