// Runs the SSTV encoder (encoder.wasm) off the main thread.
//
// Messages in:  { file, mode, sr, vox, raw, resize }
// Messages out: { modes } once loaded, then per job { msg } / { warn },
//               finally { done: Blob, name, raw, strip } or { error }
//               (strip: { width, height, pixels: RGBA buffer, bg, sr, grids },
//               see render())

let wasm = null;   // exports
let chunks = [];   // Int16Array blocks emitted by the encoder
let marks = [];    // [end Uint32Array, hz Uint16Array, kind Uint8Array] blocks

const imports = {
  env: {
    sstv_emit(ptr, count) {
      // Copy out: the block is reused and memory may grow later
      chunks.push(new Int16Array(wasm.memory.buffer, ptr, count).slice());
    },
    sstv_marks(endPtr, hzPtr, kindPtr, count) {
      const b = wasm.memory.buffer;
      marks.push([
        new Uint32Array(b, endPtr, count).slice(),
        new Uint16Array(b, hzPtr, count).slice(),
        new Uint8Array(b, kindPtr, count).slice(),
      ]);
    },
    emscripten_notify_memory_growth() {},
  },
};

function cstr(ptr) {
  const mem = new Uint8Array(wasm.memory.buffer);
  let end = ptr;
  while (mem[end]) end++;
  return new TextDecoder().decode(mem.subarray(ptr, end));
}

async function load() {
  const res = fetch("encoder.wasm");
  let inst;
  try {
    ({ instance: inst } = await WebAssembly.instantiateStreaming(res, imports));
  } catch {
    // Server without the application/wasm MIME type
    const buf = await (await fetch("encoder.wasm")).arrayBuffer();
    ({ instance: inst } = await WebAssembly.instantiate(buf, imports));
  }
  wasm = inst.exports;
  wasm._initialize();

  const modes = [];
  for (let i = 0; i < wasm.sstv_mode_count(); i++) {
    modes.push({
      index: i,
      family: cstr(wasm.sstv_mode_family(i)),
      name: cstr(wasm.sstv_mode_name(i)),
      width: wasm.sstv_mode_width(i),
      height: wasm.sstv_mode_height(i),
    });
  }
  return modes;
}

// Decode the image to top-down RGB bytes, stretched to w x h when resizing
// (aspect ratio ignored, like the old server's resize).
async function pixels(file, w, h, resize) {
  const bmp = await createImageBitmap(file, {
    colorSpaceConversion: "none",
    premultiplyAlpha: "none",
  });
  const iw = bmp.width, ih = bmp.height;

  if (!resize && (iw < w || ih < h)) {
    bmp.close();
    throw new Error(`Image is smaller than ${w}x${h}; enable resize.`);
  }

  const cw = resize ? w : iw, ch = resize ? h : ih;
  const canvas = new OffscreenCanvas(cw, ch);
  const ctx = canvas.getContext("2d", { willReadFrequently: true });
  ctx.imageSmoothingQuality = "high";
  ctx.drawImage(bmp, 0, 0, cw, ch);
  bmp.close();

  // Without resize a larger image is read as-is, like sstv.py does: the first
  // w*h pixels in row order, so rows are skewed if the width differs.
  const rgba = ctx.getImageData(0, 0, cw, ch).data;
  const n = w * h;
  const rgb = new Uint8Array(n * 3);
  for (let i = 0, j = 0; i < n; i++, j += 4) {
    rgb[i * 3] = rgba[j];
    rgb[i * 3 + 1] = rgba[j + 1];
    rgb[i * 3 + 2] = rgba[j + 2];
  }
  return { rgb, iw, ih };
}

// Colours per tone kind, in the order of enum kind in encoder.c. Image
// channels are ramps from BG to their colour by frequency (1500-2300 Hz);
// the rest are flat, except VOX which is also shaded by frequency.
const BG = [15, 17, 26];
const KINDS = [
  { rgb: [155, 123, 255], ramp: true },  // VOX
  { rgb: [255, 176, 0] },                // Leader, or FAX start tone
  { rgb: [255, 43, 214] },               // VIS start/stop
  { rgb: [255, 228, 92] },               // VIS 1
  { rgb: [214, 104, 0] },                // VIS 0
  { rgb: [255, 43, 214] },               // Sync
  { rgb: [70, 78, 102] },                // Porch
  { rgb: [255, 77, 77], ramp: true },    // Red
  { rgb: [61, 220, 132], ramp: true },   // Green
  { rgb: [77, 139, 255], ramp: true },   // Blue
  { rgb: [232, 232, 232], ramp: true },  // Y
  { rgb: [255, 122, 89], ramp: true },   // R-Y
  { rgb: [90, 169, 255], ramp: true },   // B-Y
  { rgb: [245, 230, 200], ramp: true },  // Greyscale
];
const K_SYNC = 5;
const STRIP_W = 128;

