# GPX Amenities Web App

This adds a simple Flask app to upload a GPX file, validate it, enrich it with amenities via Overpass, and render an interactive Folium map. You can download the enriched GPX and the generated HTML map.

## ToDo

* add converience stores
* add supermarkets

## Quick start

1. Create/activate a virtualenv (optional if you already have one)
2. Install requirements
3. Run the Flask app

```bash
# macOS / zsh
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export FLASK_SECRET_KEY="dev"  # required for session signing
FLASK_DEBUG=1 python app.py  # starts on http://127.0.0.1:5050 by default
```

Open http://127.0.0.1:5050, upload a `.gpx` and wait for processing.

## Production (Gunicorn)

Set a strong `FLASK_SECRET_KEY` and run the app via Gunicorn.

```bash
export FLASK_SECRET_KEY="$(openssl rand -hex 32)"
gunicorn --bind 0.0.0.0:5050 app:app
```

This command runs a production-grade WSGI server. Adjust the bind address/port or add workers as needed, e.g. `gunicorn -w 4 --bind 0.0.0.0:${PORT:-5050} app:app`.

## Docker usage

Build the image and run the container if you prefer an isolated environment.

```bash
# Build the image
docker build -t gpx-amenities .

# Run the app (listens on port 5050 inside the container)
docker run --rm \
  -p 5050:5050 \
  -e FLASK_SECRET_KEY="$(openssl rand -hex 32)" \
  gpx-amenities
```

Then open http://localhost:5050 and upload your GPX file. Use `-v "$(pwd)/webdata:/app/webdata"` if you want to persist per-run artifacts outside the container.

Need a different port? Set both the environment variable and the published port, e.g.

```bash
docker run --rm \
  -p 8080:8080 \
  -e PORT=8080 \
  -e FLASK_SECRET_KEY="$(openssl rand -hex 32)" \
  gpx-amenities
```

Re-run `docker build -t gpx-amenities .` whenever you change dependencies or server code so the image picks up the latest updates.

Long-running Overpass batches may exceed Gunicorn's default timeout. Set a higher threshold via `GUNICORN_TIMEOUT`, e.g.

```bash
docker run --rm \
  -p 5050:5050 \
  -e FLASK_SECRET_KEY="$(openssl rand -hex 32)" \
  -e GUNICORN_TIMEOUT=300 \
  gpx-amenities
```

## How it works

- The app stores per-upload artifacts in `webdata/<job_id>/`:
  - `input.gpx` (your upload)
  - `amenities.gpx` (enriched)
  - `map.html` (interactive map)
- It invokes the existing CLI scripts:
  - `find_amenities_near_route.py` to enrich GPX
  - `visualize_gpx_with_folium.py` to generate the map (falls back to `generate_map.py` if needed)
- Results page embeds the map and offers downloads.

## Notes

- Overpass can rate-limit or timeout; the enrich step has retries and local cache (as implemented in your script). If you hit limits, try again later.
- Upload limit is 20MB by default. Adjust `MAX_CONTENT_LENGTH` in `app.py` if needed.
- For production, use a WSGI server (gunicorn/uwsgi) and set a persistent `FLASK_SECRET_KEY`.
