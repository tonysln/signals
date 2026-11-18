const $ = (id) => document.getElementById(id);
const form = $("form"), inputs = $("inputs"), mode = $("mode"), image = $("image");
const resize = $("resize"), preview = $("preview"), dims = $("dims");
const go = $("go"), status = $("status"), log = $("log");
const result = $("result"), player = $("player"), audio = $("audio");
const download = $("download"), kind = $("kind");
const signal = $("signal"), strip = $("strip");

const worker = new Worker("worker.js");

let previewUrl = null;
let wavUrl = null;
let busy = false;
let ready = false;
let job = null;  // { resolve, reject } of the running encode
let shown = null;  // strip on the canvas: { img, bg, sr, grids, live }
let frame = 0;     // pending animation frame while playing

// Drop any previous output so nothing on screen belongs to old settings.
function clearResult() {
  result.hidden = true;
  signal.hidden = true;
  shown = null;
  audio.pause();
  audio.removeAttribute("src");
  audio.load();
  download.removeAttribute("href");
  if (wavUrl) { URL.revokeObjectURL(wavUrl); wavUrl = null; }
  if (!ready) return;
  status.textContent = "";
  status.className = "";
  log.replaceChildren();
  log.hidden = true;
}


function drawStrip(s, live) {
  if (!s) return;
  strip.width = s.width;
  strip.height = s.height;
  const img = new ImageData(new Uint8ClampedArray(s.pixels), s.width, s.height);
  live = live && !!s.grids;
  let dim = null;
  if (live) {
    dim = new ImageData(new Uint8ClampedArray(img.data), s.width, s.height);
    const d = dim.data;
    for (let i = 0; i < d.length; i += 4) {
      for (let c = 0; c < 3; c++) d[i + c] = s.bg[c] + (d[i + c] - s.bg[c]) * 0.25;
    }
  }
  shown = { img, dim, sr: s.sr, grids: s.grids, live, playing: false };
  reveal();
  signal.hidden = false;
}

// Paint the strip up to the current playback position.
function reveal() {
  if (!shown) return;
  const { img, dim, sr, grids, live } = shown;
  const ctx = strip.getContext("2d");
  if (!live || !shown.playing) { ctx.putImageData(img, 0, 0); return; }
  ctx.putImageData(dim, 0, 0);
  const t = audio.currentTime * sr;
  for (const g of grids) {
    const pos = Math.min(g.rows, Math.max(0, (t - g.origin) / g.period));
    const full = Math.floor(pos);
    if (full) ctx.putImageData(img, 0, 0, 0, g.y0, img.width, full * g.thick);
    const part = Math.floor((pos - full) * img.width);
    if (full < g.rows && part) {
      ctx.putImageData(img, 0, 0, 0, g.y0 + full * g.thick, part, g.thick);
    }
  }
}

function tick() {
  reveal();
  frame = audio.paused ? 0 : requestAnimationFrame(tick);
}

audio.addEventListener("play", () => {
  if (shown) shown.playing = true;
  if (!frame) frame = requestAnimationFrame(tick);
});
audio.addEventListener("seeked", reveal);
audio.addEventListener("ended", reveal);

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

// Mode dropdown, grouped by family, from the encoder's own table.
function fillModes(modes) {
  const groups = new Map();
  for (const m of modes) {
    if (!groups.has(m.family)) {
      const g = document.createElement("optgroup");
      g.label = m.family;
      groups.set(m.family, g);
      mode.append(g);
    }
    const o = document.createElement("option");
    o.value = m.index;
    o.dataset.w = m.width;
    o.dataset.h = m.height;
    o.textContent = `${m.name} — ${m.width}×${m.height}`;
    groups.get(m.family).append(o);
  }
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
  preview.hidden = true;
  dims.textContent = "No Preview";
  dims.className = "hint";
});

image.addEventListener("change", updatePreview);
form.addEventListener("change", () => { if (!busy) clearResult(); updateDims(); });

// Browsers may restore form fields from history; resync everything.
window.addEventListener("pageshow", () => { clearResult(); updatePreview(); });

worker.addEventListener("message", ({ data: ev }) => {
  if (ev.modes) {
    fillModes(ev.modes);
    ready = true;
    inputs.disabled = false;
    go.disabled = false;
    setStatus("");
    updateDims();
    return;
  }
  if (!job) {
    if (ev.error) setStatus(ev.error, "err");  // load failure
    return;
  }
  if (ev.msg) { setStatus(ev.msg); addLog(ev.msg); }
  if (ev.warn) addLog(ev.warn, "warn");
  if (ev.error) job.reject(new Error(ev.error));
  if (ev.done) job.resolve(ev);
});

worker.addEventListener("error", () => {
  if (job) job.reject(new Error("Encoder stopped unexpectedly."));
  else setStatus("Encoder failed to load.", "err");
});

form.addEventListener("submit", async (e) => {
  e.preventDefault();
  if (busy || !ready) return;
  const file = image.files[0];
  if (!file) return;

  const request = {
    file,
    mode: +mode.value,
    sr: +$("sr").value,
    vox: $("vox").checked,
    raw: $("raw").checked,
    resize: resize.checked,
  };

  clearResult();
  busy = true;
  go.disabled = true;
  inputs.disabled = true;
  setStatus("Starting encoder...");

  try {
    const out = await new Promise((resolve, reject) => {
      job = { resolve, reject };
      worker.postMessage(request);
    });

    wavUrl = URL.createObjectURL(out.done);
    player.hidden = out.raw;
    if (!out.raw) audio.src = wavUrl;
    kind.textContent = out.raw ? "Raw S16 Mono" : "WAV";
    download.href = wavUrl;
    download.download = out.name;
    download.textContent = out.name;
    result.hidden = false;
    drawStrip(out.strip, !out.raw);
    setStatus("Done.", "ok");
    addLog("Done.");
  } catch (err) {
    setStatus(err.message || "Encoding failed.", "err");
  } finally {
    job = null;
    busy = false;
    go.disabled = false;
    inputs.disabled = false;
  }
});