function kindColor(kind, hz) {
  const k = KINDS[kind];
  if (!k.ramp) return k.rgb;
  const v = 0.12 + 0.88 * Math.min(1, Math.max(0, (hz - 1500) / 800));
  return k.rgb.map((c, i) => BG[i] + (c - BG[i]) * v);
}


function render(segs, sr) {
  const { end, kind } = segs;
  const n = end.length;
  const total = n ? end[n - 1] : 0;
  if (!total) return null;
  const startOf = (i) => (i ? end[i - 1] : 0);


  const syncs = [];
  for (let i = 0; i < n; i++) if (kind[i] === K_SYNC) syncs.push(startOf(i));
  let period = total / 64, first = 0, imgFrom = 0;
  if (syncs.length > 2) {
    const gaps = syncs.slice(1).map((s, i) => s - syncs[i]).sort((a, b) => a - b);
    const med = gaps[gaps.length >> 1];
    let i0 = 0;
    while (i0 < syncs.length - 1 && Math.abs(syncs[i0 + 1] - syncs[i0] - med) > med * 0.02) i0++;
    first = syncs[i0];
    imgFrom = syncs[0];
    const last = syncs[syncs.length - 1];
    const lines = Math.round((last - first) / med);
    period = lines > 0 ? (last - first) / lines : med;
  }

  // Image grid: rows start at a sync, the first row holds the first sync
  const imgStart = first - Math.ceil((first - imgFrom) / period) * period;
  const imgRows = Math.ceil((total - imgStart) / period);

  // Header grid: 300 ms rows with the VIS start bit at x = 0
  const hPeriod = 0.3 * sr;
  let visAt = 0;
  for (let i = 0; i < n; i++) {
    if (kind[i] === 3 || kind[i] === 4) { visAt = startOf(i) - 0.03 * sr; break; }
  }
  const hStart = visAt - Math.ceil(visAt / hPeriod) * hPeriod;
  const hRows = imgFrom > 0 ? Math.ceil((imgFrom - hStart) / hPeriod) : 0;
  const thick = hRows ? Math.max(1, Math.min(6, Math.round(0.15 * imgRows / hRows))) : 0;
  const gap = hRows ? 2 : 0;

  const w = STRIP_W;
  const h = hRows * thick + gap + imgRows;
  const px = new Uint8ClampedArray(w * h * 4);
  for (let i = 0; i < w * h; i++) px.set(BG, i * 4), (px[i * 4 + 3] = 255);

  paint(segs, px, 0, hRows, thick, hStart, hPeriod, 0, imgFrom);
  paint(segs, px, hRows * thick + gap, imgRows, 1, imgStart, period, imgFrom, total);

  // Row timing, so the page can reveal the strip in step with playback
  const grids = [
    { y0: 0, rows: hRows, thick, origin: hStart, period: hPeriod },
    { y0: hRows * thick + gap, rows: imgRows, thick: 1, origin: imgStart, period },
  ];
  return { width: w, height: h, pixels: px.buffer, bg: BG, sr, grids };
}


function paint({ end, hz, kind }, px, y0, rows, thick, origin, period, from, to) {
  const n = end.length, w = STRIP_W, step = period / w;
  let s = 0;  // first segment that may overlap the current pixel
  for (let row = 0; row < rows; row++) {
    for (let x = 0; x < w; x++) {
      const t0 = Math.max(from, origin + (row * w + x) * step);
      const t1 = Math.min(to, origin + (row * w + x + 1) * step);
      if (t1 <= t0) continue;
      let r = 0, g = 0, b = 0, wsum = 0, top = -1;
      while (s < n && end[s] <= t0) s++;
      for (let j = s; j < n; j++) {
        const a = j ? end[j - 1] : 0;
        if (a >= t1) break;
        const k = kind[j];
        if (k < 7) {           // structural tone: highest priority wins
          if (top < 0 || PRIORITY[k] > PRIORITY[top]) top = k;
          continue;
        }
        const ov = Math.min(t1, end[j]) - Math.max(t0, a);
        const c = kindColor(k, hz[j]);
        r += c[0] * ov; g += c[1] * ov; b += c[2] * ov; wsum += ov;
      }
      let c;
      if (top === 0) {         // VOX: shade by the tone at the pixel centre
        let j = s;
        while (j < n - 1 && end[j] <= (t0 + t1) / 2) j++;
        c = kindColor(0, hz[j]);
      } else if (top > 0) c = KINDS[top].rgb;
      else if (wsum) c = [r / wsum, g / wsum, b / wsum];
      else continue;
      for (let dy = 0; dy < thick; dy++) {
        const o = ((y0 + row * thick + dy) * w + x) * 4;
        px[o] = c[0]; px[o + 1] = c[1]; px[o + 2] = c[2];
      }
    }
  }
}

