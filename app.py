from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    flash,
    send_file,
    abort,
)
from pathlib import Path
from werkzeug.utils import secure_filename
import subprocess
import uuid
import os
import secrets
import mimetypes

from flask_wtf import CSRFProtect
from flask_wtf.csrf import CSRFError, generate_csrf


ALLOWED_EXTENSIONS = {".gpx"}
ALLOWED_MIME_TYPES = {
    "application/gpx+xml",
    "application/xml",
    "text/xml",
}

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY") or secrets.token_hex(32)
app.config["MAX_CONTENT_LENGTH"] = int(os.environ.get("MAX_CONTENT_LENGTH", 20 * 1024 * 1024))
csrf = CSRFProtect(app)


@app.context_processor
def inject_csrf_token():
    return dict(csrf_token=lambda: generate_csrf())

# Always use absolute paths and ensure writable directory for files
BASE_DIR = Path(__file__).resolve().parent
WORK_DIR = BASE_DIR / "uploads"
WORK_DIR.mkdir(exist_ok=True)


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
    if not filename:
        flash("Invalid filename.", "error")
        return redirect(url_for("index"))

    ext = Path(filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        flash("Unsupported file type. Please upload a GPX file.", "error")
        return redirect(url_for("index"))

    # GPX files can have inconsistent MIME types from browsers (application/octet-stream,
    # application/gpx+xml, text/xml, etc.), so we primarily rely on file extension.
    # Only reject if we get a clearly wrong MIME type like image/*, video/*, etc.
    sniff_type = file.mimetype or ""
    if sniff_type:
        # Reject obviously wrong MIME types
        reject_prefixes = ("image/", "video/", "audio/", "application/pdf", "application/zip")
        if any(sniff_type.startswith(prefix) for prefix in reject_prefixes):
            flash("Unsupported MIME type. Please upload a valid GPX file.", "error")
            return redirect(url_for("index"))

    job_id = uuid.uuid4().hex
    job_dir = (WORK_DIR / job_id)
    job_dir.mkdir(parents=True, exist_ok=True)

    input_path = (job_dir / filename).resolve()
    file.save(input_path)

    # Render configuration screen so user can tweak processing parameters before running
    return render_template(
        "configure.html",
        job_id=job_id,
        filename=filename,
        distance_step_default=1000,
        search_radius_default=300,
        min_distance_step=500,
        max_search_radius=1000,
        no_cache_default=False,
    )


@app.route("/configure/<job_id>", methods=["GET"])
def configure(job_id):
    if not job_id.isalnum():
        flash("Invalid job identifier.", "error")
        return redirect(url_for("index"))

    job_dir = (WORK_DIR / job_id)
    if not job_dir.exists():
        flash("Job not found. Please upload the GPX again.", "error")
        return redirect(url_for("index"))

    filename = request.args.get("filename")
    if not filename:
        flash("Missing file reference. Please re-upload.", "error")
        return redirect(url_for("index"))

    input_path = (job_dir / filename).resolve()
    if not input_path.exists() or WORK_DIR not in input_path.parents:
        flash("Uploaded file could not be located. Please re-upload.", "error")
        return redirect(url_for("index"))

    def parse_int(value, fallback):
        try:
            return int(value)
        except (TypeError, ValueError):
            return fallback

    distance_step = parse_int(request.args.get("distance_step"), 1000)
    if distance_step < 500:
        distance_step = 500

    search_radius = parse_int(request.args.get("search_radius"), 300)
    if search_radius > 1000:
        search_radius = 1000
    if search_radius < 50:
        search_radius = 50

    no_cache = request.args.get("no_cache") == "1"

    return render_template(
        "configure.html",
        job_id=job_id,
        filename=filename,
        distance_step_default=distance_step,
        search_radius_default=search_radius,
        min_distance_step=500,
        max_search_radius=1000,
        no_cache_default=no_cache,
    )
@app.route("/process/<job_id>", methods=["POST"])
def process(job_id):
    if not job_id.isalnum():
        flash("Invalid job identifier.", "error")
        return redirect(url_for("index"))

    job_dir = (WORK_DIR / job_id)
    if not job_dir.exists():
        flash("Job not found. Please upload the GPX again.", "error")
        return redirect(url_for("index"))

    filename = request.form.get("filename")
    if not filename:
        flash("Missing original file reference.", "error")
        return redirect(url_for("index"))

    input_path = (job_dir / filename).resolve()
    if not input_path.exists() or WORK_DIR not in input_path.parents:
        flash("Uploaded file could not be located.", "error")
        return redirect(url_for("index"))

    # Sanitize parameter inputs from the form
    def parse_int(name, fallback):
        raw = request.form.get(name)
        try:
            return int(raw)
        except (TypeError, ValueError):
            return fallback

    distance_step = parse_int("distance_step", 1000)
    if distance_step < 500:
        distance_step = 500

    search_radius = parse_int("search_radius", 300)
    if search_radius > 1000:
        search_radius = 1000
    if search_radius < 50:
        search_radius = 50

    use_cache = request.form.get("no_cache") != "on"

    enrich_script = (BASE_DIR / "find_amenities_near_route.py").resolve()

    if not enrich_script.exists():
        flash("Server misconfiguration: find_amenities_near_route.py not found.", "error")
        return redirect(url_for("index"))

    enriched_name = filename.rsplit(".", 1)[0] + "_amenities.gpx"
    enriched_path = (job_dir / enriched_name).resolve()
    map_name = filename.rsplit(".", 1)[0] + "_map.html"
    map_path = (job_dir / map_name).resolve()

    args = [
        os.fspath(input_path),
        "-o",
        os.fspath(enriched_path),
        "-d",
        str(distance_step),
        "-r",
        str(search_radius),
    ]
    if not use_cache:
        args.append("--no-cache")

    rc, out, err = run_script(
        enrich_script,
        args,
        cwd=BASE_DIR,
    )

    success = rc == 0 and enriched_path.exists()

    map_stdout = ""
    map_stderr = ""
    if success:
        vis_script = (BASE_DIR / "visualize_gpx_with_folium.py").resolve()
        fallback_script = (BASE_DIR / "generate_map.py").resolve()

        script_to_use = vis_script if vis_script.exists() else fallback_script if fallback_script.exists() else None

        if script_to_use:
            rc_map, map_stdout, map_stderr = run_script(
                script_to_use,
                [os.fspath(enriched_path), "-o", os.fspath(map_path)],
                cwd=BASE_DIR,
            )
            if rc_map != 0 or not map_path.exists():
                success = False
        else:
            map_stderr = "No map generator script available."
            success = False

    stdout_combined = "\n".join(filter(None, [out.strip(), map_stdout.strip()]))
    stderr_combined = "\n".join(filter(None, [err.strip(), map_stderr.strip()]))

    gpx_available = success and enriched_path.exists()
    map_available = success and map_path.exists()

    gpx_url = url_for("artifact", job_id=job_id, filename=enriched_name) if gpx_available else None
    map_url = url_for("artifact", job_id=job_id, filename=map_name) if map_available else None

    return render_template(
        "result.html",
        success=success,
        stdout=stdout_combined or "",
        stderr=stderr_combined or "",
        job_id=job_id,
        gpx_file=enriched_name if gpx_available else None,
        map_file=map_name if map_available else None,
        gpx_url=gpx_url,
        map_url=map_url,
        distance_step=distance_step,
        search_radius=search_radius,
        original_filename=filename,
    no_cache=not use_cache,
    )


@app.route("/download/<job_id>/<path:filename>")
def download(job_id, filename):
    job_dir = (WORK_DIR / job_id)
    file_path = (job_dir / filename).resolve()
    if not file_path.exists() or WORK_DIR not in file_path.parents:
        flash("Requested file not found.", "error")
        return redirect(url_for("index"))
    return send_file(file_path, as_attachment=True)


@app.route("/artifact/<job_id>/<path:filename>")
def artifact(job_id, filename):
    job_dir = (WORK_DIR / job_id)
    file_path = (job_dir / filename).resolve()
    if not file_path.exists() or WORK_DIR not in file_path.parents:
        flash("Requested file not found.", "error")
        return redirect(url_for("index"))
    return send_file(file_path)


@app.errorhandler(CSRFError)
def handle_csrf_error(err):
    flash("Security token mismatch. Please try again.", "error")
    return redirect(url_for("index"))


if __name__ == "__main__":
    # Recommended: use gunicorn/uwsgi in production; this remains for local dev only.
    debug_enabled = os.environ.get("FLASK_DEBUG") == "1"
    port = int(os.environ.get("PORT", 5050))
    host = os.environ.get("HOST", "127.0.0.1")
    app.run(debug=debug_enabled, host=host, port=port)
