#!/usr/bin/env python3
import gpxpy
import folium
import argparse
import os
from folium import plugins
from branca.element import Template, MacroElement
from folium import Element
import re

def parse_args():
    parser = argparse.ArgumentParser(description="Visualize GPX route with amenities using Folium")
    parser.add_argument("gpx_file", help="GPX file with route and amenities")
    parser.add_argument("-o", "--output", default=None,
                       help="Output HTML file (default: input filename with '.html' extension)")
    return parser.parse_args()

def get_amenity_icon_color(amenity_type, symbol):
    """Return appropriate Font Awesome icon name and color for amenity types"""

    # Prefer type-based mapping
    if amenity_type:
        type_map = {
            'Cafe': ('coffee', 'orange'),
            'Restaurant': ('cutlery', 'red'),
            'Pub/Bar': ('beer', 'darkred'),
            'Fast Food': ('cutlery', 'pink'),
            'Toilets': ('male', 'blue'),
            'Water Source': ('tint', 'lightblue'),
            'Fuel Station': ('car', 'darkblue'),
            'Bike Shop': ('bicycle', 'green'),
        }
        if amenity_type in type_map:
            return type_map[amenity_type]

    # Fallback based on GPX symbol
    icon_map = {
        'Restaurant': ('cutlery', 'red'),
        'Restroom': ('male', 'blue'),
        'Water Source': ('tint', 'lightblue'),
    'Gas Station': ('car', 'darkblue'),
        'Bike Trail': ('bicycle', 'green'),
        'Waypoint': ('info-circle', 'gray'),
    }
    return icon_map.get(symbol, ('info-circle', 'gray'))

