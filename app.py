from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    flash,
    send_file,
)
from pathlib import Path
from werkzeug.utils import secure_filename
import subprocess
import uuid
import os

app = Flask(__name__)
app.secret_key = "some_secret_string_here"

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

    job_id = uuid.uuid4().hex
    job_dir = (WORK_DIR / job_id)
    job_dir.mkdir(parents=True, exist_ok=True)

    input_path = (job_dir / filename).resolve()
    file.save(input_path)

    enriched_name = filename.rsplit(".", 1)[0] + "_amenities.gpx"
    enriched_path = (job_dir / enriched_name).resolve()
    map_name = filename.rsplit(".", 1)[0] + "_map.html"
    map_path = (job_dir / map_name).resolve()

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

    success = rc == 0 and enriched_path.exists()

    map_stdout = ""
    map_stderr = ""
    if success:
        vis_script = (BASE_DIR / "visualize_gpx_with_folium.py").resolve()
        if not vis_script.exists():
            vis_script = (BASE_DIR / "generate_map.py").resolve()

        if vis_script.exists():
            rc_map, map_stdout, map_stderr = run_script(
                vis_script,
                [os.fspath(enriched_path), "-o", os.fspath(map_path)],
                cwd=BASE_DIR
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


if __name__ == "__main__":
    # Recommended: use `flask run` in dev. This fallback is fine.
    app.run(debug=True, port=5050)