// Which structural kind shows when several share a pixel
const PRIORITY = [1, 2, 6, 5, 5, 7, 3];

function joinMarks(blocks) {
  const n = blocks.reduce((a, m) => a + m[0].length, 0);
  const end = new Uint32Array(n), hz = new Uint16Array(n), kind = new Uint8Array(n);
  let o = 0;
  for (const [e, f, k] of blocks) {
    end.set(e, o); hz.set(f, o); kind.set(k, o);
    o += e.length;
  }
  return { end, hz, kind };
}

function wavHeader(sr, dataBytes) {
  const v = new DataView(new ArrayBuffer(44));
  const str = (o, s) => { for (let i = 0; i < 4; i++) v.setUint8(o + i, s.charCodeAt(i)); };
  str(0, "RIFF");
  v.setUint32(4, 36 + dataBytes, true);
  str(8, "WAVE");
  str(12, "fmt ");
  v.setUint32(16, 16, true);       // fmt chunk size
  v.setUint16(20, 1, true);        // PCM
  v.setUint16(22, 1, true);        // mono
  v.setUint32(24, sr, true);
  v.setUint32(28, sr * 2, true);   // byte rate
  v.setUint16(32, 2, true);        // block align
  v.setUint16(34, 16, true);       // bits per sample
  str(36, "data");
  v.setUint32(40, dataBytes, true);
  return v.buffer;
}

async function encode({ file, mode, sr, vox, raw, resize }, modes) {
  const m = modes[mode];
  if (!m) throw new Error("Unknown encoding or mode.");

  const post = (msg) => self.postMessage({ msg });

  if (resize) post(`Resizing image to ${m.width}x${m.height}...`);
  const { rgb, iw, ih } = await pixels(file, m.width, m.height, resize);
  if (!resize && (iw !== m.width || ih !== m.height)) {
    self.postMessage({ warn: `input image dimensions (${iw},${ih}) not supported by encoding mode (${m.width},${m.height})` });
  }

  if (wasm.sstv_begin(mode, sr) !== 0) throw new Error("Encoder could not start.");
  new Uint8Array(wasm.memory.buffer, wasm.sstv_image(), rgb.length).set(rgb);

  chunks = [];
  marks = [];
  post(`Using ${m.family} ${m.name} at ${sr} Hz`);
  if (vox) {
    post("Generating VOX intro code...");
    wasm.sstv_intro();
  }
  post(m.family === "FAX" ? "Generating header and phasing..." : "Generating header and VIS code...");
  wasm.sstv_header();

  post("Encoding image data...");
  for (let y = 0; y < m.height; y++) wasm.sstv_line(y);
  wasm.sstv_finish();

  const parts = chunks;
  chunks = [];
  const strip = render(joinMarks(marks), sr);
  marks = [];
  const bytes = parts.reduce((n, c) => n + c.byteLength, 0);
  if (!raw) parts.unshift(wavHeader(sr, bytes));

  const base = file.name.replace(/\.[^.]*$/, "");
  const name = `${base}_${m.name}.${raw ? "raw" : "wav"}`;
  const blob = new Blob(parts, { type: raw ? "application/octet-stream" : "audio/wav" });
  self.postMessage({ done: blob, name, raw, strip }, strip ? [strip.pixels] : []);
}

const ready = load();
ready.then(
  (modes) => self.postMessage({ modes }),
  (err) => self.postMessage({ error: `Encoder failed to load: ${err.message}` }),
);

self.onmessage = async (e) => {
  try {
    await encode(e.data, await ready);
  } catch (err) {
    chunks = [];
    marks = [];
    self.postMessage({ error: err.message || "Encoding failed." });
  }
};