def create_folium_map(gpx_file, output_file):
    """Create an interactive Folium map from GPX data"""
    
    # Parse GPX file
    with open(gpx_file, 'r') as f:
        gpx = gpxpy.parse(f)
    
    # Extract track points
    track_points = []
    for track in gpx.tracks:
        for segment in track.segments:
            for point in segment.points:
                track_points.append([point.latitude, point.longitude])
    
    if not track_points:
        print("No track points found in GPX file")
        return
    
    # Calculate map center
    center_lat = sum(p[0] for p in track_points) / len(track_points)
    center_lon = sum(p[1] for p in track_points) / len(track_points)
    
    # Create map
    m = folium.Map(
        location=[center_lat, center_lon],
        zoom_start=12,
        tiles='OpenStreetMap'
    )
    
    # Add the route as a polyline
    route_line = folium.PolyLine(
        track_points,
        color='blue',
        weight=4,
        opacity=0.8,
        popup='GPX Route'
    )
    route_line.add_to(m)
    
    # Add start and end markers
    if track_points:
        # Start marker (green)
        folium.Marker(
            track_points[0],
            popup='Start',
            tooltip='Route Start',
            icon=folium.Icon(color='green', icon='play')
        ).add_to(m)
        
        # End marker (red)
        folium.Marker(
            track_points[-1],
            popup='End',
            tooltip='Route End',
            icon=folium.Icon(color='red', icon='stop')
        ).add_to(m)
    
    # Add waypoints (amenities)
    amenity_groups = {}
    marker_meta = []  # collect marker JS ids and labels for the toggle control
    
    def parse_description(desc: str):
        """Extract distance fields and return (clean_desc, from_km, remain_km, off_m)."""
        if not desc:
            return '', None, None, None

        # Patterns for distances
        m_start = re.search(r"Route km:\s*([0-9]+(?:\.[0-9]+)?)", desc)
        m_rem = re.search(r"Remaining:\s*([0-9]+(?:\.[0-9]+)?)km", desc)
        m_off = re.search(r"Off route:\s*([0-9]+)m", desc)

        start_km = float(m_start.group(1)) if m_start else None
        remain_km = float(m_rem.group(1)) if m_rem else None
        off_m = int(m_off.group(1)) if m_off else None

        # Remove matched parts and any inline Website text from description
        clean = re.sub(r"\.?\s*Route km:\s*[0-9]+(?:\.[0-9]+)?", "", desc)
        clean = re.sub(r"\,?\s*Remaining:\s*[0-9]+(?:\.[0-9]+)?km", "", clean)
        clean = re.sub(r"\,?\s*Off route:\s*[0-9]+m", "", clean)
        clean = re.sub(r"\.?\s*Website:\s*\S+", "", clean)
        clean = clean.strip()
        if clean.endswith('.'):
            clean = clean[:-1]
        return clean, start_km, remain_km, off_m

    for waypoint in gpx.waypoints:
        lat, lon = waypoint.latitude, waypoint.longitude
        name = waypoint.name or 'Unnamed'
        description = waypoint.description or ''
        symbol = waypoint.symbol or 'Waypoint'
        amenity_type = waypoint.type or 'Amenity'
        
        # Get appropriate icon and color
        icon_name, color = get_amenity_icon_color(amenity_type, symbol)

        # Include clickable website link if present in GPX
        link_html = ""
        if getattr(waypoint, 'link', None):
            link_text = getattr(waypoint, 'link_text', None) or getattr(waypoint, 'link', '')
            link_href = getattr(waypoint, 'link', '')
            link_html = f"<br>Website: <a href=\"{link_href}\" target=\"_blank\" rel=\"noopener\">{link_text}</a>"

        # Parse distances from description and build a neat section
        clean_desc, start_km, remain_km, off_m = parse_description(description)
        dist_lines = []
        if start_km is not None:
            dist_lines.append(f"From start: {start_km:.1f} km")
        if remain_km is not None:
            dist_lines.append(f"Remaining: {remain_km:.1f} km")
        if off_m is not None:
            dist_lines.append(f"Off route: {off_m} m")
        dist_html = "<br>".join(dist_lines)

        desc_html = f"<br><em>{clean_desc}</em>" if clean_desc else ""
        distances_block = f"<div style=\"margin-top:4px;color:#333\">{dist_html}</div>" if dist_html else ""
        popup_content = f"""
        <b>{name}</b><br>
        Type: {amenity_type}
        {distances_block}
        {desc_html}
        {link_html}
        """

        # Create marker
        marker = folium.Marker(
            [lat, lon],
            popup=folium.Popup(popup_content, max_width=300),
            tooltip=f"{name} ({amenity_type})",
            icon=folium.Icon(color=color, icon=icon_name, prefix='fa')
        )
        
        # Group markers by type for layer control
        if amenity_type not in amenity_groups:
            amenity_groups[amenity_type] = folium.FeatureGroup(name=amenity_type)
            amenity_groups[amenity_type].add_to(m)
        
        marker.add_to(amenity_groups[amenity_type])
        # Record marker meta for interactive toggle
        try:
            marker_meta.append({
                "id": marker.get_name(),
                "label": f"{name} ({amenity_type})",
                "cluster": None
            })
        except Exception:
            pass
    
    # Add layer control to toggle amenity types
    folium.LayerControl().add_to(m)
    
    # Add a marker cluster for better performance with many markers
    if len(gpx.waypoints) > 50:
        marker_cluster = plugins.MarkerCluster().add_to(m)
        cluster_js_name = marker_cluster.get_name()
        
        for waypoint in gpx.waypoints:
            lat, lon = waypoint.latitude, waypoint.longitude
            name = waypoint.name or 'Unnamed'
            description = waypoint.description or ''
            symbol = waypoint.symbol or 'Waypoint'
            amenity_type = waypoint.type or 'Amenity'
            
            icon_name, color = get_amenity_icon_color(amenity_type, symbol)

            link_html = ""
            if getattr(waypoint, 'link', None):
                link_text = getattr(waypoint, 'link_text', None) or getattr(waypoint, 'link', '')
                link_href = getattr(waypoint, 'link', '')
                link_html = f"<br>Website: <a href=\"{link_href}\" target=\"_blank\" rel=\"noopener\">{link_text}</a>"

            clean_desc, start_km, remain_km, off_m = parse_description(description)
            dist_lines = []
            if start_km is not None:
                dist_lines.append(f"From start: {start_km:.1f} km")
            if remain_km is not None:
                dist_lines.append(f"Remaining: {remain_km:.1f} km")
            if off_m is not None:
                dist_lines.append(f"Off route: {off_m} m")
            dist_html = "<br>".join(dist_lines)

            desc_html = f"<br><em>{clean_desc}</em>" if clean_desc else ""
            distances_block = f"<div style=\"margin-top:4px;color:#333\">{dist_html}</div>" if dist_html else ""
            popup_content = f"""
            <b>{name}</b><br>
            Type: {amenity_type}
            {distances_block}
            {desc_html}
            {link_html}
            """

            marker = folium.Marker(
                [lat, lon],
                popup=folium.Popup(popup_content, max_width=300),
                tooltip=f"{name} ({amenity_type})",
                icon=folium.Icon(color=color, icon=icon_name, prefix='fa')
            )
            marker.add_to(marker_cluster)
            # Record marker meta for interactive toggle with cluster reference
            try:
                marker_meta.append({
                    "id": marker.get_name(),
                    "label": f"{name} ({amenity_type})",
                    "cluster": cluster_js_name
                })
            except Exception:
                pass
    
    # Add fullscreen button
    plugins.Fullscreen().add_to(m)
    
    # Add measure control
    plugins.MeasureControl().add_to(m)

    # Inject interactive waypoint toggle control (per-marker checkboxes)
    import json as _json
    marker_meta_json = _json.dumps(marker_meta)
    map_var = m.get_name()
    raw_tpl = """
{% macro html(this, kwargs) %}
<style>
    .wpt-toggle-control {
        background: rgba(255,255,255,0.95);
        padding: 8px;
        border-radius: 4px;
        box-shadow: 0 1px 4px rgba(0,0,0,0.3);
        max-height: 240px;
        overflow: auto;
        font: 12px/1.2 Arial, sans-serif;
    }
    .wpt-toggle-control h4 { margin: 0 0 6px 0; font-size: 13px; }
    .wpt-toggle-actions { margin-bottom: 6px; }
    .wpt-toggle-actions button { margin-right: 6px; }
    .wpt-item { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
</style>
<script>
(function() {
    // Safely resolve the map object by name; avoid referencing the variable before it exists
    var mapName = "__MAP__";
    function getMap() {
        try { return window[mapName]; } catch (e) { return null; }
    }
    var map = getMap();
    var meta = __META__;
    if (!meta || !meta.length) return;

    function allReady() {
        try {
            for (var i=0;i<meta.length;i++) {
                var id = meta[i].id;
                var exists = false;
                try { exists = !!eval(id); } catch(err) { exists = false; }
                if (!exists) return false;
            }
            return true;
        } catch(err) { return false; }
    }

    function build() {
        window._wptRegistry = window._wptRegistry || {};
        window._wptHidden = window._wptHidden || new Set();

        // Resolve marker variables and optionally cluster groups
        meta.forEach(function(e) {
            try {
                window._wptRegistry[e.id] = { marker: eval(e.id), cluster: e.cluster ? eval(e.cluster) : null };
            } catch(err) {}
        });

        // Control UI
        var Control = L.Control.extend({
            options: { position: 'topleft' },
            onAdd: function(map) {
                var container = L.DomUtil.create('div', 'leaflet-control wpt-toggle-control');
                var title = L.DomUtil.create('h4', '', container); title.textContent = 'Waypoints';
                var actions = L.DomUtil.create('div', 'wpt-toggle-actions', container);
                var btnAll = L.DomUtil.create('button', '', actions); btnAll.type='button'; btnAll.textContent='All';
                var btnNone = L.DomUtil.create('button', '', actions); btnNone.type='button'; btnNone.textContent='None';

                var list = L.DomUtil.create('div', '', container);

                function setCheckedAll(flag) {
                    var inputs = list.querySelectorAll('input[type=checkbox]');
                    inputs.forEach(function(cb) {
                        if (cb.checked !== flag) { cb.checked = flag; toggleOne(cb.dataset.id, flag); }
                    });
                }

                btnAll.onclick = function(e) { setCheckedAll(true); };
                btnNone.onclick = function(e) { setCheckedAll(false); };

                meta.forEach(function(e, idx) {
                    var row = L.DomUtil.create('div', 'wpt-item', list);
                    var id = e.id;
                    var cb = L.DomUtil.create('input', '', row); cb.type='checkbox'; cb.checked = !window._wptHidden.has(id); cb.dataset.id = id; cb.id = 'wpt_' + idx;
                    var label = L.DomUtil.create('label', '', row); label.htmlFor = cb.id; label.textContent = ' ' + e.label;
                    cb.onchange = function() { toggleOne(id, cb.checked); };
                });

                L.DomEvent.disableClickPropagation(container);
                return container;
            }
        });

        function toggleOne(id, visible) {
            var rec = window._wptRegistry[id]; if (!rec || !rec.marker) return;
            var mk = rec.marker;
            var cl = rec.cluster;
            if (visible) {
                window._wptHidden.delete(id);
                try { if (cl) cl.addLayer(mk); else map.addLayer(mk); } catch(err) {}
            } else {
                window._wptHidden.add(id);
                try { if (cl) cl.removeLayer(mk); else map.removeLayer(mk); } catch(err) {}
            }
        }

        // Re-apply hidden set when overlays are toggled (LayerControl)
        map.on('overlayadd', function() {
            window._wptHidden.forEach(function(id) {
                var rec = window._wptRegistry[id]; if (!rec || !rec.marker) return;
                try { if (rec.cluster) rec.cluster.removeLayer(rec.marker); else if (map.hasLayer(rec.marker)) map.removeLayer(rec.marker); } catch(err) {}
            });
        });

        new Control().addTo(map);
    }

        function wait(attempts) {
            // Ensure both map object and all markers exist
            if (!map) { map = getMap(); }
            if ((!!map && allReady()) || attempts <= 0) { if (!!map) build(); return; }
            setTimeout(function() { wait(attempts - 1); }, 80);
    }

    wait(200);
})();
</script>
{% endmacro %}
"""
    # Inject map var name and meta JSON via simple placeholder replacement
    script_filled = raw_tpl.replace('__MAP__', map_var).replace('__META__', marker_meta_json)
    toggle_tpl = Template(script_filled)
    macro = MacroElement()
    macro._template = toggle_tpl
    m.get_root().add_child(macro)

    # LayerControl toolbar helper to restore check-all/uncheck-all actions
    layer_control_js = """
    <script>
    (function() {
        function enhanceLayerControl() {
            var list = document.querySelector('.leaflet-control-layers-list');
            if (!list || list.querySelector('.wpt-layer-actions')) { return; }

            var container = document.createElement('div');
            container.className = 'wpt-layer-actions';
            container.style.margin = '4px 0 6px';
            container.style.display = 'flex';
            container.style.gap = '6px';

            function makeButton(label) {
                var btn = document.createElement('button');
                btn.type = 'button';
                btn.textContent = label;
                btn.style.padding = '2px 6px';
                btn.style.border = '1px solid #bbb';
                btn.style.background = '#f6f8fa';
                btn.style.cursor = 'pointer';
                btn.style.fontSize = '11px';
                btn.style.lineHeight = '1.2';
                btn.style.borderRadius = '3px';
                return btn;
            }

            var allBtn = makeButton('All');
            allBtn.addEventListener('click', function(ev) {
                ev.preventDefault();
                var boxes = list.querySelectorAll('input[type="checkbox"]');
                boxes.forEach(function(cb) { if (!cb.checked) { cb.click(); } });
            });

            var noneBtn = makeButton('None');
            noneBtn.addEventListener('click', function(ev) {
                ev.preventDefault();
                var boxes = list.querySelectorAll('input[type="checkbox"]');
                boxes.forEach(function(cb) { if (cb.checked) { cb.click(); } });
            });

            container.appendChild(allBtn);
            container.appendChild(noneBtn);
            list.insertBefore(container, list.firstChild);
        }

        if (document.readyState === 'complete' || document.readyState === 'interactive') {
            setTimeout(enhanceLayerControl, 0);
        } else {
            document.addEventListener('DOMContentLoaded', enhanceLayerControl);
        }
    })();
    </script>
    """
    m.get_root().html.add_child(Element(layer_control_js))

    # Save map
    m.save(output_file)
    print(f"Interactive map saved to: {output_file}")
    print(f"Open in browser: file://{os.path.abspath(output_file)}")
    
    # Print statistics
    print(f"\nMap Statistics:")
    print(f"- Route points: {len(track_points)}")
    print(f"- Waypoints: {len(gpx.waypoints)}")
    print(f"- Amenity types: {len(amenity_groups)}")
    for amenity_type, group in amenity_groups.items():
        count = len([wp for wp in gpx.waypoints if wp.type == amenity_type])
        print(f"  - {amenity_type}: {count}")

def main():
    args = parse_args()
    
    # Set default output filename
    if args.output is None:
        base_name = os.path.splitext(args.gpx_file)[0]
        args.output = f"{base_name}_map.html"
    
    create_folium_map(args.gpx_file, args.output)

if __name__ == "__main__":
    main()