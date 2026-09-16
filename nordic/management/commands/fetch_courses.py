"""Management command: fetch Nordic ski course GPX files from OpenStreetMap.

Usage:
    python manage.py fetch_courses
    python manage.py fetch_courses --venue Falun
    python manage.py fetch_courses --force   # re-fetch even if GPX exists
"""
from __future__ import annotations

import math
import time
import urllib.parse
from pathlib import Path

import requests
from django.core.management.base import BaseCommand

from nordic.engine import VENUES

COURSES_DIR = Path(__file__).resolve().parent.parent.parent / "courses"

# Overpass query radius in metres per venue
_RADIUS = 6000

# Target path length: try to build a route this long (metres)
_TARGET_LEN_M = 12_000


_OVERPASS_MIRRORS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
]


def _get(url: str, **kwargs) -> requests.Response:
    """GET with retries across multiple Overpass mirrors."""
    # Detect if this is an Overpass URL so we can try mirrors
    is_overpass = any(m.split("/api/")[0] in url for m in _OVERPASS_MIRRORS)
    query_str = url.split("?data=", 1)[1] if "?data=" in url else None

    mirrors = _OVERPASS_MIRRORS if (is_overpass and query_str) else [None]
    for mirror in mirrors:
        try_url = (mirror + "?data=" + query_str) if mirror and query_str else url
        for attempt in range(2):
            try:
                r = requests.get(try_url, timeout=45, headers={"User-Agent": "GlideCast/1.0"}, **kwargs)
                if r.status_code == 429:
                    time.sleep(10)
                    continue
                if r.status_code in (502, 504):
                    break  # try next mirror
                r.raise_for_status()
                return r
            except requests.exceptions.Timeout:
                break  # try next mirror
            except requests.exceptions.ConnectionError:
                time.sleep(3)
    raise RuntimeError(f"All Overpass mirrors failed for query")


def fetch_osm_ways(lat: float, lon: float, radius: int = _RADIUS) -> dict:
    q = (
        f"[out:json][timeout:35];"
        f"(way[\"piste:type\"=\"nordic\"](around:{radius},{lat},{lon});"
        f"relation[\"piste:type\"=\"nordic\"](around:{radius},{lat},{lon}););"
        f"out body;>;out skel qt;"
    )
    url = "https://overpass-api.de/api/interpreter?data=" + urllib.parse.quote(q)
    r = _get(url)
    return r.json()


def build_node_index(data: dict) -> dict[int, dict]:
    """Map node_id → {lat, lon, ele}."""
    return {
        e["id"]: {"lat": e["lat"], "lon": e["lon"], "ele": e.get("tags", {}).get("ele")}
        for e in data["elements"]
        if e["type"] == "node"
    }


def extract_ways(data: dict) -> list[list[int]]:
    """List of ways, each a list of node IDs."""
    return [e["nodes"] for e in data["elements"] if e["type"] == "way" and "nodes" in e]


def _dist_m(a: dict, b: dict) -> float:
    R = 6_371_000.0
    phi1, phi2 = math.radians(a["lat"]), math.radians(b["lat"])
    dphi = math.radians(b["lat"] - a["lat"])
    dlam = math.radians(b["lon"] - a["lon"])
    x = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
    return 2 * R * math.asin(math.sqrt(max(0, x)))


def build_route(ways: list[list[int]], nodes: dict[int, dict], target_m: float = _TARGET_LEN_M) -> list[int]:
    """Greedily chain ways into a single connected route up to target_m length.

    Strategy:
    1. Start from the way that has the most elevation variation (interesting profile).
    2. At each step, pick the adjacent way whose endpoint is closest to our current tail.
    3. Stop when we exceed target_m.
    """
    if not ways:
        return []

    # Score ways by elevation range (prefer ones with relief)
    def _elev_range(way: list[int]) -> float:
        eles = [float(nodes[n]["ele"]) for n in way if n in nodes and nodes[n]["ele"] is not None]
        return max(eles) - min(eles) if len(eles) >= 2 else 0.0

    valid_ways = [w for w in ways if all(n in nodes for n in w) and len(w) >= 2]
    if not valid_ways:
        valid_ways = [w for w in ways if any(n in nodes for n in w)]

    # Start with the way with most elevation variation
    scored = sorted(valid_ways, key=_elev_range, reverse=True)
    current_way = scored[0]
    route: list[int] = list(current_way)
    used = {id(current_way)}
    total_dist = sum(
        _dist_m(nodes[route[i]], nodes[route[i + 1]])
        for i in range(len(route) - 1)
        if route[i] in nodes and route[i + 1] in nodes
    )

    # Build lookup: endpoint_node_id → list of ways containing that node
    endpoint_map: dict[int, list[list[int]]] = {}
    for w in valid_ways:
        for endpoint in (w[0], w[-1]):
            endpoint_map.setdefault(endpoint, []).append(w)

    for _ in range(500):
        if total_dist >= target_m:
            break
        tail = route[-1]
        if tail not in nodes:
            break

        # Candidate: unused ways that share the tail node as endpoint, OR
        # unused ways whose start/end is within 50m of tail
        candidates = [
            w for w in endpoint_map.get(tail, [])
            if id(w) not in used
        ]

        if not candidates:
            # Try nearest endpoint within 80m
            tail_node = nodes[tail]
            best_w, best_d = None, 80.0
            for w in valid_ways:
                if id(w) in used:
                    continue
                for ep in (w[0], w[-1]):
                    if ep in nodes:
                        d = _dist_m(tail_node, nodes[ep])
                        if d < best_d:
                            best_d, best_w = d, w
            if best_w is None:
                break
            candidates = [best_w]

        # Among candidates, pick the one with most elevation variation
        best = max(candidates, key=_elev_range)
        used.add(id(best))
        segment = list(best) if best[0] == tail else list(reversed(best))
        # Skip the first node if it duplicates the tail
        if segment and segment[0] == tail:
            segment = segment[1:]
        for i in range(len(segment) - 1):
            if segment[i] in nodes and segment[i + 1] in nodes:
                total_dist += _dist_m(nodes[segment[i]], nodes[segment[i + 1]])
        route.extend(segment)

    return route


