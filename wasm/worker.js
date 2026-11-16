// Runs the SSTV encoder (encoder.wasm) off the main thread.
//
// Messages in:  { file, mode, sr, vox, raw, resize }
// Messages out: { modes } once loaded, then per job { msg } / { warn },
//               finally { done: Blob, name, raw } or { error }

let wasm = null;   // exports
let chunks = [];   // Int16Array blocks emitted by the encoder

const imports = {
  env: {
    sstv_emit(ptr, count) {
      // Copy out: the block is reused and memory may grow later
      chunks.push(new Int16Array(wasm.memory.buffer, ptr, count).slice());
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
  const bytes = parts.reduce((n, c) => n + c.byteLength, 0);
  if (!raw) parts.unshift(wavHeader(sr, bytes));

  const base = file.name.replace(/\.[^.]*$/, "");
  const name = `${base}_${m.name}.${raw ? "raw" : "wav"}`;
  const blob = new Blob(parts, { type: raw ? "application/octet-stream" : "audio/wav" });
  self.postMessage({ done: blob, name, raw });
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
    self.postMessage({ error: err.message || "Encoding failed." });
  }
};
