import os, subprocess, tempfile, zipfile, json, time, uuid, threading
from pathlib import Path
from flask import Flask, request, render_template, send_file, jsonify, Response

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 500 * 1024 * 1024  # 500 MB max upload

# ── LibreOffice detection ────────────────────────────────────────────────────
POSSIBLE_SOFFICE = [
    r"C:\Program Files\LibreOffice\program\soffice.exe",
    r"C:\Program Files (x86)\LibreOffice\program\soffice.exe",
    "/usr/bin/soffice",
    "/usr/local/bin/soffice",
    "soffice",
]

def find_soffice():
    for p in POSSIBLE_SOFFICE:
        if p == "soffice":
            return p
        if os.path.exists(p):
            return p
    return "soffice"

SOFFICE = find_soffice()

# ── Conversion matrix ────────────────────────────────────────────────────────
# Maps input extension → list of valid output formats
CONVERSION_MAP = {
    ".pptx": ["pdf", "png", "jpg", "docx", "html", "txt"],
    ".ppt":  ["pdf", "png", "jpg", "docx", "html", "txt"],
    ".odp":  ["pdf", "png", "jpg", "pptx", "html"],
    ".docx": ["pdf", "html", "txt", "odt"],
    ".doc":  ["pdf", "html", "txt", "docx"],
    ".odt":  ["pdf", "docx", "html", "txt"],
    ".rtf":  ["pdf", "docx", "html", "txt"],
    ".xlsx": ["pdf", "html", "csv", "ods"],
    ".xls":  ["pdf", "html", "csv", "xlsx"],
    ".ods":  ["pdf", "xlsx", "csv", "html"],
    ".csv":  ["pdf", "xlsx", "ods"],
    ".html": ["pdf", "docx", "txt"],
    ".txt":  ["pdf", "docx", "html"],
}

ALL_FORMATS = sorted({fmt for fmts in CONVERSION_MAP.values() for fmt in fmts})

# LibreOffice filter overrides for certain formats
LO_FORMAT_FILTER = {
    "docx": "docx",
    "xlsx": "xlsx",
    "pptx": "pptx",
    "txt":  "txt",
    "csv":  "csv",
    "ods":  "ods",
    "odt":  "odt",
}

# ── Job store ────────────────────────────────────────────────────────────────
jobs: dict = {}
jobs_lock = threading.Lock()


def push_event(job_id: str, event: dict):
    with jobs_lock:
        if job_id in jobs:
            jobs[job_id]["events"].append(event)


# ── Conversion worker ────────────────────────────────────────────────────────
def convert_worker(job_id, file_paths, output_dir, output_format):
    total = len(file_paths)
    converted = failed = skipped = 0
    t0 = time.time()

    push_event(job_id, {
        "type": "start",
        "total": total,
        "format": output_format,
        "msg": f"Converting {total} file(s) → {output_format.upper()}"
    })

    for idx, fp in enumerate(file_paths, 1):
        fname = os.path.basename(fp)
        ext = Path(fp).suffix.lower()
        allowed = CONVERSION_MAP.get(ext, [])

        if output_format not in allowed:
            skipped += 1
            push_event(job_id, {
                "type": "skip",
                "file": fname, "index": idx, "total": total,
                "msg": f"⊘ {fname} — {ext} cannot convert to {output_format.upper()}"
            })
            continue

        push_event(job_id, {
            "type": "converting",
            "file": fname, "index": idx, "total": total,
            "msg": f"Converting {fname}…"
        })

        # Build soffice command
        cmd = [SOFFICE, "--headless", "--convert-to", output_format,
               "--outdir", output_dir, fp]

        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
            stem = Path(fp).stem
            # For PNG/JPG, LO may produce stem.png or stem1.png stem2.png etc.
            pattern = f"{stem}*.{output_format}"
            found = list(Path(output_dir).glob(pattern))

            if proc.returncode == 0 and found:
                converted += 1
                total_kb = sum(f.stat().st_size for f in found) // 1024
                push_event(job_id, {
                    "type": "done",
                    "file": fname, "index": idx, "total": total,
                    "output_count": len(found), "size_kb": total_kb,
                    "msg": f"✓ {fname} → {len(found)} file(s) ({total_kb} KB)"
                })
            else:
                failed += 1
                err_msg = (proc.stderr or proc.stdout or "unknown error").strip()[:200]
                push_event(job_id, {
                    "type": "error",
                    "file": fname, "index": idx, "total": total,
                    "msg": f"✗ {fname} — {err_msg}"
                })

        except subprocess.TimeoutExpired:
            failed += 1
            push_event(job_id, {
                "type": "error",
                "file": fname, "index": idx, "total": total,
                "msg": f"✗ {fname} — timed out (>180 s)"
            })
        except Exception as e:
            failed += 1
            push_event(job_id, {
                "type": "error",
                "file": fname, "index": idx, "total": total,
                "msg": f"✗ {fname} — {e}"
            })

    # Build ZIP
    out_files = list(Path(output_dir).glob(f"*.{output_format}"))
    zip_path = None
    if out_files:
        zip_path = os.path.join(os.path.dirname(output_dir), "fileforge_output.zip")
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for f in out_files:
                zf.write(f, arcname=f.name)
        zip_kb = os.path.getsize(zip_path) // 1024

    elapsed = round(time.time() - t0, 1)

    with jobs_lock:
        jobs[job_id].update({"done": True, "zip_path": zip_path, "status": "complete"})

    push_event(job_id, {
        "type": "complete",
        "converted": converted, "failed": failed,
        "skipped": skipped, "total": total,
        "elapsed": elapsed,
        "zip_kb": zip_kb if zip_path else 0,
        "has_download": zip_path is not None,
        "msg": (f"Done — {converted} converted, {failed} failed, "
                f"{skipped} skipped in {elapsed}s")
    })


