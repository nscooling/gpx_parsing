#!/usr/bin/env python3
import gpxpy
import folium
import argparse
import os
from folium import plugins
import re


def parse_args():
    parser = argparse.ArgumentParser(description="Visualize GPX route with amenities using Folium")
    parser.add_argument("gpx_file", help="GPX file with route and amenities")
    parser.add_argument("-o", "--output", default=None,
                        help="Output HTML file (default: input filename with '.html' extension)")
    return parser.parse_args()


def get_amenity_icon_color(amenity_type, symbol):
    """Return appropriate Font Awesome icon name and color for amenity types."""
    type_map = {
        "Cafe": ("coffee", "orange"),
        "Restaurant": ("cutlery", "red"),
        "Pub/Bar": ("beer", "darkred"),     # <- fixed: use 'beer' instead of 'glass'
        "Fast Food": ("cutlery", "pink"),
        "Toilets": ("male", "blue"),
        "Water Source": ("tint", "lightblue"),
        "Fuel Station": ("car", "orange"),
        "Bike Shop": ("bicycle", "green"),
    }
    if amenity_type in type_map:
        return type_map[amenity_type]

    icon_map = {
        "Restaurant": ("cutlery", "red"),
        "Restroom": ("male", "blue"),
        "Water Source": ("tint", "lightblue"),
        "Gas Station": ("car", "orange"),
        "Bike Trail": ("bicycle", "green"),
        "Waypoint": ("info-circle", "gray"),
    }
    return icon_map.get(symbol, ("info-circle", "gray"))



def parse_description(desc: str):
    """Extract distance fields and return (clean_desc, from_km, remain_km, off_m)."""
    if not desc:
        return "", None, None, None

    m_start = re.search(r"Route km:\s*([0-9]+(?:\.[0-9]+)?)", desc)
    m_rem = re.search(r"Remaining:\s*([0-9]+(?:\.[0-9]+)?)km", desc)
    m_off = re.search(r"Off route:\s*([0-9]+)m", desc)

    start_km = float(m_start.group(1)) if m_start else None
    remain_km = float(m_rem.group(1)) if m_rem else None
    off_m = int(m_off.group(1)) if m_off else None

    clean = re.sub(r"\.?\s*Route km:\s*[0-9]+(?:\.[0-9]+)?", "", desc)
    clean = re.sub(r"\,?\s*Remaining:\s*[0-9]+(?:\.[0-9]+)?km", "", clean)
    clean = re.sub(r"\,?\s*Off route:\s*[0-9]+m", "", clean)
    clean = re.sub(r"\.?\s*Website:\s*\S+", "", clean)
    clean = clean.strip()
    if clean.endswith("."):
        clean = clean[:-1]
    return clean, start_km, remain_km, off_m


def create_folium_map(gpx_file, output_file):
    with open(gpx_file, "r") as f:
        gpx = gpxpy.parse(f)

    track_points = []
    for track in gpx.tracks:
        for segment in track.segments:
            for point in segment.points:
                track_points.append([point.latitude, point.longitude])

    if not track_points:
        print("No track points found in GPX file")
        return

    center_lat = sum(p[0] for p in track_points) / len(track_points)
    center_lon = sum(p[1] for p in track_points) / len(track_points)

    m = folium.Map(location=[center_lat, center_lon], zoom_start=12, tiles="OpenStreetMap")

    folium.PolyLine(track_points, color="blue", weight=4, opacity=0.8, popup="GPX Route").add_to(m)

    # Start / End markers
    folium.Marker(track_points[0], popup="Start", icon=folium.Icon(color="green", icon="play")).add_to(m)
    folium.Marker(track_points[-1], popup="End", icon=folium.Icon(color="red", icon="stop")).add_to(m)

    # Group waypoints by amenity type
    amenity_groups = {}

    for waypoint in gpx.waypoints:
        lat, lon = waypoint.latitude, waypoint.longitude
        name = waypoint.name or "Unnamed"
        description = waypoint.description or ""
        symbol = waypoint.symbol or "Waypoint"
        amenity_type = waypoint.type or "Amenity"

        icon_name, color = get_amenity_icon_color(amenity_type, symbol)
        clean_desc, start_km, remain_km, off_m = parse_description(description)

        dist_lines = []
        if start_km is not None:
            dist_lines.append(f"From start: {start_km:.1f} km")
        if remain_km is not None:
            dist_lines.append(f"Remaining: {remain_km:.1f} km")
        if off_m is not None:
            dist_lines.append(f"Off route: {off_m} m")

        dist_html = "<br>".join(dist_lines)
        popup_content = f"""
        <b>{name}</b><br>
        Type: {amenity_type}<br>
        {dist_html}<br><em>{clean_desc}</em>
        """

        marker = folium.Marker(
            [lat, lon],
            popup=folium.Popup(popup_content, max_width=300),
            tooltip=f"{name} ({amenity_type})",
            icon=folium.Icon(color=color, icon=icon_name, prefix="fa"),
        )

        # Collect markers per type
        if amenity_type not in amenity_groups:
            amenity_groups[amenity_type] = folium.FeatureGroup(name=amenity_type)
        marker.add_to(amenity_groups[amenity_type])

    # Add grouped layers to map
    for group in amenity_groups.values():
        group.add_to(m)

    # Layer control (shows Waypoints toggle)
    folium.LayerControl(collapsed=False).add_to(m)

    # Save map
    m.save(output_file)
    print(f"✅ Map saved to {output_file}")


def main():
    args = parse_args()
    output_file = args.output or os.path.splitext(args.gpx_file)[0] + "_map.html"
    create_folium_map(args.gpx_file, output_file)


if __name__ == "__main__":
    main()