def fill_elevation_openelev(node_ids: list[int], nodes: dict[int, dict]) -> None:
    """Fill missing elevation using Open-Elevation API (free, no key)."""
    missing = [nid for nid in node_ids if nodes.get(nid) and nodes[nid]["ele"] is None]
    if not missing:
        return

    # Batch in groups of 100
    for i in range(0, len(missing), 100):
        batch = missing[i: i + 100]
        locations = [{"latitude": nodes[n]["lat"], "longitude": nodes[n]["lon"]} for n in batch]
        try:
            r = requests.post(
                "https://api.open-elevation.com/api/v1/lookup",
                json={"locations": locations},
                timeout=20,
                headers={"User-Agent": "GlideCast/1.0"},
            )
            if r.status_code == 200:
                results = r.json().get("results", [])
                for nid, res in zip(batch, results):
                    nodes[nid]["ele"] = res.get("elevation", 0)
        except Exception:
            # Fall back to 0 elevation — profile will be flat but won't crash
            for nid in batch:
                nodes[nid]["ele"] = 0
        time.sleep(0.5)


def route_to_gpx(route: list[int], nodes: dict[int, dict], venue_name: str) -> str:
    """Serialise a node-ID route to GPX XML."""
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<gpx version="1.1" xmlns="http://www.topografix.com/GPX/1/1" creator="GlideCast">',
        f'  <trk><name>{venue_name}</name><trkseg>',
    ]
    for nid in route:
        n = nodes.get(nid)
        if n is None:
            continue
        ele = n["ele"] if n["ele"] is not None else 0
        lines.append(f'    <trkpt lat="{n["lat"]}" lon="{n["lon"]}"><ele>{ele}</ele></trkpt>')
    lines += ["  </trkseg></trk>", "</gpx>"]
    return "\n".join(lines)


def slug(name: str) -> str:
    return name.lower().replace("/", "_").replace(" ", "_").replace("ø", "o").replace("ä", "a").replace("ö", "o").replace("ü", "u").replace("å", "a")


class Command(BaseCommand):
    help = "Fetch Nordic ski course GPX files from OpenStreetMap for all venues."

    def add_arguments(self, parser):
        parser.add_argument("--venue", type=str, default=None, help="Only fetch this venue.")
        parser.add_argument("--force", action="store_true", help="Re-fetch even if GPX already exists.")

    def handle(self, *args, **options):
        COURSES_DIR.mkdir(parents=True, exist_ok=True)
        target_venue = options.get("venue")
        force = options.get("force", False)

        venues_to_fetch = {
            k: v for k, v in VENUES.items()
            if target_venue is None or k == target_venue
        }

        for venue_name, venue in venues_to_fetch.items():
            out_path = COURSES_DIR / f"{slug(venue_name)}.gpx"
            if out_path.exists() and not force:
                self.stdout.write(f"  skip  {venue_name} (already exists)")
                continue

            self.stdout.write(f"  fetch {venue_name} …", ending="")
            self.stdout.flush()

            try:
                lat, lon = venue["lat"], venue["lon"]
                data = fetch_osm_ways(lat, lon)
                nodes = build_node_index(data)
                ways = extract_ways(data)

                if not ways or not nodes:
                    self.stdout.write(self.style.WARNING(f" no OSM data"))
                    time.sleep(2)
                    continue

                route = build_route(ways, nodes)
                if len(route) < 4:
                    self.stdout.write(self.style.WARNING(f" route too short ({len(route)} nodes)"))
                    time.sleep(2)
                    continue

                # Fill missing elevation
                fill_elevation_openelev(route, nodes)

                gpx_xml = route_to_gpx(route, nodes, venue_name)
                out_path.write_text(gpx_xml, encoding="utf-8")

                # Quick stats
                km = sum(
                    _dist_m(nodes[route[i]], nodes[route[i + 1]])
                    for i in range(len(route) - 1)
                    if route[i] in nodes and route[i + 1] in nodes
                ) / 1000
                self.stdout.write(self.style.SUCCESS(f" {len(route)} nodes, {km:.1f} km → {out_path.name}"))

            except Exception as exc:
                self.stdout.write(self.style.ERROR(f" ERROR: {exc}"))

            time.sleep(3)  # be polite to Overpass

        self.stdout.write("Done.")
