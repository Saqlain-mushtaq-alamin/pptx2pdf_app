import os
import sys
import subprocess
import tempfile
import shutil
import zipfile
from pathlib import Path
from flask import Flask, request, render_template, send_file, jsonify

app = Flask(__name__)

# ---- CONFIGURE THIS IF NEEDED ----
# Common Windows install paths for LibreOffice. The app will try each one.
POSSIBLE_SOFFICE_PATHS = [
    r"C:\Program Files\LibreOffice\program\soffice.exe",
    r"C:\Program Files (x86)\LibreOffice\program\soffice.exe",
    "soffice",  # fallback: assume it's on PATH (works on Mac/Linux too)
]

def find_soffice():
    for path in POSSIBLE_SOFFICE_PATHS:
        if path == "soffice":
            return path  # let subprocess try PATH resolution
        if os.path.exists(path):
            return path
    return "soffice"

SOFFICE = find_soffice()


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/convert", methods=["POST"])
def convert():
    files = request.files.getlist("files")
    if not files:
        return jsonify({"error": "No files uploaded"}), 400

    work_dir = tempfile.mkdtemp(prefix="pptx2pdf_")
    output_dir = os.path.join(work_dir, "output")
    os.makedirs(output_dir, exist_ok=True)

    results = []

    try:
        for f in files:
            if not f.filename.lower().endswith((".pptx", ".ppt")):
                results.append({"name": f.filename, "status": "skipped (not pptx/ppt)"})
                continue

            saved_path = os.path.join(work_dir, f.filename)
            f.save(saved_path)

            proc = subprocess.run(
                [SOFFICE, "--headless", "--convert-to", "pdf", "--outdir", output_dir, saved_path],
                capture_output=True, text=True, timeout=120
            )

            pdf_name = Path(f.filename).stem + ".pdf"
            pdf_path = os.path.join(output_dir, pdf_name)

            if proc.returncode == 0 and os.path.exists(pdf_path):
                results.append({"name": f.filename, "status": "converted"})
            else:
                results.append({"name": f.filename, "status": "failed", "error": proc.stderr.strip()[:300]})

        pdf_files = list(Path(output_dir).glob("*.pdf"))
        if not pdf_files:
            return jsonify({"error": "No files were converted successfully", "details": results}), 500

        zip_path = os.path.join(work_dir, "converted_pdfs.zip")
        with zipfile.ZipFile(zip_path, "w") as zf:
            for pdf in pdf_files:
                zf.write(pdf, arcname=pdf.name)

        response = send_file(zip_path, as_attachment=True, download_name="converted_pdfs.zip")
        return response

    finally:
        # Cleanup happens after response is sent (best-effort)
        pass


if __name__ == "__main__":
    print(f"Using LibreOffice at: {SOFFICE}")
    print("Open http://127.0.0.1:5000 in your browser")
    app.run(debug=False, port=5000)
