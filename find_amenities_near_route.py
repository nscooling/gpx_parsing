#!/usr/bin/env python3
import gpxpy, gpxpy.gpx
import overpy
import math
import argparse
import xml.sax.saxutils
from urllib.parse import urlsplit, urlunsplit, quote, unquote
import time
import random
import os
import json
import hashlib
from types import SimpleNamespace

# --- Parameters ---
DISTANCE_STEP = 500  # meters between sample points (increased to reduce API load)
SEARCH_RADIUS = 300  # meters (reduced to reduce API load)
AMENITY_FILTER = r"^(cafe|restaurant|pub|bar|fast_food|toilets|drinking_water|fuel)$"

# --- Helper: XML escaping function ---
def escape_xml(text):
    """Properly escape XML content"""
    if text is None:
        return ""
    return xml.sax.saxutils.escape(str(text), {'"': '&quot;', "'": '&apos;'})

# --- Helper: sanitize URLs for XML attribute usage ---
def sanitize_url(url: str) -> str:
    """Return a safely escaped URL suitable for XML attribute values.
    - Strips whitespace
    - Ensures scheme (defaults to https)
    - Percent-encodes unsafe characters in path/query/fragment while keeping reserved ones
    - Leaves XML escaping to the serializer (attribute context), but avoids stray control chars
    """
    if not url:
        return url
    s = url.strip()
    # Unescape common HTML/XML entities that may be in OSM tags
    s = s.replace('&amp;', '&').replace('&quot;', '"').replace('&apos;', "'")
    parts = urlsplit(s if '://' in s else f'https://{s}')
    # Safe set keeps RFC3986 reserved chars unescaped
    safe_set = "/:@%?&=#[]!$'()*+,;"  # do not escape these
    path = quote(unquote(parts.path), safe=safe_set)
    query = quote(unquote(parts.query), safe=safe_set)
    fragment = quote(unquote(parts.fragment), safe=safe_set)
    netloc = parts.netloc
    scheme = parts.scheme or 'https'
    return urlunsplit((scheme, netloc, path, query, fragment))

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
    # Overpass settings
    parser.add_argument("--overpass-timeout", type=int, default=120,
                       help="Overpass server timeout in seconds (default: 120)")
    parser.add_argument("--batch-size", type=int, default=20,
                       help="Number of sample points per Overpass request (default: 20)")
    parser.add_argument("--retries", type=int, default=4,
                       help="Number of retries per batch on transient Overpass errors (default: 4)")
    parser.add_argument("--retry-backoff", type=float, default=2.0,
                       help="Initial backoff in seconds for retries (exponential with jitter) (default: 2.0)")
    parser.add_argument("--batch-sleep", type=float, default=0.5,
                       help="Seconds to sleep between successful batches to reduce server load (default: 0.5)")
    parser.add_argument("--endpoint", type=str, default=None,
                       help="Custom Overpass API endpoint URL (e.g., https://overpass-api.de/api/interpreter)")
    # Caching settings
    parser.add_argument("--cache-dir", type=str, default=".cache",
                       help="Directory to store Overpass cache files (default: .cache)")
    parser.add_argument("--cache-ttl", type=int, default=24*3600,
                       help="Cache time-to-live in seconds (default: 86400 = 24h)")
    parser.add_argument("--no-cache", action="store_true",
                       help="Disable local caching of Overpass results")
    # Query scope
    parser.add_argument("--nodes-only", action="store_true",
                       help="Query only node amenities and skip ways to reduce load")
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

# --- Step 2: Query Overpass with caching, batching & retries ---
def ensure_dir(path: str):
    os.makedirs(path, exist_ok=True)

def build_cache_key(points_list):
    # Stable digest of sampled points and parameters impacting query outputs
    pts_digest_src = ";".join(f"{p.latitude:.6f},{p.longitude:.6f}" for p in points_list)
    pts_digest = hashlib.sha256(pts_digest_src.encode("utf-8")).hexdigest()
    # Use input file identity to avoid cross-file collisions
    try:
        st = os.stat(args.input_file)
        file_sig = f"{os.path.abspath(args.input_file)}|{int(st.st_mtime)}|{st.st_size}"
    except Exception:
        file_sig = os.path.abspath(args.input_file)
    scope = "nodes" if args.nodes_only else "nodes_ways"
    key = f"v1|{file_sig}|step={args.distance_step}|rad={args.search_radius}|filter={AMENITY_FILTER}|scope={scope}|pts={pts_digest}"
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
    return digest

def cache_paths(digest: str):
    cache_base = os.path.join(args.cache_dir, "overpass")
    ensure_dir(cache_base)
    return os.path.join(cache_base, f"{digest}.json")

