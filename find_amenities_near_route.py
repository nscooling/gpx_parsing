#!/usr/bin/env python3
import gpxpy, gpxpy.gpx
import overpy
import math
import argparse

# --- Parameters ---
DISTANCE_STEP = 1000  # meters between sample points (increased to reduce API load)
SEARCH_RADIUS = 300  # meters (reduced to reduce API load)
AMENITY_FILTER = r"^(cafe|restaurant|pub|bar|fast_food|toilets|drinking_water|fuel)$"

# --- CLI argument parsing ---
def parse_args():
    parser = argparse.ArgumentParser(description="Find amenities near a GPX route")
    parser.add_argument("input_file", help="Input GPX file path")
    parser.add_argument("-o", "--output", default=None, 
                       help="Output GPX file path (default: input filename with '_amenities' appended)")
    parser.add_argument("-d", "--distance-step", type=int, default=1000,
                       help="Distance between sample points in meters (default: 1000)")
    parser.add_argument("-r", "--search-radius", type=int, default=300,
                       help="Search radius around each point in meters (default: 300)")
    args = parser.parse_args()
    
    # Set default output filename if not provided
    if args.output is None:
        import os
        base_name = os.path.splitext(args.input_file)[0]
        args.output = f"{base_name}_amenities.gpx"
    
    return args

args = parse_args()

# --- Parameters ---
DISTANCE_STEP = args.distance_step  # meters between sample points
SEARCH_RADIUS = args.search_radius  # meters
AMENITY_FILTER = r"^(cafe|restaurant|pub|bar|fast_food|toilets|drinking_water|fuel)$"

# --- Helper: haversine distance (m) ---
def haversine(lat1, lon1, lat2, lon2):
    R = 6371000
    dlat, dlon = math.radians(lat2-lat1), math.radians(lon2-lon1)
    a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1))*math.cos(math.radians(lat2))*math.sin(dlon/2)**2
    return 2 * R * math.atan2(math.sqrt(a), math.sqrt(1-a))

# --- Step 1: Load GPX and sample points every ≥500 m ---
with open(args.input_file) as f:
    gpx = gpxpy.parse(f)

points = []
dist_since_last = 0
last_pt = None

for trk in gpx.tracks:
    for seg in trk.segments:
        for p in seg.points:
            if last_pt is None or haversine(last_pt.latitude, last_pt.longitude, p.latitude, p.longitude) >= DISTANCE_STEP:
                points.append(p)
                last_pt = p

print(f"Sampled {len(points)} points along track")

# --- Step 2: Query Overpass ---
api = overpy.Overpass()
query_parts = []
for p in points:
    lat, lon = p.latitude, p.longitude
    query_parts.append(f"""
      node["amenity"~"{AMENITY_FILTER}"](around:{SEARCH_RADIUS},{lat},{lon});
      way ["amenity"~"{AMENITY_FILTER}"](around:{SEARCH_RADIUS},{lat},{lon});
      node["shop"="bicycle"](around:{SEARCH_RADIUS},{lat},{lon});
    """)

query = f"[out:json][timeout:90];(\n{''.join(query_parts)});\nout center meta;"
print("Querying Overpass…")
result = api.query(query)
print(f"Found {len(result.nodes)} node amenities, {len(result.ways)} ways")

# --- Step 3: Calculate route points and cumulative distances ---
route_points = []
cumulative_distances = [0]  # Distance from start to each point along route

for trk in gpx.tracks:
    for seg in trk.segments:
        for p in seg.points:
            route_points.append((p.latitude, p.longitude))
            if len(route_points) > 1:
                # Calculate distance from previous point
                prev_lat, prev_lon = route_points[-2]
                curr_lat, curr_lon = route_points[-1]
                dist = haversine(float(prev_lat), float(prev_lon), float(curr_lat), float(curr_lon))
                cumulative_distances.append(cumulative_distances[-1] + dist)

total_route_distance = cumulative_distances[-1] if cumulative_distances else 0
print(f"Total route distance: {total_route_distance/1000:.1f} km")

