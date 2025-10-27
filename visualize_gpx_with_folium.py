#!/usr/bin/env python3
import gpxpy
import folium
import argparse
import os
from folium import plugins

def parse_args():
    parser = argparse.ArgumentParser(description="Visualize GPX route with amenities using Folium")
    parser.add_argument("gpx_file", help="GPX file with route and amenities")
    parser.add_argument("-o", "--output", default=None,
                       help="Output HTML file (default: input filename with '.html' extension)")
    return parser.parse_args()

def get_amenity_icon_color(amenity_type, symbol):
    """Return appropriate icon and color for different amenity types"""
    
    # First check by specific type for more granular icons
    if amenity_type:
        type_map = {
            'Cafe': ('coffee', 'orange'),
            'Restaurant': ('cutlery', 'red'),
            'Pub/Bar': ('glass', 'darkred'),
            'Fast Food': ('cutlery', 'pink'),
            'Toilets': ('male', 'blue'),  # or could use 'female' or 'transgender'
            'Water Source': ('tint', 'lightblue'),
            'Fuel Station': ('car', 'orange'),
            'Bike Shop': ('bicycle', 'green'),
        }
        if amenity_type in type_map:
            return type_map[amenity_type]
    
    # Fallback to symbol-based mapping
    icon_map = {
        'Restaurant': ('cutlery', 'red'),
        'Restroom': ('male', 'blue'),  # Updated from 'home' to 'male'
        'Water Source': ('tint', 'lightblue'),
        'Gas Station': ('car', 'orange'),
        'Bike Trail': ('bicycle', 'green'),
        'Waypoint': ('info-sign', 'gray')
    }
    return icon_map.get(symbol, ('info-sign', 'gray'))

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
    
    for waypoint in gpx.waypoints:
        lat, lon = waypoint.latitude, waypoint.longitude
        name = waypoint.name or 'Unnamed'
        description = waypoint.description or ''
        symbol = waypoint.symbol or 'Waypoint'
        amenity_type = waypoint.type or 'Amenity'
        
        # Get appropriate icon and color
        icon_name, color = get_amenity_icon_color(amenity_type, symbol)
        
        # Create popup content with description
        popup_content = f"""
        <b>{name}</b><br>
        Type: {amenity_type}<br>
        {description.replace('. Website:', '<br>Website:')}
        """
        
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
    
    # Add a marker cluster for better performance with many markers
    if len(gpx.waypoints) > 50:
        marker_cluster = plugins.MarkerCluster().add_to(m)
        
        for waypoint in gpx.waypoints:
            lat, lon = waypoint.latitude, waypoint.longitude
            name = waypoint.name or 'Unnamed'
            description = waypoint.description or ''
            symbol = waypoint.symbol or 'Waypoint'
            amenity_type = waypoint.type or 'Amenity'
            
            icon_name, color = get_amenity_icon_color(amenity_type, symbol)
            
            popup_content = f"""
            <b>{name}</b><br>
            Type: {amenity_type}<br>
            {description.replace('. Website:', '<br>Website:')}
            """
            
            folium.Marker(
                [lat, lon],
                popup=folium.Popup(popup_content, max_width=300),
                tooltip=f"{name} ({amenity_type})",
                icon=folium.Icon(color=color, icon=icon_name)
            ).add_to(marker_cluster)
    
    # Add fullscreen button
    plugins.Fullscreen().add_to(m)
    
    # Add measure control
    plugins.MeasureControl().add_to(m)
    
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