# ── Routes ───────────────────────────────────────────────────────────────────
@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/formats")
def api_formats():
    return jsonify({"conversion_map": CONVERSION_MAP, "all_formats": ALL_FORMATS})


@app.route("/api/convert", methods=["POST"])
def api_convert():
    files = request.files.getlist("files")
    output_format = request.form.get("format", "pdf").lower()

    if not files or all(f.filename == "" for f in files):
        return jsonify({"error": "No files uploaded"}), 400

    job_id = str(uuid.uuid4())
    work_dir = tempfile.mkdtemp(prefix=f"fg_{job_id[:8]}_")
    in_dir = os.path.join(work_dir, "input")
    out_dir = os.path.join(work_dir, "output")
    os.makedirs(in_dir); os.makedirs(out_dir)

    saved = []
    for f in files:
        if not f.filename:
            continue
        safe = Path(f.filename).name
        dest = os.path.join(in_dir, safe)
        f.save(dest)
        saved.append(dest)

    if not saved:
        return jsonify({"error": "No valid files"}), 400

    with jobs_lock:
        jobs[job_id] = {"status": "running", "events": [],
                        "done": False, "zip_path": None, "work_dir": work_dir}

    threading.Thread(
        target=convert_worker,
        args=(job_id, saved, out_dir, output_format),
        daemon=True
    ).start()

    return jsonify({"job_id": job_id, "total": len(saved)})


@app.route("/api/progress/<job_id>")
def api_progress(job_id):
    def stream():
        sent = 0
        while True:
            with jobs_lock:
                job = jobs.get(job_id)
                if not job:
                    yield f"data: {json.dumps({'type':'error','msg':'Job not found'})}\n\n"
                    return
                events = list(job["events"])
                done = job["done"]

            for ev in events[sent:]:
                yield f"data: {json.dumps(ev)}\n\n"
            sent = len(events)

            if done and sent >= len(events):
                return
            time.sleep(0.12)

    return Response(stream(), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.route("/api/download/<job_id>")
def api_download(job_id):
    with jobs_lock:
        job = jobs.get(job_id)
    if not job or not job.get("zip_path"):
        return jsonify({"error": "Result not available"}), 404
    return send_file(job["zip_path"], as_attachment=True,
                     download_name="fileforge_output.zip")


@app.route("/api/soffice-status")
def soffice_status():
    found = any(os.path.exists(p) for p in POSSIBLE_SOFFICE if p != "soffice")
    return jsonify({"path": SOFFICE, "found": found})


if __name__ == "__main__":
    print(f"FileForge — LibreOffice: {SOFFICE}")
    print("→ http://127.0.0.1:5000")
    app.run(debug=False, port=5000, threaded=True)