def calculate_distances(amenity_lat, amenity_lon):
    """Calculate distances from amenity to route start, end, and closest point on route"""
    if not route_points:
        return 0, 0, 0
    
    amenity_lat, amenity_lon = float(amenity_lat), float(amenity_lon)
    
    # Find closest point on route and its index
    min_dist_to_route = float('inf')
    closest_index = 0
    
    for i, (lat, lon) in enumerate(route_points):
        dist = haversine(float(lat), float(lon), amenity_lat, amenity_lon)
        if dist < min_dist_to_route:
            min_dist_to_route = dist
            closest_index = i
    
    # Distance along route to closest point (in km)
    dist_from_start = cumulative_distances[closest_index] / 1000
    # Remaining distance along route (in km)  
    dist_to_end = (total_route_distance - cumulative_distances[closest_index]) / 1000
    
    return dist_from_start, dist_to_end, min_dist_to_route

# --- Step 4: Deduplicate & add waypoints ---
seen = set()
new_gpx = gpxpy.gpx.GPX()
for trk in gpx.tracks:
    new_gpx.tracks.append(trk)

def add_wp(lat, lon, name, desc, amenity_type=None, tags=None):
    # Calculate route distances
    dist_start, dist_end, dist_route = calculate_distances(lat, lon)
    
    # Format description without "amenity=" prefix and add distance info
    clean_desc = desc.replace("amenity=", "").replace("shop=", "")
    distance_info = f"Route km: {dist_start:.1f}, Remaining: {dist_end:.1f}km, Off route: {dist_route:.0f}m"
    
    # Check for website links in tags
    website = None
    if tags:
        website = tags.get("website") or tags.get("contact:website") or tags.get("url")
    
    # Build full description
    if website:
        full_desc = f"{clean_desc}. {distance_info}. Website: {website}" if clean_desc else f"{distance_info}. Website: {website}"
    else:
        full_desc = f"{clean_desc}. {distance_info}" if clean_desc else distance_info
    
    wpt = gpxpy.gpx.GPXWaypoint(latitude=lat, longitude=lon, name=name, description=full_desc)
    
    # Add link element if website exists
    if website:
        # Create a link element (GPX supports this)
        wpt.link = website
        wpt.link_text = name or "Website"
    
    # Set symbol and type based on amenity
    if amenity_type:
        if amenity_type in ['cafe', 'restaurant', 'pub', 'bar', 'fast_food']:
            wpt.symbol = 'Restaurant'
            wpt.type = 'Food & Drink'
        elif amenity_type == 'toilets':
            wpt.symbol = 'Restroom'
            wpt.type = 'Facilities'
        elif amenity_type == 'drinking_water':
            wpt.symbol = 'Water Source'
            wpt.type = 'Facilities'
        elif amenity_type == 'fuel':
            wpt.symbol = 'Gas Station'
            wpt.type = 'Transportation'
        elif amenity_type == 'bicycle':  # shop=bicycle
            wpt.symbol = 'Bike Trail'
            wpt.type = 'Transportation'
        else:
            wpt.symbol = 'Waypoint'
            wpt.type = 'Amenity'
    else:
        wpt.symbol = 'Waypoint'
        wpt.type = 'Amenity'
    
    new_gpx.waypoints.append(wpt)

print("Processing amenities...")
processed_count = 0
for n in result.nodes:
    if n.id in seen: continue
    seen.add(n.id)
    desc = ", ".join(f"{k}={v}" for k, v in n.tags.items() if k in ("amenity", "shop"))
    amenity_type = n.tags.get("amenity") or n.tags.get("shop")
    add_wp(n.lat, n.lon, n.tags.get("name", "Amenity"), desc, amenity_type, n.tags)
    
    processed_count += 1
    if processed_count % 50 == 0:
        print(".", end="", flush=True)

for w in result.ways:
    if w.id in seen: continue
    seen.add(w.id)
    # Calculate center of way by averaging node coordinates
    try:
        if w.nodes:
            center_lat = sum(node.lat for node in w.nodes) / len(w.nodes)
            center_lon = sum(node.lon for node in w.nodes) / len(w.nodes)
            desc = ", ".join(f"{k}={v}" for k, v in w.tags.items() if k in ("amenity", "shop"))
            amenity_type = w.tags.get("amenity") or w.tags.get("shop")
            add_wp(center_lat, center_lon, w.tags.get("name", "Amenity"), desc, amenity_type, w.tags)
            
            processed_count += 1
            if processed_count % 50 == 0:
                print(".", end="", flush=True)
    except overpy.exception.DataIncomplete:
        # Skip ways where node data is incomplete
        continue

if processed_count % 50 != 0:
    print()  # New line after progress dots

# --- Step 4: Save new GPX ---
with open(args.output, "w") as f:
    f.write(new_gpx.to_xml())

print(f"Saved enriched GPX → {args.output}")
