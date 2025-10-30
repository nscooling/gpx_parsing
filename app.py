from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    flash,
    send_file
)
from pathlib import Path
from werkzeug.utils import secure_filename
import subprocess
import os

app = Flask(__name__)
app.secret_key = "some_secret_string_here"

# Always use absolute paths and ensure writable directory for files
BASE_DIR = Path(__file__).resolve().parent
UPLOAD_DIR = BASE_DIR / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)


def run_script(script: Path, args: list, cwd: Path):
    """
    Run a Python script in a subprocess; return (rc, stdout, stderr).
    Ensures that both the script path and CWD are resolved.
    """
    script = script.resolve()
    cwd = cwd.resolve()

    python_cmd = os.environ.get("PYTHON")
    if python_cmd:
        interpreter = os.fspath(Path(python_cmd).expanduser())
    else:
        interpreter = os.fspath(Path(os.sys.executable))

    cmd = [interpreter, os.fspath(script), *args]

    proc = subprocess.run(
        cmd,
        cwd=os.fspath(cwd),
        capture_output=True,
        text=True
    )
    return proc.returncode, proc.stdout, proc.stderr


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/upload", methods=["POST"])
def upload():
    file = request.files.get("file")

    if not file:
        flash("No file uploaded.", "error")
        return redirect(url_for("index"))

    filename = secure_filename(file.filename)
    input_path = (UPLOAD_DIR / filename).resolve()
    file.save(input_path)

    enriched_name = filename.rsplit(".", 1)[0] + "_enriched.gpx"
    enriched_path = (UPLOAD_DIR / enriched_name).resolve()

    enrich_script = (BASE_DIR / "find_amenities_near_route.py").resolve()

    if not enrich_script.exists():
        flash("Server misconfiguration: find_amenities_near_route.py not found.", "error")
        return redirect(url_for("index"))

    # Run enrichment script
    rc, out, err = run_script(
        enrich_script,
        [os.fspath(input_path), "-o", os.fspath(enriched_path)],
        cwd=BASE_DIR
    )

    # Render results page (always show stdout/stderr)
    return render_template(
        "result.html",
        filename=enriched_name,
        success=(rc == 0 and enriched_path.exists()),
        stdout=out.strip(),
        stderr=err.strip(),
    )


@app.route("/download/<path:filename>")
def download(filename):
    file_path = (UPLOAD_DIR / filename).resolve()
    return send_file(file_path, as_attachment=True)


if __name__ == "__main__":
    # Recommended: use `flask run` in dev. This fallback is fine.
    app.run(debug=True, port=5050)
