"""GPX file parser — extracts trackpoints and computes course geometry."""
from __future__ import annotations

import math
import xml.etree.ElementTree as ET
from typing import Any


_GPX_NS = {
    "gpx10": "http://www.topografix.com/GPX/1/0",
    "gpx11": "http://www.topografix.com/GPX/1/1",
}


def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in metres."""
    R = 6_371_000.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


def _bearing_deg(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Forward azimuth from point 1 to point 2, 0–360°."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dlam = math.radians(lon2 - lon1)
    x = math.sin(dlam) * math.cos(phi2)
    y = math.cos(phi1) * math.sin(phi2) - math.sin(phi1) * math.cos(phi2) * math.cos(dlam)
    return (math.degrees(math.atan2(x, y)) + 360) % 360


def parse_gpx(gpx_bytes: bytes) -> list[dict[str, Any]]:
    """Parse raw GPX bytes → list of {lat, lon, elevation_m, dist_m, cum_dist_m, bearing_deg}."""
    try:
        root = ET.fromstring(gpx_bytes)
    except ET.ParseError as exc:
        raise ValueError(f"Invalid GPX file: {exc}") from exc

    # Detect namespace from root tag: "{http://...}gpx" or "gpx"
    tag = root.tag
    ns_uri = tag[1: tag.index("}")] if tag.startswith("{") else ""

    def _q(local: str) -> str:
        """Qualified tag name."""
        return f"{{{ns_uri}}}{local}" if ns_uri else local

    # Collect raw trackpoints
    raw: list[tuple[float, float, float]] = []
    for trkpt in root.iter(_q("trkpt")):
        try:
            lat = float(trkpt.get("lat", 0))
            lon = float(trkpt.get("lon", 0))
            ele_el = trkpt.find(_q("ele"))
            elev = float(ele_el.text) if ele_el is not None and ele_el.text else 0.0
            raw.append((lat, lon, elev))
        except (TypeError, ValueError):
            continue

    # Fall back to waypoints / route points if no track
    if not raw:
        for local in ("wpt", "rtept"):
            for pt in root.iter(_q(local)):
                try:
                    lat = float(pt.get("lat", 0))
                    lon = float(pt.get("lon", 0))
                    ele_el = pt.find(_q("ele"))
                    elev = float(ele_el.text) if ele_el is not None and ele_el.text else 0.0
                    raw.append((lat, lon, elev))
                except (TypeError, ValueError):
                    continue

    if len(raw) < 2:
        raise ValueError("GPX file must contain at least 2 trackpoints.")

    # Build segment list with cumulative distance and bearing
    points: list[dict[str, Any]] = []
    cum_dist = 0.0
    for i, (lat, lon, elev) in enumerate(raw):
        if i == 0:
            dist = 0.0
            bearing = _bearing_deg(lat, lon, raw[1][0], raw[1][1]) if len(raw) > 1 else 0.0
        else:
            prev = raw[i - 1]
            dist = _haversine_m(prev[0], prev[1], lat, lon)
            cum_dist += dist
            bearing = _bearing_deg(prev[0], prev[1], lat, lon)
        points.append({
            "lat": lat,
            "lon": lon,
            "elevation_m": elev,
            "dist_m": dist,
            "cum_dist_m": cum_dist,
            "bearing_deg": bearing,
        })
    return points


def sample_course(points: list[dict], interval_m: float = 300.0) -> list[dict[str, Any]]:
    """Resample course to evenly-spaced segments of ~interval_m metres.

    Returns one dict per sample: lat, lon, elevation_m, cum_dist_m, bearing_deg,
    elev_gain_m (gain from previous sample), aspect_class ('north'|'south'|'east'|'west').
    """
    if not points:
        return []

    total_dist = points[-1]["cum_dist_m"]
    if total_dist < interval_m:
        # Very short course — just return endpoints
        return [_enrich(points[0]), _enrich(points[-1])]

    samples: list[dict] = []
    target = 0.0
    idx = 0
    while target <= total_dist + 1.0:
        # Find the two raw points bracketing this distance
        while idx < len(points) - 1 and points[idx + 1]["cum_dist_m"] < target:
            idx += 1
        p0 = points[idx]
        if idx + 1 < len(points):
            p1 = points[idx + 1]
            seg_len = p1["cum_dist_m"] - p0["cum_dist_m"]
            frac = (target - p0["cum_dist_m"]) / seg_len if seg_len > 0 else 0.0
            interp = {
                "lat": p0["lat"] + frac * (p1["lat"] - p0["lat"]),
                "lon": p0["lon"] + frac * (p1["lon"] - p0["lon"]),
                "elevation_m": p0["elevation_m"] + frac * (p1["elevation_m"] - p0["elevation_m"]),
                "cum_dist_m": target,
                "bearing_deg": p1["bearing_deg"],
            }
        else:
            interp = {**p0, "cum_dist_m": target}
        samples.append(_enrich(interp))
        target += interval_m

    # Compute elevation gain between samples
    for i, s in enumerate(samples):
        if i == 0:
            s["elev_gain_m"] = 0.0
        else:
            s["elev_gain_m"] = s["elevation_m"] - samples[i - 1]["elevation_m"]

    return samples


def _enrich(p: dict) -> dict:
    """Add aspect_class from bearing."""
    b = p.get("bearing_deg", 0.0)
    if 315 <= b or b < 45:
        aspect = "north"
    elif 45 <= b < 135:
        aspect = "east"
    elif 135 <= b < 225:
        aspect = "south"
    else:
        aspect = "west"
    return {**p, "aspect_class": aspect, "elev_gain_m": 0.0}


def course_stats(samples: list[dict]) -> dict[str, Any]:
    """Summarise course: total distance, elevation gain/loss, min/max elevation."""
    if not samples:
        return {}
    elevs = [s["elevation_m"] for s in samples]
    gains = [s["elev_gain_m"] for s in samples if s["elev_gain_m"] > 0]
    losses = [abs(s["elev_gain_m"]) for s in samples if s["elev_gain_m"] < 0]
    return {
        "total_dist_km": round(samples[-1]["cum_dist_m"] / 1000, 2),
        "elev_min_m": round(min(elevs), 1),
        "elev_max_m": round(max(elevs), 1),
        "elev_gain_m": round(sum(gains), 1),
        "elev_loss_m": round(sum(losses), 1),
        "num_samples": len(samples),
    }
