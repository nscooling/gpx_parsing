# GPX Amenities Web App

This adds a simple Flask app to upload a GPX file, validate it, enrich it with amenities via Overpass, and render an interactive Folium map. You can download the enriched GPX and the generated HTML map.

## Quick start

1. Create/activate a virtualenv (optional if you already have one)
2. Install requirements
3. Run the Flask app

```bash
# macOS / zsh
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export FLASK_SECRET_KEY="dev"  # optional
python app.py  # starts on http://localhost:5000
```

Open http://localhost:5000, upload a `.gpx` and wait for processing.

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
