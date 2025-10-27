#!/usr/bin/env python3
print("Starting visualization script...")

try:
    import gpxpy
    print("✓ gpxpy imported")
except ImportError as e:
    print(f"✗ gpxpy import failed: {e}")

try:
    import folium
    print("✓ folium imported")
except ImportError as e:
    print(f"✗ folium import failed: {e}")

import sys
print(f"Python path: {sys.executable}")
print(f"Arguments: {sys.argv}")

if len(sys.argv) > 1:
    gpx_file = sys.argv[1]
    print(f"GPX file: {gpx_file}")
    
    try:
        with open(gpx_file, 'r') as f:
            gpx = gpxpy.parse(f)
        print(f"✓ GPX file parsed successfully")
        print(f"  Tracks: {len(gpx.tracks)}")
        print(f"  Waypoints: {len(gpx.waypoints)}")
    except Exception as e:
        print(f"✗ GPX parsing failed: {e}")
else:
    print("No GPX file provided")