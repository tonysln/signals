import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import uuid

from flask import (Flask, Response, abort, render_template, request,
                   stream_with_context)
from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SSTV_DIR = os.path.join(ROOT, "sstv")

sys.path.insert(0, SSTV_DIR)
import encoder as enc  # noqa: E402

# Same names as sstv.py's ENCODERS; importing sstv.py itself would load the
# C libraries relative to the current directory.
ENCODERS = {
    "Martin": enc.MartinEncoder,
    "Scottie": enc.ScottieEncoder,
    "Wrasse": enc.WrasseEncoder,
    "Pasokon": enc.PasokonEncoder,
    "FAX": enc.FAXEncoder,
    "Robot": enc.RobotEncoder,
    "PD": enc.PDEncoder,
}
IMAGE_EXTS = {"png", "jpg", "jpeg", "bmp"}
SAMPLE_RATES = [8000, 11025, 16000, 22050, 32000, 44100, 48000, 96000]
DEFAULT_SR = 44100

# Runs sstv.py with INFO logging so its progress messages reach stderr
# (sstv.py's own basicConfig is a no-op once logging is configured).
RUNNER = (
    "import logging, runpy, sys;"
    "logging.basicConfig(level=logging.INFO, format='%(levelname)s:%(message)s');"
    "sys.argv = ['sstv.py', *sys.argv[1:]];"
    "runpy.run_path('sstv.py', run_name='__main__')"
)

# Finished outputs wait here until the browser fetches them once
JOBS_DIR = tempfile.mkdtemp(prefix="sstv-jobs-")
JOB_TTL = 600  # seconds

app = Flask(__name__)


def prune_jobs():
    now = time.time()
    for name in os.listdir(JOBS_DIR):
        path = os.path.join(JOBS_DIR, name)
        if now - os.path.getmtime(path) > JOB_TTL:
            shutil.rmtree(path, ignore_errors=True)


def stretch(src, dst, width, height):
    # Fit exactly to the mode, ignoring aspect ratio (like magick's WxH!)
    with Image.open(src) as im:
        im = im.convert("RGB")
        if im.size != (width, height):
            im = im.resize((width, height), Image.Resampling.LANCZOS)
        im.save(dst, "PNG")


def event(**kw):
    return json.dumps(kw) + "\n"


@app.get("/")
def index():
    modes = {name: cls.opts for name, cls in ENCODERS.items()}
    return render_template("index.html", modes=modes, rates=SAMPLE_RATES,
                           default_sr=DEFAULT_SR)


@app.post("/encode")
def encode():
    image = request.files.get("image")
    encoding = request.form.get("encoding", "")
    mode = request.form.get("mode", "")
    raw = bool(request.form.get("raw"))
    vox = bool(request.form.get("vox"))
    resize = bool(request.form.get("resize"))

    if not image or not image.filename:
        return "No image provided.", 400
    ext = image.filename.rsplit(".", 1)[-1].lower()
    if ext not in IMAGE_EXTS:
        return "Image must be PNG, JPEG or BMP.", 400
    if encoding not in ENCODERS or mode not in ENCODERS[encoding].opts:
        return "Unknown encoding or mode.", 400
    try:
        sr = int(request.form.get("sr", DEFAULT_SR))
    except ValueError:
        return "Sample rate must be a number.", 400
    if sr not in SAMPLE_RATES:
        return "Unsupported sample rate.", 400

    prune_jobs()
    job = uuid.uuid4().hex
    job_dir = os.path.join(JOBS_DIR, job)
    os.mkdir(job_dir)

    src = os.path.join(job_dir, f"in.{ext}")
    image.save(src)

    base = image.filename.rsplit(".", 1)[0]
    name = f"{base}_{mode}." + ("raw" if raw else "wav")
    out = os.path.join(job_dir, "out")
    dims = ENCODERS[encoding].opts[mode]
    size = "{width}x{height}".format(**dims)

    @stream_with_context
    def run():
        nonlocal src
        ok = False
        try:
            if resize:
                yield event(msg=f"Resizing image to {size}...")
                resized = os.path.join(job_dir, "resized.png")
                try:
                    stretch(src, resized, dims["width"], dims["height"])
                except Exception as e:
                    yield event(error=f"Resize failed: {e}")
                    return
                src = resized

            yield event(msg="Starting encoder...")
            cmd = [sys.executable, "-c", RUNNER, "--encode", src, "--out", out,
                   "--encoding", encoding, "--mode", mode, "--sr", str(sr)]
            if vox:
                cmd.append("--vox")
            if raw:
                cmd.append("--raw")

            # sstv.py expects to run from its own folder (../lib/libimg.so)
            proc = subprocess.Popen(cmd, cwd=SSTV_DIR, stdout=subprocess.DEVNULL,
                                    stderr=subprocess.PIPE, text=True, bufsize=1)
            error = None
            for line in proc.stderr:
                level, _, msg = line.strip().partition(":")
                if not msg:
                    continue
                # Hide server paths; the final "Done." is sent below
                msg = msg.replace(src, image.filename)
                if msg == "Done." or msg.startswith("Wrote output"):
                    continue
                if level == "ERROR":
                    error = error or msg
                elif level == "WARNING":
                    yield event(warn=msg.removeprefix("Error: "))
                else:
                    yield event(msg=msg)
            proc.wait()

            if proc.returncode == 3:  # sstv.py: image smaller than the mode
                yield event(error=f"Image is smaller than {size}; enable resize.")
                return
            if proc.returncode != 0 or not os.path.exists(out):
                yield event(error=error or "Encoding failed.")
                return

            with open(os.path.join(job_dir, "name"), "w") as f:
                f.write(name)
            ok = True
            yield event(done=job, name=name, raw=raw)
        finally:
            for p in (os.path.join(job_dir, f"in.{ext}"), src):
                if os.path.exists(p):
                    os.remove(p)
            if not ok:
                shutil.rmtree(job_dir, ignore_errors=True)

    return Response(run(), mimetype="application/x-ndjson",
                    headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"})


@app.get("/result/<job>")
def result(job):
    if len(job) != 32 or not job.isalnum():
        abort(404)
    job_dir = os.path.join(JOBS_DIR, job)
    out = os.path.join(job_dir, "out")
    if not os.path.exists(out):
        abort(404)

    with open(os.path.join(job_dir, "name")) as f:
        name = f.read()
    with open(out, "rb") as f:
        data = f.read()
    # One-shot: nothing stays on disk after the browser has it
    shutil.rmtree(job_dir, ignore_errors=True)

    mimetype = "application/octet-stream" if name.endswith(".raw") else "audio/wav"
    return Response(data, mimetype=mimetype, headers={
        "Content-Disposition": f'attachment; filename="{name}"',
        "Cache-Control": "no-store",
    })


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5001)
