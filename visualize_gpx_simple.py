#!/usr/bin/env python3
import folium
from folium import plugins
import re
import argparse
import os

def parse_args():
    parser = argparse.ArgumentParser(description="Visualize GPX route with amenities using Folium (XML-safe)")
    parser.add_argument("gpx_file", help="GPX file with route and amenities")
    parser.add_argument("-o", "--output", default=None,
                       help="Output HTML file (default: input filename with '.html' extension)")
    return parser.parse_args()

def extract_gpx_data_with_regex(gpx_content):
    """Extract GPX data using regex to avoid XML parsing issues"""
    
    # Extract track points
    track_points = []
    trkpt_pattern = r'<trkpt lat="([^"]+)" lon="([^"]+)"'
    for match in re.finditer(trkpt_pattern, gpx_content):
        lat, lon = float(match.group(1)), float(match.group(2))
        track_points.append([lat, lon])
    
    # Extract waypoints
    waypoints = []
    wpt_pattern = r'<wpt lat="([^"]+)" lon="([^"]+)".*?</wpt>'
    
    for wpt_match in re.finditer(wpt_pattern, gpx_content, re.DOTALL):
        lat, lon = float(wpt_match.group(1)), float(wpt_match.group(2))
        wpt_content = wpt_match.group(0)
        
        # Extract name
        name_match = re.search(r'<name>(.*?)</name>', wpt_content)
        name = name_match.group(1) if name_match else 'Unnamed'
        
        # Extract description
        desc_match = re.search(r'<desc>(.*?)</desc>', wpt_content, re.DOTALL)
        description = desc_match.group(1) if desc_match else ''
        
        # Extract symbol
        sym_match = re.search(r'<sym>(.*?)</sym>', wpt_content)
        symbol = sym_match.group(1) if sym_match else 'Waypoint'
        
        # Extract type
        type_match = re.search(r'<type>(.*?)</type>', wpt_content)
        amenity_type = type_match.group(1) if type_match else 'Amenity'
        
        waypoints.append({
            'lat': lat,
            'lon': lon,
            'name': name,
            'description': description,
            'symbol': symbol,
            'type': amenity_type
        })
    
    return track_points, waypoints

def get_amenity_icon_color(symbol, amenity_type=None):
    """Return appropriate icon and color for different amenity types"""
    
    # First check by specific type for more granular icons
    if amenity_type:
        type_map = {
            'Cafe': ('star', 'orange'),  # Using 'star' icon which is definitely supported
            'Restaurant': ('cutlery', 'red'),
            'Pub/Bar': ('glass', 'darkred'),
            'Fast Food': ('cutlery', 'pink'),
            'Toilets': ('male', 'blue'),  # Font Awesome toilet icon alternatives: 'male', 'female', 'transgender'
            'Water Source': ('tint', 'lightblue'),
            'Fuel Station': ('car', 'orange'),
            'Bike Shop': ('bicycle', 'green'),
        }
        if amenity_type in type_map:
            return type_map[amenity_type]
    
    # Fallback to symbol-based mapping
    icon_map = {
        'Restaurant': ('cutlery', 'red'),
        'Restroom': ('male', 'blue'),  # Updated from 'home' to 'male' for toilets
        'Water Source': ('tint', 'lightblue'),
        'Gas Station': ('car', 'orange'),
        'Bike Trail': ('bicycle', 'green'),
        'Waypoint': ('info-sign', 'gray')
    }
    return icon_map.get(symbol, ('info-sign', 'gray'))

def create_folium_map(gpx_file, output_file):
    """Create an interactive Folium map from GPX data using regex parsing"""
    
    print(f"Reading GPX file: {gpx_file}")
    
    # Read GPX file as text
    with open(gpx_file, 'r', encoding='utf-8') as f:
        gpx_content = f.read()
    
    # Extract data using regex
    track_points, waypoints = extract_gpx_data_with_regex(gpx_content)
    
    print(f"Found {len(track_points)} track points and {len(waypoints)} waypoints")
    
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
    
    # Create feature groups for different amenity types
    amenity_groups = {}
    
    for waypoint in waypoints:
        lat, lon = waypoint['lat'], waypoint['lon']
        name = waypoint['name']
        description = waypoint['description']
        symbol = waypoint['symbol']
        amenity_type = waypoint['type']
        
        # Get appropriate icon and color
        icon_name, color = get_amenity_icon_color(symbol, amenity_type)
        
        # Clean up description for display
        clean_desc = description.replace('&amp;', '&')
        
        # Extract website URL if present and make it clickable
        website_url = None
        display_desc = clean_desc
        
        if 'Website:' in clean_desc:
            parts = clean_desc.split('Website:', 1)
            if len(parts) == 2:
                website_url = parts[1].strip()
                display_desc = parts[0].rstrip('. ')
                
        # Create popup content with clickable website link
        popup_content = f"""
        <div style="min-width: 200px;">
        <b style="color: #2E4057; font-size: 14px;">{name}</b><br>
        <span style="color: #666; font-size: 12px;">Type: {amenity_type}</span><br>
        <span style="font-size: 11px;">{display_desc}</span>
        """
        
        if website_url:
            popup_content += f'''<br><br>
            <a href="{website_url}" target="_blank" rel="noopener noreferrer" 
               style="color: #1976D2; text-decoration: none; font-weight: bold; font-size: 12px;">
               🌐 Visit Website
            </a>'''
        
        popup_content += "</div>"
        
        # Create marker
        marker = folium.Marker(
            [lat, lon],
            popup=folium.Popup(popup_content, max_width=300),
            tooltip=f"{name} ({amenity_type})",
            icon=folium.Icon(color=color, icon=icon_name)
        )
        
        # Group markers by type for layer control
        if amenity_type not in amenity_groups:
            amenity_groups[amenity_type] = folium.FeatureGroup(name=amenity_type)
            amenity_groups[amenity_type].add_to(m)
        
        marker.add_to(amenity_groups[amenity_type])
    
    # Add layer control to toggle amenity types
    folium.LayerControl().add_to(m)
    
    # Add fullscreen button
    plugins.Fullscreen().add_to(m)
    
    # Save map
    m.save(output_file)
    print(f"Interactive map saved to: {output_file}")
    print(f"Open in browser: file://{os.path.abspath(output_file)}")
    
    # Print statistics
    print(f"\nMap Statistics:")
    print(f"- Route points: {len(track_points)}")
    print(f"- Waypoints: {len(waypoints)}")
    print(f"- Amenity types: {len(amenity_groups)}")
    for amenity_type in amenity_groups.keys():
        count = len([wp for wp in waypoints if wp['type'] == amenity_type])
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