def try_load_cache(digest: str):
    if args.no_cache:
        return None
    path = cache_paths(digest)
    if not os.path.exists(path):
        return None
    # TTL check by file mtime
    age = time.time() - os.path.getmtime(path)
    if age > args.cache_ttl:
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        nodes = [SimpleNamespace(id=n["id"], lat=float(n["lat"]), lon=float(n["lon"]), tags=n.get("tags", {})) for n in data.get("nodes", [])]
        ways = [SimpleNamespace(id=w["id"], center_lat=float(w["center_lat"]), center_lon=float(w["center_lon"]), tags=w.get("tags", {}), nodes=[]) for w in data.get("ways", [])]
        print(f"Loaded Overpass cache ({len(nodes)} nodes, {len(ways)} ways)")
        return nodes, ways
    except Exception as e:
        print(f"Cache load failed, will re-query: {e}")
        return None

def save_cache(digest: str, nodes_list, ways_list):
    if args.no_cache:
        return
    path = cache_paths(digest)
    try:
        serial = {
            "created": time.time(),
            "nodes": [
                {"id": n.id, "lat": float(n.lat), "lon": float(n.lon), "tags": getattr(n, "tags", {})}
                for n in nodes_list
            ],
            "ways": [
                {"id": w.id, "center_lat": float(getattr(w, "center_lat", 0.0)), "center_lon": float(getattr(w, "center_lon", 0.0)), "tags": getattr(w, "tags", {})}
                for w in ways_list
            ]
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(serial, f)
        print(f"Saved Overpass cache → {path}")
    except Exception as e:
        print(f"Warning: failed to save cache: {e}")
def build_query_for_points(pts):
    parts = []
    for p in pts:
        lat, lon = p.latitude, p.longitude
        if args.nodes_only:
            parts.append(f"""
              node["amenity"~"{AMENITY_FILTER}"](around:{SEARCH_RADIUS},{lat},{lon});
              node["shop"="bicycle"](around:{SEARCH_RADIUS},{lat},{lon});
            """)
        else:
            parts.append(f"""
              node["amenity"~"{AMENITY_FILTER}"](around:{SEARCH_RADIUS},{lat},{lon});
              way["amenity"~"{AMENITY_FILTER}"](around:{SEARCH_RADIUS},{lat},{lon});
              node["shop"="bicycle"](around:{SEARCH_RADIUS},{lat},{lon});
            """)
    # Use provided timeout
    return f"[out:json][timeout:{args.overpass_timeout}];(\n{''.join(parts)});\nout center meta;"

def run_query_with_retries(api, q, batch_idx, total_batches):
    delay = args.retry_backoff
    for attempt in range(1, args.retries + 2):  # retries + initial try
        try:
            print(f"Batch {batch_idx}/{total_batches}: querying ({'attempt ' + str(attempt) if attempt>1 else 'try'})…")
            return api.query(q)
        except (overpy.exception.OverpassGatewayTimeout,
                overpy.exception.OverpassTooManyRequests,
                overpy.exception.MaxRetriesReached):
            if attempt > args.retries:
                raise
            jitter = random.uniform(0, delay * 0.3)
            sleep_s = delay + jitter
            print(f"  Transient Overpass error, retrying in {sleep_s:.1f}s…")
            time.sleep(sleep_s)
            delay *= 2
        except overpy.exception.OverpassBadRequest as e:
            # Query too big or malformed; no point retrying
            raise e

# Initialize Overpass API
api = overpy.Overpass(url=args.endpoint) if args.endpoint else overpy.Overpass()

cache_digest = build_cache_key(points)
cached = try_load_cache(cache_digest)
if cached is not None:
    result_nodes, result_ways = cached
else:
    final_nodes = {}
    final_ways = {}

    if not points:
        result_nodes = []
        result_ways = []
    else:
        total_batches = max(1, (len(points) + args.batch_size - 1) // args.batch_size)
        print(f"Querying Overpass in {total_batches} batch(es)…")
        for i in range(0, len(points), args.batch_size):
            batch_pts = points[i:i+args.batch_size]
            q = build_query_for_points(batch_pts)
            batch_idx = (i // args.batch_size) + 1
            try:
                batch_res = run_query_with_retries(api, q, batch_idx, total_batches)
            except Exception as e:
                print(f"Batch {batch_idx} failed permanently: {e}")
                continue

            # Aggregate without duplicates
            for n in batch_res.nodes:
                if n.id not in final_nodes:
                    final_nodes[n.id] = n
            if not args.nodes_only:
                for w in batch_res.ways:
                    if w.id not in final_ways:
                        final_ways[w.id] = w

            # Be nice to Overpass between batches
            time.sleep(max(0.0, args.batch_sleep))

        result_nodes = list(final_nodes.values())
        result_ways = [] if args.nodes_only else list(final_ways.values())

    # Save cache on success
    try:
        # Convert Overpass objects to a storable list of primitives
        store_nodes = result_nodes
        store_ways = [] if args.nodes_only else []
        if not args.nodes_only:
            store_ways = []
            for w in result_ways:
                c_lat = getattr(w, 'center_lat', None)
                c_lon = getattr(w, 'center_lon', None)
                if c_lat is None or c_lon is None:
                    # compute simple average if nodes present
                    try:
                        if getattr(w, 'nodes', None):
                            c_lat = sum(node.lat for node in w.nodes) / len(w.nodes)
                            c_lon = sum(node.lon for node in w.nodes) / len(w.nodes)
                    except Exception:
                        pass
                # Wrap into a SimpleNamespace compatible for serialization
                store_ways.append(SimpleNamespace(id=w.id, center_lat=c_lat or 0.0, center_lon=c_lon or 0.0, tags=getattr(w, 'tags', {})))
        save_cache(cache_digest, store_nodes, store_ways)
    except Exception as e:
        print(f"Cache save skipped due to error: {e}")

print(f"Found {len(result_nodes)} node amenities, {len(result_ways)} ways")

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
    
    # Build full description (include website as text as well)
    if website:
        full_desc = f"{clean_desc}. {distance_info}. Website: {website}" if clean_desc else f"{distance_info}. Website: {website}"
    else:
        full_desc = f"{clean_desc}. {distance_info}" if clean_desc else distance_info
    
    # Create waypoint - gpxpy will handle XML escaping for text content
    wpt = gpxpy.gpx.GPXWaypoint(latitude=lat, longitude=lon, name=name, description=full_desc)
    
    # Add link element safely (GPX 1.1: <link href="..."><text>..</text></link>)
    if website:
        safe_url = sanitize_url(website)
        # Pre-escape for XML attribute context because gpxpy doesn't escape attribute values here
        wpt.link = escape_xml(safe_url)
        # Use hostname as link text when possible
        try:
            host = urlsplit(safe_url).netloc or safe_url
        except Exception:
            host = safe_url
        wpt.link_text = host
        wpt.link_type = 'text/html'
    
    # Set symbol and type based on amenity
    if amenity_type:
        if amenity_type == 'cafe':
            wpt.symbol = 'Restaurant'
            wpt.type = 'Cafe'
        elif amenity_type == 'restaurant':
            wpt.symbol = 'Restaurant'
            wpt.type = 'Restaurant'
        elif amenity_type in ['pub', 'bar']:
            wpt.symbol = 'Restaurant'
            wpt.type = 'Pub/Bar'
        elif amenity_type == 'fast_food':
            wpt.symbol = 'Restaurant'
            wpt.type = 'Fast Food'
        elif amenity_type == 'toilets':
            wpt.symbol = 'Restroom'
            wpt.type = 'Toilets'
        elif amenity_type == 'drinking_water':
            wpt.symbol = 'Water Source'
            wpt.type = 'Water Source'
        elif amenity_type == 'fuel':
            wpt.symbol = 'Gas Station'
            wpt.type = 'Fuel Station'
        elif amenity_type == 'bicycle':  # shop=bicycle
            wpt.symbol = 'Bike Trail'
            wpt.type = 'Bike Shop'
        else:
            wpt.symbol = 'Waypoint'
            wpt.type = 'Amenity'
    else:
        wpt.symbol = 'Waypoint'
        wpt.type = 'Amenity'
    
    new_gpx.waypoints.append(wpt)

print("Processing amenities...")
processed_count = 0
for n in result_nodes:
    if n.id in seen: continue
    seen.add(n.id)
    desc = ", ".join(f"{k}={v}" for k, v in n.tags.items() if k in ("amenity", "shop"))
    amenity_type = n.tags.get("amenity") or n.tags.get("shop")
    add_wp(n.lat, n.lon, n.tags.get("name", "Amenity"), desc, amenity_type, n.tags)
    
    processed_count += 1
    if processed_count % 50 == 0:
        print(".", end="", flush=True)

for w in result_ways:
    if w.id in seen: continue
    seen.add(w.id)
    # Calculate center of way by averaging node coordinates
    try:
        if w.nodes:
            # Prefer center coords if provided by Overpass (with out center)
            center_lat = getattr(w, 'center_lat', None)
            center_lon = getattr(w, 'center_lon', None)
            if center_lat is None or center_lon is None:
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
