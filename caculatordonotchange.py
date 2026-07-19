"""
RaceWax Oracle - Django Engine
===============================
All Streamlit references removed. All calculation logic, chart builders,
HTML card renderers, CSS styles, colors, and output functions are preserved
exactly as they were in the original racewax_oracle.py.

HOW TO USE IN DJANGO:
    from racewax_engine import (
        VENUES, ModelParams, OBS_COLUMNS,
        get_hourly_forecast, merge_forecasts, prepare_venue,
        attach_observations, run_summary,
        build_temperature_figure, build_meteorology_figure,
        build_time_series_figure, build_visual_wax_chart,
        render_run_card_html, render_summary_strip_html,
        render_energy_panel_html,
        make_download_csv, error_metrics,
        cache_status_text, CARD_CSS,
    )

    In your Django view:
        upper = get_hourly_forecast(lat, lon)
        lower = get_hourly_forecast(lat2, lon2)
        merged = merge_forecasts(upper, lower)
        model = prepare_venue(merged, venue, start_ft, finish_ft, params, race_date)
        model = attach_observations(model, obs_df)
        run1 = run_summary(model, run1_dt, snow_mode, dirty_abrasive)
        run2 = run_summary(model, run2_dt, snow_mode, dirty_abrasive)

        # Plotly figures — convert to JSON for embedding in template
        import plotly
        chart_json = plotly.io.to_json(build_visual_wax_chart(run1, run2))

        # HTML card blocks — pass directly to template with |safe filter
        run1_card_html = render_run_card_html("Run 1", run1)
        summary_html = render_summary_strip_html(run1, run2, cache_status_text())
"""

from __future__ import annotations

import html
import json
import math
import os
import re
import time
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import pvlib
import requests
from pvlib.location import Location
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


# ---------------------------------------------------------------------------
# Constants & configuration
# ---------------------------------------------------------------------------

USER_AGENT = "RaceWaxOracle/2.0 (educational-use; local launcher)"
HEADERS = {"User-Agent": USER_AGENT, "Accept": "application/geo+json"}
LOCAL_TZ = "America/New_York"
SUPPORT_DIR = Path(os.path.expanduser("~/Library/Application Support/RaceWaxOracleV9"))
FORECAST_CACHE_DIR = SUPPORT_DIR / "forecast_cache"
FORECAST_CACHE_DIR.mkdir(parents=True, exist_ok=True)
LAST_FETCH_META: dict[str, str] = {}

VENUES = {
    "Sugarloaf": {
        "display_name": "Sugarloaf Wax Tool",
        "course_name": "Sugarloaf Cribworks / Narrow Gauge",
        "lat": 45.0310,
        "lon": -70.3140,
        "elev_ft": 2851,
        "aspect_deg": 20.0,
        "slope_deg": 19.0,
        "finish_ft": 2444,
        "starts_ft": {"SL": 3159, "GS": 3575, "SuperG": 3759},
        "points": {
            "Upper NWS point": {"lat": 45.0310, "lon": -70.3140, "elev_ft": 2851},
            "Lower NWS point": {"lat": 45.0541, "lon": -70.3087, "elev_ft": 2172},
        },
    },
    "Sunday River": {
        "display_name": "Sunday River Wax Tool",
        "course_name": "Sunday River Race Venue",
        "lat": 44.48515,
        "lon": -70.8828,
        "elev_ft": 2615,
        "aspect_deg": 10.0,
        "slope_deg": 18.0,
        "finish_ft": 1210,
        "starts_ft": {"SL": 1932, "GS": 2460, "SuperG": 2460},
        "points": {
            "Upper NWS point": {"lat": 44.4720, "lon": -70.8770, "elev_ft": 2615},
            "Lower NWS point": {"lat": 44.4983, "lon": -70.8886, "elev_ft": 1388},
        },
    },
    "Gore Mountain": {
        "display_name": "Gore Mountain Wax Tool",
        "course_name": "Gore Mountain Race Venue",
        "lat": 43.6713,
        "lon": -74.0300,
        "elev_ft": 2667,
        "aspect_deg": 125.0,
        "slope_deg": 14.0,
        "finish_ft": 1509,
        "starts_ft": {"SL": 2326, "GS": 2667, "SuperG": 2667},
        "points": {
            "Upper NWS point": {"lat": 43.6765, "lon": -74.0351, "elev_ft": 3419},
            "Lower NWS point": {"lat": 43.6660, "lon": -74.0250, "elev_ft": 1650},
        },
    },
    "Mount Snow": {
        "display_name": "Mount Snow Wax Tool",
        "course_name": "Mount Snow Race Venue",
        "lat": 42.9600,
        "lon": -72.9200,
        "elev_ft": 3600,
        "aspect_deg": 15.0,
        "slope_deg": 17.0,
        "finish_ft": 1900,
        "starts_ft": {"SL": 2800, "GS": 3300, "SuperG": 3600},
        "points": {
            "Upper NWS point": {"lat": 42.9650, "lon": -72.9150, "elev_ft": 3600},
            "Lower NWS point": {"lat": 42.9550, "lon": -72.9250, "elev_ft": 2000},
        },
    },
    "Killington": {
        "display_name": "Killington Wax Tool",
        "course_name": "Killington Race Venue",
        "lat": 43.6770,
        "lon": -72.7800,
        "elev_ft": 4241,
        "aspect_deg": 22.0,
        "slope_deg": 18.0,
        "finish_ft": 1650,
        "starts_ft": {"SL": 3100, "GS": 3800, "SuperG": 4241},
        "points": {
            "Upper NWS point": {"lat": 43.6820, "lon": -72.7750, "elev_ft": 4241},
            "Lower NWS point": {"lat": 43.6680, "lon": -72.7880, "elev_ft": 1800},
        },
    },
}

OBS_COLUMNS = [
    "time",
    "air_start_measured_f",
    "air_finish_measured_f",
    "snow_start_measured_f",
    "snow_finish_measured_f",
]

HS_PRODUCTS = [
    ("HS5 Turquoise", -18.0, -10.0),
    ("HS6 Blue", -12.0, -6.0),
    ("HS7 Violet", -8.0, -2.0),
    ("HS8 Red", -4.0, 4.0),
    ("HS10 Yellow", 0.0, 10.0),
]

TST_PRODUCTS = [
    ("TS5 Turbo Turquoise", -15.0, -8.0),
    ("TS6 Turbo Blue", -12.0, -4.0),
    ("TS7 Turbo Violet", -7.0, -2.0),
    ("TS8 Turbo Red", -4.0, 4.0),
    ("TS10 Turbo Yellow", 0.0, 10.0),
]

TSP_PRODUCTS = [
    ("TSP5 Turquoise", -15.0, -8.0),
    ("TSP6 Blue", -10.0, -5.0),
    ("TSP7 Violet", -7.0, -2.0),
    ("TSP8 Red", -4.0, 4.0),
    ("TSP10 Yellow", 0.0, 10.0),
]

PRODUCT_COLORS = {
    "Turquoise": "#1bb3c8",
    "Blue": "#2563eb",
    "Violet": "#7c3aed",
    "Red": "#dc2626",
    "Yellow": "#f59e0b",
}

ACTIVE_LAYER_WM2_PER_FPH = 4.9


# ---------------------------------------------------------------------------
# CSS — preserved exactly from original (formerly injected via st.markdown)
# Include this in your Django base template with {{ CARD_CSS|safe }}
# ---------------------------------------------------------------------------

CARD_CSS = """
<style>
.summary-strip {display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px;margin:6px 0 18px 0;}
.summary-card {border:1px solid transparent;border-radius:16px;padding:14px 16px;box-shadow:0 2px 8px rgba(0,0,0,0.12);}
.summary-card-neutral {background:linear-gradient(180deg,#103d75 0%,#0c2c53 100%);border-color:#0c2c53;}
.summary-label {font-size:0.78rem;text-transform:uppercase;letter-spacing:0.04em;opacity:0.82;font-weight:700;margin-bottom:6px;}
.summary-main {font-size:1.12rem;font-weight:800;line-height:1.2;}
.summary-sub {font-size:0.82rem;opacity:0.92;margin-top:6px;line-height:1.25;}
.wax-run-card {border:1px solid #d8dde6;border-radius:16px;padding:16px 16px 10px 16px;box-shadow:0 1px 6px rgba(0,0,0,0.06);margin-bottom:10px;}
.wax-run-header {display:flex;justify-content:space-between;align-items:flex-start;gap:12px;margin-bottom:10px;}
.wax-run-eyebrow {font-size:0.82rem;color:#556;text-transform:uppercase;letter-spacing:0.05em;font-weight:700;}
.wax-run-time {font-size:1.05rem;font-weight:700;color:#111827;}
.wax-band-pill {border-radius:999px;padding:6px 12px;font-size:0.85rem;font-weight:700;white-space:nowrap;}
.wax-grid {display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px;}
.wax-mini-card {background:white;border:1px solid #e5e7eb;border-radius:12px;padding:10px 12px;min-height:76px;}
.wax-mini-title {font-size:0.78rem;color:#667085;text-transform:uppercase;letter-spacing:0.04em;font-weight:700;margin-bottom:5px;}
.wax-mini-value {font-size:0.98rem;font-weight:700;color:#111827;line-height:1.25;}
.wax-mini-subtitle {margin-top:4px;font-size:0.80rem;color:#6b7280;line-height:1.25;}
.wax-split-top{padding:10px 12px;font-size:0.90rem;font-weight:800;line-height:1.2;}
.wax-split-bottom{padding:10px 12px;font-size:0.88rem;color:#111827;line-height:1.25;background:#ffffff;}
@media (max-width: 900px) {.summary-strip {grid-template-columns:1fr;}}
@media (max-width: 1100px) {.wax-grid {grid-template-columns:repeat(2,minmax(0,1fr));}}
</style>
"""


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class ModelParams:
    wind_coeff: float
    solar_coeff: float
    clear_night_coeff: float
    longwave_coeff: float
    latent_coeff: float
    restore_coeff: float
    lapse_cap_f_per_1000ft: float
    deep_snow_start_f: float
    deep_snow_finish_f: float
    deep_auto_relax_coeff: float
    slope_deg: float
    aspect_deg: float
    cloud_attenuation: float
    diffuse_floor_frac: float
    albedo: float


# ---------------------------------------------------------------------------
# Color helpers (unchanged)
# ---------------------------------------------------------------------------

def product_color(name: str) -> str:
    for key, color in PRODUCT_COLORS.items():
        if key in name:
            return color
    return "#64748b"


def hex_to_rgba(hex_color: str, alpha: float) -> str:
    hex_color = hex_color.lstrip("#")
    if len(hex_color) != 6:
        return f"rgba(100,116,139,{alpha})"
    r = int(hex_color[0:2], 16)
    g = int(hex_color[2:4], 16)
    b = int(hex_color[4:6], 16)
    return f"rgba({r},{g},{b},{alpha})"


def text_color_for_wax(hex_color: str) -> str:
    c = hex_color.lower()
    if (
        c in {"#f59e0b", "#ffd54f", "#facc15", "#eab308", "#1bb3c8"}
        or "f59e0b" in c or "facc15" in c or "eab308" in c or "1bb3c8" in c
    ):
        return "#111827"
    return "#ffffff"


# ---------------------------------------------------------------------------
# Physics / thermodynamics helpers (unchanged)
# ---------------------------------------------------------------------------

def temp_to_c(tf: pd.Series | float) -> pd.Series | float:
    return (tf - 32.0) * 5.0 / 9.0


def saturation_vapor_pressure_hpa(temp_c: float | np.ndarray) -> float | np.ndarray:
    temp_c = np.asarray(temp_c, dtype=float)
    return 6.112 * np.exp((17.67 * temp_c) / (temp_c + 243.5))


def longwave_exchange_term_f(air_f: float, snow_f: float, rh_pct: float, cloud_frac: float, coeff: float) -> float:
    sigma = 5.670374419e-8
    ta_k = (air_f - 32.0) * 5.0 / 9.0 + 273.15
    ts_k = (snow_f - 32.0) * 5.0 / 9.0 + 273.15
    rh = float(np.clip(rh_pct if pd.notna(rh_pct) else 75.0, 5.0, 100.0)) / 100.0
    cloud = float(np.clip(cloud_frac if pd.notna(cloud_frac) else 0.5, 0.0, 1.0))
    emiss_air = np.clip(0.70 + 0.00025 * rh * saturation_vapor_pressure_hpa((air_f - 32.0) * 5.0 / 9.0) * 100.0, 0.72, 0.99)
    emiss_sky = np.clip(emiss_air * (1.0 + 0.22 * cloud * cloud), 0.72, 0.995)
    incoming = emiss_sky * sigma * ta_k**4
    outgoing = 0.99 * sigma * ts_k**4
    return coeff * ((incoming - outgoing) / 100.0)


def latent_exchange_term_f(air_f: float, snow_f: float, rh_pct: float, wind_mph: float, coeff: float) -> float:
    ta_c = (air_f - 32.0) * 5.0 / 9.0
    ts_c = min((snow_f - 32.0) * 5.0 / 9.0, 0.0)
    rh = float(np.clip(rh_pct if pd.notna(rh_pct) else 75.0, 1.0, 100.0)) / 100.0
    wind = float(np.clip(wind_mph if pd.notna(wind_mph) else 0.0, 0.0, 60.0))
    ea = rh * saturation_vapor_pressure_hpa(ta_c)
    es_surface = saturation_vapor_pressure_hpa(ts_c)
    vapor_gradient = ea - es_surface
    return coeff * wind * (vapor_gradient / 6.0)


def clear_night_cooling_term_f(rh_pct: float, cloud_frac: float, wind_mph: float, solar_elev_deg: float, coeff: float) -> float:
    if pd.isna(solar_elev_deg):
        solar_elev_deg = -6.0
    if solar_elev_deg >= 2.0:
        return 0.0
    rh = float(np.clip(rh_pct if pd.notna(rh_pct) else 75.0, 5.0, 100.0)) / 100.0
    cloud = float(np.clip(cloud_frac if pd.notna(cloud_frac) else 0.5, 0.0, 1.0))
    wind = float(np.clip(wind_mph if pd.notna(wind_mph) else 0.0, 0.0, 40.0))
    twilight_factor = 1.0 if solar_elev_deg <= -6.0 else float(np.clip((2.0 - solar_elev_deg) / 8.0, 0.0, 1.0))
    humidity_factor = float(np.clip(1.15 - rh, 0.15, 1.0))
    wind_factor = 1.0 / (1.0 + 0.10 * wind)
    return coeff * (1.0 - cloud) * humidity_factor * wind_factor * twilight_factor


def parse_wind_speed_to_mph(value: Optional[str]) -> float:
    if value is None:
        return np.nan
    text = str(value).lower().replace("mph", "").strip()
    if " to " in text:
        vals = [float(p) for p in text.split(" to ") if p.strip()]
        return float(np.mean(vals)) if vals else np.nan
    try:
        return float(text.split()[0])
    except Exception:
        return np.nan


# ---------------------------------------------------------------------------
# HTTP / NWS fetch helpers (unchanged, @st.cache_data replaced with lru_cache)
# ---------------------------------------------------------------------------

def build_session() -> requests.Session:
    session = requests.Session()
    retry = Retry(
        total=5,
        connect=5,
        read=5,
        backoff_factor=1.5,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset(["GET"]),
        raise_on_status=False,
        respect_retry_after_header=True,
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    session.headers.update(HEADERS)
    return session


def periods_to_df(periods: list[dict]) -> pd.DataFrame:
    rows = []
    for p in periods:
        rh = p.get("relativeHumidity")
        rows.append(
            {
                "time": pd.to_datetime(p["startTime"]),
                "air_temp_f": p.get("temperature"),
                "wind_mph": parse_wind_speed_to_mph(p.get("windSpeed")),
                "is_day": bool(p.get("isDaytime")),
                "short_forecast": p.get("shortForecast", ""),
                "precip_prob_pct": (p.get("probabilityOfPrecipitation") or {}).get("value"),
                "rh_pct": (rh or {}).get("value"),
                "sky_cover_pct": p.get("skyCover") if p.get("skyCover") is not None else np.nan,
            }
        )
    df = pd.DataFrame(rows)
    if df.empty:
        raise ValueError("No forecast periods returned from NWS API.")
    df["time"] = df["time"].dt.tz_convert(LOCAL_TZ).dt.tz_localize(None)
    df["air_temp_c"] = temp_to_c(df["air_temp_f"])
    return df


def parse_iso8601_duration_to_timedelta(duration: str) -> pd.Timedelta:
    if not duration or not duration.startswith("P"):
        return pd.Timedelta(hours=1)
    match = re.fullmatch(
        r"P(?:(?P<days>\d+)D)?(?:T(?:(?P<hours>\d+)H)?(?:(?P<minutes>\d+)M)?(?:(?P<seconds>\d+)S)?)?",
        duration,
    )
    if not match:
        return pd.Timedelta(hours=1)
    parts = {k: int(v) if v else 0 for k, v in match.groupdict().items()}
    td = pd.Timedelta(days=parts["days"], hours=parts["hours"], minutes=parts["minutes"], seconds=parts["seconds"])
    return td if td > pd.Timedelta(0) else pd.Timedelta(hours=1)


def parse_valid_time_interval(valid_time: str) -> tuple[pd.Timestamp, pd.Timestamp]:
    if "/" not in valid_time:
        start = pd.to_datetime(valid_time)
        return start, start + pd.Timedelta(hours=1)
    start_text, duration_text = valid_time.split("/", 1)
    start = pd.to_datetime(start_text)
    duration = parse_iso8601_duration_to_timedelta(duration_text)
    return start, start + duration


def grid_values_to_hourly_series(values: list[dict], hourly_times_naive: pd.Series) -> pd.Series:
    if not values:
        return pd.Series(np.nan, index=hourly_times_naive.index, dtype=float)
    hourly_local = pd.to_datetime(hourly_times_naive).dt.tz_localize(LOCAL_TZ)
    out = pd.Series(np.nan, index=hourly_times_naive.index, dtype=float)
    for entry in values:
        vt = entry.get("validTime")
        val = entry.get("value")
        if vt is None or val is None:
            continue
        start, end = parse_valid_time_interval(vt)
        start = start.tz_localize(LOCAL_TZ) if start.tzinfo is None else start.tz_convert(LOCAL_TZ)
        end = end.tz_localize(LOCAL_TZ) if end.tzinfo is None else end.tz_convert(LOCAL_TZ)
        mask = (hourly_local >= start) & (hourly_local < end)
        out.loc[mask] = float(val)
    return out.ffill().bfill()


def fetch_json(session: requests.Session, url: str) -> dict:
    last_error = None
    for pause in (0.0, 1.0, 3.0):
        try:
            if pause:
                time.sleep(pause)
            resp = session.get(url, timeout=(10, 60))
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:
            last_error = exc
    raise RuntimeError(f"Request failed for {url}: {last_error}")


def get_hourly_forecast(lat: float, lon: float) -> pd.DataFrame:
    """Fetch NWS hourly forecast with local file cache fallback (30 min TTL)."""
    cache_key = f"{lat:.4f}_{lon:.4f}".replace("-", "m").replace(".", "p")
    cache_path = FORECAST_CACHE_DIR / f"forecast_{cache_key}.json"
    session = build_session()
    last_error = None
    try:
        point_json = fetch_json(session, f"https://api.weather.gov/points/{lat},{lon}")
        point = point_json["properties"]
        hourly_url = point["forecastHourly"]
        grid_url = point["forecastGridData"]

        forecast_json = fetch_json(session, hourly_url)
        periods = forecast_json["properties"]["periods"]
        df = periods_to_df(periods)

        grid_json = fetch_json(session, grid_url)
        sky_values = ((grid_json.get("properties") or {}).get("skyCover") or {}).get("values", [])
        if sky_values:
            df["sky_cover_pct"] = grid_values_to_hourly_series(sky_values, df["time"])
            df["sky_cover_source"] = "NWS forecastGridData skyCover"
        else:
            df["sky_cover_source"] = np.where(df["sky_cover_pct"].notna(), "NWS forecastHourly skyCover", "Missing")

        cache_payload = {
            "fetched_at": pd.Timestamp.now(tz=LOCAL_TZ).isoformat(),
            "periods": periods,
            "sky_values": sky_values,
        }
        cache_path.write_text(json.dumps(cache_payload), encoding="utf-8")
        LAST_FETCH_META[cache_key] = "live"
        return df
    except Exception as exc:
        last_error = exc

    if cache_path.exists():
        cached = json.loads(cache_path.read_text(encoding="utf-8"))
        periods = cached.get("periods", [])
        df = periods_to_df(periods)
        sky_values = cached.get("sky_values", [])
        if sky_values:
            df["sky_cover_pct"] = grid_values_to_hourly_series(sky_values, df["time"])
            df["sky_cover_source"] = "Cached NWS forecastGridData skyCover"
        else:
            df["sky_cover_source"] = np.where(df["sky_cover_pct"].notna(), "Cached forecastHourly skyCover", "Missing")
        fetched_at = cached.get("fetched_at", "unknown time")
        LAST_FETCH_META[cache_key] = f"cached from {fetched_at} after live fetch failed: {last_error}"
        return df
    raise RuntimeError(f"Could not fetch the NWS forecast after multiple retries. Original error: {last_error}")


def merge_forecasts(upper: pd.DataFrame, lower: pd.DataFrame) -> pd.DataFrame:
    a = upper.rename(columns={
        "air_temp_f": "air_upper_f", "air_temp_c": "air_upper_c", "wind_mph": "wind_upper_mph",
        "rh_pct": "rh_upper_pct", "sky_cover_pct": "sky_upper_pct", "sky_cover_source": "sky_upper_source",
        "precip_prob_pct": "pop_upper_pct", "short_forecast": "forecast_upper", "is_day": "is_day_upper",
    })
    b = lower.rename(columns={
        "air_temp_f": "air_lower_f", "air_temp_c": "air_lower_c", "wind_mph": "wind_lower_mph",
        "rh_pct": "rh_lower_pct", "sky_cover_pct": "sky_lower_pct", "sky_cover_source": "sky_lower_source",
        "precip_prob_pct": "pop_lower_pct", "short_forecast": "forecast_lower", "is_day": "is_day_lower",
    })
    return pd.merge(a, b, on="time", how="inner").sort_values("time").reset_index(drop=True)


def solar_geometry_and_irradiance(
    times_local_naive: tuple,
    lat: float,
    lon: float,
    elev_m: float,
    slope_deg: float,
    aspect_deg: float,
    cloud_tuple: tuple,
    cloud_attenuation: float,
    diffuse_floor_frac: float,
    albedo: float,
) -> pd.DataFrame:
    times = pd.DatetimeIndex(list(times_local_naive)).tz_localize(LOCAL_TZ)
    loc = Location(lat, lon, tz=LOCAL_TZ, altitude=elev_m)
    solpos = loc.get_solarposition(times)
    clearsky = loc.get_clearsky(times, model="ineichen")
    cloud_frac = np.clip(np.asarray(cloud_tuple, dtype=float), 0.0, 1.0)
    trans = np.clip(1.0 - cloud_attenuation * cloud_frac, 0.05, 1.0)
    ghi = clearsky["ghi"].to_numpy() * trans
    dni = clearsky["dni"].to_numpy() * np.clip(trans ** 1.3, 0.02, 1.0)
    dhi = clearsky["dhi"].to_numpy() * np.clip(diffuse_floor_frac + (1.0 - diffuse_floor_frac) * trans, 0.05, 1.0)
    poa = pvlib.irradiance.get_total_irradiance(
        surface_tilt=slope_deg,
        surface_azimuth=aspect_deg,
        solar_zenith=solpos["apparent_zenith"],
        solar_azimuth=solpos["azimuth"],
        dni=dni,
        ghi=ghi,
        dhi=dhi,
        albedo=albedo,
        model="isotropic",
    )
    out = pd.DataFrame({
        "time": times.tz_localize(None),
        "solar_zenith_deg": solpos["apparent_zenith"].to_numpy(),
        "solar_elevation_deg": solpos["elevation"].to_numpy(),
        "solar_azimuth_deg": solpos["azimuth"].to_numpy(),
        "poa_global_wm2": np.clip(poa["poa_global"].to_numpy(), 0.0, None),
    })
    out["solar_norm"] = (out["poa_global_wm2"] / 1000.0).clip(0.0, 1.2)
    return out


# ---------------------------------------------------------------------------
# Deep snow / seasonal helpers (unchanged)
# ---------------------------------------------------------------------------

def seasonal_deep_snow_baseline_f(day_of_year: int) -> float:
    baseline = 25.0 + 7.0 * math.sin(2.0 * math.pi * (day_of_year - 100.0) / 365.25)
    return float(np.clip(baseline, 16.0, 32.0))


def estimate_initial_deep_snow_temp_f(air_series_f: pd.Series, race_date: pd.Timestamp) -> float:
    valid = pd.to_numeric(air_series_f, errors="coerce").dropna()
    recent_mean = float(valid.iloc[: min(len(valid), 36)].mean()) if not valid.empty else 24.0
    seasonal = seasonal_deep_snow_baseline_f(int(pd.Timestamp(race_date).dayofyear))
    estimate = 0.65 * recent_mean + 0.35 * seasonal - 1.5
    return float(np.clip(estimate, 12.0, 32.0))


def evolve_deep_snow_series_f(forcing_air_f: pd.Series, initial_deep_f: float, relax_coeff: float) -> pd.Series:
    vals = [float(initial_deep_f)]
    forcing = pd.to_numeric(forcing_air_f, errors="coerce").ffill().bfill().to_numpy()
    for i in range(1, len(forcing)):
        prev = vals[-1]
        vals.append(float(np.clip(prev + relax_coeff * (forcing[i - 1] - prev), 0.0, 32.0)))
    return pd.Series(vals, index=forcing_air_f.index, dtype=float)


# ---------------------------------------------------------------------------
# Venue / model preparation (unchanged)
# ---------------------------------------------------------------------------

def prepare_venue(df: pd.DataFrame, venue: dict, start_ft: float, finish_ft: float, params: ModelParams, race_date: pd.Timestamp) -> pd.DataFrame:
    points = venue["points"]
    upper_pt = points["Upper NWS point"]
    lower_pt = points["Lower NWS point"]
    out = df.copy()
    delta_ft = upper_pt["elev_ft"] - lower_pt["elev_ft"]
    raw_lapse_f_per_ft = (out["air_upper_f"] - out["air_lower_f"]) / delta_ft
    cap = params.lapse_cap_f_per_1000ft / 1000.0
    out["lapse_f_per_ft"] = raw_lapse_f_per_ft.clip(-cap, cap)
    out["lapse_f_per_1000ft"] = out["lapse_f_per_ft"] * 1000.0
    out["air_start_f"] = out["air_upper_f"] + out["lapse_f_per_ft"] * (start_ft - upper_pt["elev_ft"])
    out["air_finish_f"] = out["air_upper_f"] + out["lapse_f_per_ft"] * (finish_ft - upper_pt["elev_ft"])
    out["wind_start_mph"] = out[["wind_upper_mph", "wind_lower_mph"]].mean(axis=1).ffill().fillna(0.0)
    out["wind_finish_mph"] = out["wind_start_mph"]
    out["sky_pct"] = out[["sky_upper_pct", "sky_lower_pct"]].mean(axis=1)
    sky_default = pd.Series(np.where(out["is_day_upper"], 45.0, 65.0), index=out.index)
    out["sky_pct"] = out["sky_pct"].where(out["sky_pct"].notna(), sky_default)
    both_grid = out["sky_upper_source"].fillna("").str.contains("skyCover") & out["sky_lower_source"].fillna("").str.contains("skyCover")
    one_grid = out[["sky_upper_pct", "sky_lower_pct"]].notna().any(axis=1)
    out["sky_source"] = np.where(both_grid, "NWS grid sky cover (both points)", np.where(one_grid, "NWS grid sky cover (one point)", "Fallback default"))
    out["rh_pct"] = out[["rh_upper_pct", "rh_lower_pct"]].mean(axis=1).fillna(70.0)
    out["cloud_frac"] = (out["sky_pct"] / 100.0).clip(0.0, 1.0)

    solar = solar_geometry_and_irradiance(
        tuple(out["time"]), venue["lat"], venue["lon"], venue["elev_ft"] * 0.3048,
        params.slope_deg, params.aspect_deg, tuple(out["cloud_frac"]),
        params.cloud_attenuation, params.diffuse_floor_frac, params.albedo,
    )
    out = out.merge(solar, on="time", how="left")
    out["solar_norm"] = out["solar_norm"].fillna(0.0)
    out["poa_global_wm2"] = out["poa_global_wm2"].fillna(0.0)

    out["clear_night_start_fph"] = [clear_night_cooling_term_f(rh, cf, w, se, params.clear_night_coeff) for rh, cf, w, se in zip(out["rh_pct"], out["cloud_frac"], out["wind_start_mph"], out["solar_elevation_deg"])]
    out["clear_night_finish_fph"] = [clear_night_cooling_term_f(rh, cf, w, se, params.clear_night_coeff) for rh, cf, w, se in zip(out["rh_pct"], out["cloud_frac"], out["wind_finish_mph"], out["solar_elevation_deg"])]

    deep_start_init = estimate_initial_deep_snow_temp_f(out["air_start_f"], pd.Timestamp(race_date))
    deep_finish_init = estimate_initial_deep_snow_temp_f(out["air_finish_f"], pd.Timestamp(race_date))
    if not math.isnan(params.deep_snow_start_f):
        deep_start_init = params.deep_snow_start_f
    if not math.isnan(params.deep_snow_finish_f):
        deep_finish_init = params.deep_snow_finish_f
    out["deep_snow_start_f"] = evolve_deep_snow_series_f(out["air_start_f"], deep_start_init, params.deep_auto_relax_coeff)
    out["deep_snow_finish_f"] = evolve_deep_snow_series_f(out["air_finish_f"], deep_finish_init, params.deep_auto_relax_coeff)

    snow_start = [float(out["deep_snow_start_f"].iloc[0])]
    snow_finish = [float(out["deep_snow_finish_f"].iloc[0])]
    for i in range(1, len(out)):
        prev_start = snow_start[-1]
        prev_finish = snow_finish[-1]
        row_prev = out.iloc[i - 1]
        lw_start = longwave_exchange_term_f(row_prev["air_start_f"], prev_start, row_prev["rh_pct"], row_prev["cloud_frac"], params.longwave_coeff)
        lw_finish = longwave_exchange_term_f(row_prev["air_finish_f"], prev_finish, row_prev["rh_pct"], row_prev["cloud_frac"], params.longwave_coeff)
        latent_start = latent_exchange_term_f(row_prev["air_start_f"], prev_start, row_prev["rh_pct"], row_prev["wind_start_mph"], params.latent_coeff)
        latent_finish = latent_exchange_term_f(row_prev["air_finish_f"], prev_finish, row_prev["rh_pct"], row_prev["wind_finish_mph"], params.latent_coeff)
        clear_start = row_prev["clear_night_start_fph"]
        sensible_start = params.wind_coeff * (1 + 0.08 * row_prev["wind_start_mph"]) * (row_prev["air_start_f"] - prev_start)
        ground_start = params.restore_coeff * (row_prev["deep_snow_start_f"] - prev_start)
        solar_term = params.solar_coeff * row_prev["solar_norm"]
        next_start = prev_start + (sensible_start + solar_term - clear_start + lw_start + latent_start + ground_start)
        clear_finish = row_prev["clear_night_finish_fph"]
        sensible_finish = params.wind_coeff * (1 + 0.08 * row_prev["wind_finish_mph"]) * (row_prev["air_finish_f"] - prev_finish)
        ground_finish = params.restore_coeff * (row_prev["deep_snow_finish_f"] - prev_finish)
        next_finish = prev_finish + (sensible_finish + solar_term - clear_finish + lw_finish + latent_finish + ground_finish)
        snow_start.append(min(next_start, 32.0))
        snow_finish.append(min(next_finish, 32.0))

    out["snow_start_pred_f"] = snow_start
    out["snow_finish_pred_f"] = snow_finish
    out["snow_start_pred_c"] = temp_to_c(out["snow_start_pred_f"])
    out["snow_finish_pred_c"] = temp_to_c(out["snow_finish_pred_f"])
    out["solar_fph"] = params.solar_coeff * out["solar_norm"]
    out["sensible_start_fph"] = params.wind_coeff * (1 + 0.08 * out["wind_start_mph"]) * (out["air_start_f"] - out["snow_start_pred_f"])
    out["sensible_finish_fph"] = params.wind_coeff * (1 + 0.08 * out["wind_finish_mph"]) * (out["air_finish_f"] - out["snow_finish_pred_f"])
    out["ground_start_fph"] = params.restore_coeff * (out["deep_snow_start_f"] - out["snow_start_pred_f"])
    out["ground_finish_fph"] = params.restore_coeff * (out["deep_snow_finish_f"] - out["snow_finish_pred_f"])
    out["longwave_start_fph"] = [longwave_exchange_term_f(a, s, rh, cf, params.longwave_coeff) for a, s, rh, cf in zip(out["air_start_f"], out["snow_start_pred_f"], out["rh_pct"], out["cloud_frac"])]
    out["longwave_finish_fph"] = [longwave_exchange_term_f(a, s, rh, cf, params.longwave_coeff) for a, s, rh, cf in zip(out["air_finish_f"], out["snow_finish_pred_f"], out["rh_pct"], out["cloud_frac"])]
    out["latent_start_fph"] = [latent_exchange_term_f(a, s, rh, w, params.latent_coeff) for a, s, rh, w in zip(out["air_start_f"], out["snow_start_pred_f"], out["rh_pct"], out["wind_start_mph"])]
    out["latent_finish_fph"] = [latent_exchange_term_f(a, s, rh, w, params.latent_coeff) for a, s, rh, w in zip(out["air_finish_f"], out["snow_finish_pred_f"], out["rh_pct"], out["wind_finish_mph"])]
    out["net_start_fph"] = out["solar_fph"] + out["sensible_start_fph"] - out["clear_night_start_fph"] + out["longwave_start_fph"] + out["latent_start_fph"] + out["ground_start_fph"]
    out["net_finish_fph"] = out["solar_fph"] + out["sensible_finish_fph"] - out["clear_night_finish_fph"] + out["longwave_finish_fph"] + out["latent_finish_fph"] + out["ground_finish_fph"]
    for col in ["solar_fph", "sensible_start_fph", "sensible_finish_fph", "clear_night_start_fph", "clear_night_finish_fph", "longwave_start_fph", "longwave_finish_fph", "latent_start_fph", "latent_finish_fph", "ground_start_fph", "ground_finish_fph", "net_start_fph", "net_finish_fph"]:
        out[col.replace("_fph", "_wm2")] = out[col] * ACTIVE_LAYER_WM2_PER_FPH
    return out


def attach_observations(model_df: pd.DataFrame, obs_df: Optional[pd.DataFrame]) -> pd.DataFrame:
    out = model_df.copy()
    for col in OBS_COLUMNS[1:]:
        out[col] = np.nan
    if obs_df is None or obs_df.empty:
        return out
    local = obs_df.copy()
    local.columns = [c.strip().lower() for c in local.columns]
    missing = [c for c in OBS_COLUMNS if c not in local.columns]
    if missing:
        raise ValueError(f"Observation file is missing columns: {', '.join(missing)}")
    local["time"] = pd.to_datetime(local["time"]).dt.tz_localize(None)
    return pd.merge(out, local[OBS_COLUMNS], on="time", how="left", suffixes=("", "_obs"))


def error_metrics(series_pred: pd.Series, series_obs: pd.Series) -> dict[str, float]:
    valid = ~(series_pred.isna() | series_obs.isna())
    if valid.sum() == 0:
        return {"n": 0, "mae": np.nan, "bias": np.nan}
    err = series_pred[valid] - series_obs[valid]
    return {"n": int(valid.sum()), "mae": float(np.abs(err).mean()), "bias": float(err.mean())}


# ---------------------------------------------------------------------------
# Wax selection logic (unchanged)
# ---------------------------------------------------------------------------

def select_product_tuple(temp_c: float, products: list[tuple[str, float, float]]) -> tuple[str, float, float]:
    if pd.isna(temp_c):
        return ("—", np.nan, np.nan)
    for name, low, high in products:
        if low <= temp_c <= high:
            return (name, low, high)
    return min(products, key=lambda x: abs(temp_c - (x[1] + x[2]) / 2.0))


def select_temp_product(temp_c: float, products: list[tuple[str, float, float]]) -> str:
    name, low, high = select_product_tuple(temp_c, products)
    if pd.isna(low):
        return "—"
    nearest_text = "" if low <= temp_c <= high else ", nearest match"
    return f"{name} ({low:.0f} to {high:.0f}°C{nearest_text})"


def format_range_f(start_f: float, finish_f: float) -> str:
    lo = min(start_f, finish_f)
    hi = max(start_f, finish_f)
    return f"{lo:.1f} to {hi:.1f} °F"


def hs_candidates(temp_c: float) -> list[tuple[str, float, float]]:
    return [p for p in HS_PRODUCTS if p[1] <= temp_c <= p[2]]


def choose_overlap_primary(candidates: list[tuple[str, float, float]], snow_type: str, glide_regime: str, avg_air_f: float, rh_pct: float) -> tuple[tuple[str, float, float], str]:
    if len(candidates) <= 1:
        return (candidates[0] if candidates else select_product_tuple(temp_to_c(avg_air_f), HS_PRODUCTS)), "Single HS window."
    colder = sorted(candidates, key=lambda x: x[1])[0]
    warmer = sorted(candidates, key=lambda x: x[1])[-1]
    colder_bias = 0
    warmer_bias = 0
    reasons = []
    if snow_type in {"Fine / new snow", "Aggressive cold / manmade", "Injected / icy"}:
        colder_bias += 2
        reasons.append("favored colder for sharper / more abrasive snow")
    if glide_regime == "Cold dry friction":
        colder_bias += 1
        reasons.append("favored colder in dry-friction conditions")
    if pd.notna(rh_pct) and rh_pct <= 35:
        colder_bias += 1
        reasons.append("favored colder in dry air")
    if snow_type == "Coarse / transformed / artificial":
        warmer_bias += 1
    if glide_regime in {"Transitional mixed", "Wet suction / free water"}:
        warmer_bias += 2
        reasons.append("favored warmer in wetter / transformed conditions")
    if avg_air_f >= 28:
        warmer_bias += 1
        reasons.append("favored warmer with milder air temperatures")
    chosen = colder if colder_bias >= warmer_bias else warmer
    if not reasons:
        reasons.append("defaulted slightly colder as a conservative tie-breaker")
    return chosen, "; ".join(reasons)


def hs_call_from_conditions(start_snow_f: float, finish_snow_f: float, start_air_f: float, finish_air_f: float, snow_type: str) -> tuple[str, str, float, str, bool]:
    start_c = float(temp_to_c(start_snow_f))
    finish_c = float(temp_to_c(finish_snow_f))
    start_adj = adjust_temp_for_snow_type(start_c, snow_type)
    finish_adj = adjust_temp_for_snow_type(finish_c, snow_type)
    melt_flag = max(start_snow_f, finish_snow_f) >= 31.5 and max(start_air_f, finish_air_f) > 32.0
    if melt_flag:
        name, _low, _high = HS_PRODUCTS[-1]
        note = "Predicted surface at 32°F with above-freezing air suggests melt / liquid water, so HS10 Yellow is favored."
        return name, note, max(start_adj, finish_adj), product_color(name), True
    weighted = 0.45 * start_adj + 0.55 * finish_adj
    name, _low, _high = select_product_tuple(weighted, HS_PRODUCTS)
    note = f"HS call weighted 45% start / 55% finish after snow-type adjustment: {weighted:.1f}°C."
    return name, note, weighted, product_color(name), False


def humidity_bucket(rh_pct: float) -> str:
    if pd.isna(rh_pct):
        return "mid"
    if rh_pct <= 25:
        return "dry"
    if rh_pct <= 35:
        return "mid"
    return "wet"


def _forecast_text_has(text: str, phrases: list[str]) -> bool:
    text = text.lower()
    return any(p in text for p in phrases)


def _combined_air_f(window: pd.DataFrame) -> pd.Series:
    return window[["air_start_f", "air_finish_f"]].mean(axis=1)


def infer_snow_type(model: pd.DataFrame, run_dt: pd.Timestamp, mode: str) -> tuple[str, str, float]:
    if mode != "Auto":
        return mode, f"Manual override: {mode}", 0.9
    lookback = model[(model["time"] >= run_dt - pd.Timedelta(hours=48)) & (model["time"] <= run_dt)].copy()
    if lookback.empty:
        lookback = model.iloc[: min(48, len(model))].copy()

    lookback["combined_text"] = (lookback["forecast_upper"].fillna("") + " " + lookback["forecast_lower"].fillna("")).str.lower()
    lookback["mean_air_f"] = _combined_air_f(lookback)
    lookback["max_pop_pct"] = lookback[["pop_upper_pct", "pop_lower_pct"]].max(axis=1).fillna(0.0)
    lookback["snow_word"] = lookback["combined_text"].apply(lambda t: _forecast_text_has(t, ["snow", "snow showers", "flurries"]))
    lookback["mixed_word"] = lookback["combined_text"].apply(lambda t: _forecast_text_has(t, ["sleet", "wintry mix", "mix", "rain/snow", "rain and snow"]))
    lookback["rain_word"] = lookback["combined_text"].apply(lambda t: _forecast_text_has(t, ["rain", "drizzle", "showers", "freezing rain"]))

    snow_event = lookback[
        (lookback["snow_word"])
        & (~lookback["mixed_word"])
        & (lookback["max_pop_pct"] >= 35)
        & (lookback["mean_air_f"] <= 33.5)
    ].copy()

    fresh_persistence = 0.0
    persistence_note = "No credible fresh-snow signal in the last 48 hours."
    if not snow_event.empty:
        last_snow_time = snow_event["time"].max()
        after = lookback[lookback["time"] >= last_snow_time].copy()
        fresh_persistence = 1.0
        for air_f in after["mean_air_f"].fillna(after["air_start_f"]):
            if air_f <= 20:
                fresh_persistence -= 0.005
            elif air_f <= 25:
                fresh_persistence -= 0.010
            elif air_f <= 30:
                fresh_persistence -= 0.025
            elif air_f <= 32:
                fresh_persistence -= 0.050
            else:
                fresh_persistence -= 0.080
        if after["rain_word"].any():
            fresh_persistence -= 0.40
        if (after["mean_air_f"] > 32).sum() >= 3:
            fresh_persistence -= 0.30
        if (after["mean_air_f"] >= 28).sum() >= 8:
            fresh_persistence -= 0.15
        fresh_persistence = float(max(0.0, min(1.0, fresh_persistence)))
        hrs = int((run_dt - last_snow_time).total_seconds() / 3600.0)
        persistence_note = f"Credible snowfall {hrs} h before the run; fresh-snow persistence score {fresh_persistence:.2f} after accounting for post-snow temperatures and any wetting."

    recent24 = lookback[lookback["time"] >= run_dt - pd.Timedelta(hours=24)].copy()
    mean_air_24 = float(_combined_air_f(recent24).mean()) if not recent24.empty else float(_combined_air_f(lookback).mean())
    min_air_12 = float(_combined_air_f(lookback[lookback["time"] >= run_dt - pd.Timedelta(hours=12)]).min()) if not lookback.empty else np.nan
    max_air_24 = float(_combined_air_f(recent24).max()) if not recent24.empty else np.nan
    rain_or_wet = bool(recent24["rain_word"].any() or recent24["mixed_word"].any())
    thaw_refreeze = bool(((recent24["mean_air_f"] > 32).any() or rain_or_wet) and pd.notna(min_air_12) and min_air_12 <= 31.0)
    freezing_rain_signal = bool(recent24["combined_text"].str.contains("freezing rain", regex=False).any())
    avg_snow_c = float(temp_to_c(lookback["snow_start_pred_f"].mean()))
    precip_prob = float(lookback["max_pop_pct"].max()) if not lookback.empty else 0.0
    rh_mean = float(lookback["rh_pct"].mean()) if lookback["rh_pct"].notna().any() else 70.0

    if fresh_persistence >= 0.65:
        conf = min(0.95, 0.72 + 0.20 * fresh_persistence)
        return "Fine / new snow", persistence_note + " Fresh crystals likely remain sharp enough to ski like new snow.", conf
    if thaw_refreeze or freezing_rain_signal:
        note = "Recent melt/rain followed by sub-freezing temperatures suggests a refrozen or icy surface."
        return "Injected / icy", note, 0.82
    if avg_snow_c <= -10 and precip_prob < 25 and rh_mean < 75 and mean_air_24 <= 22:
        note = "Cold, dry weather without recent fresh snow favors an aggressive old/manmade race surface."
        return "Aggressive cold / manmade", note, 0.72
    if fresh_persistence >= 0.35:
        note = persistence_note + " Fresh snow signal is fading, so the surface is likely transitional rather than truly new."
        return "Coarse / transformed / artificial", note, 0.68
    note = "No strong fresh-snow or thaw-refreeze signal was found; defaulting to coarse / transformed snow."
    return "Coarse / transformed / artificial", note, 0.62


def adjust_temp_for_snow_type(temp_c: float, snow_type: str) -> float:
    offsets = {
        "Fine / new snow": 0.5,
        "Coarse / transformed / artificial": 0.0,
        "Aggressive cold / manmade": -0.7,
        "Injected / icy": -1.2,
    }
    return temp_c + offsets.get(snow_type, 0.0)


def world_cup_recommendation(temp_c: float, rh_pct: float, snow_type: str, dirty: bool) -> tuple[str, str]:
    hum = humidity_bucket(rh_pct)
    if dirty or snow_type == "Injected / icy":
        return ("PM WC Powder Molybdenum", "DH7 Black World Cup Glider")
    if snow_type == "Fine / new snow":
        powder = {"dry": "PF25 WC Powder Fine Dry", "mid": "PF35 WC Powder Fine Mid", "wet": "PF100 WC Powder Fine Wet"}[hum]
    else:
        powder = {"dry": "PC25 WC Powder Coarse Dry", "mid": "PC35 WC Powder Coarse Mid", "wet": "PC100 WC Powder Coarse Wet"}[hum]
    glider = "DH7 World Cup Glider" if rh_pct > 60 else "DH6 World Cup Glider"
    return powder, glider


def wax_band(temp_f: float) -> str:
    if pd.isna(temp_f):
        return "—"
    if temp_f >= 28:
        return "Warm / transformed"
    if temp_f >= 22:
        return "Mid-cold"
    if temp_f >= 12:
        return "Cold"
    return "Very cold"


def classify_glide_regime(start_snow_f: float, finish_snow_f: float, start_air_f: float, finish_air_f: float, rh_pct: float, snow_type: str, melt_flag: bool) -> tuple[str, str]:
    avg_snow_f = float(np.nanmean([start_snow_f, finish_snow_f]))
    max_air_f = float(np.nanmax([start_air_f, finish_air_f]))
    avg_air_f = float(np.nanmean([start_air_f, finish_air_f]))
    rh = float(rh_pct) if pd.notna(rh_pct) else 65.0
    if melt_flag or avg_snow_f >= 31.3 or (max_air_f > 32.0 and max(start_snow_f, finish_snow_f) >= 31.0):
        return ("Wet suction / free water", "Surface is at or near melting with above-freezing air, so liquid water and suction dominate glide.")
    if avg_snow_f >= 26.0 or (snow_type in {"Coarse / transformed / artificial", "Injected / icy"} and avg_air_f >= 27.0) or (rh >= 80 and avg_snow_f >= 24.0):
        return ("Transitional mixed", "Near-freezing snow suggests mixed dry friction and emerging wet-suction behavior.")
    return ("Cold dry friction", "Snow remains below freezing enough that dry friction and crystal interaction dominate glide.")


def cache_status_text() -> str:
    vals = list(LAST_FETCH_META.values())
    if not vals:
        return "Unknown"
    if all(v == "live" for v in vals):
        return "Live NWS"
    if any(str(v).startswith("cached from") for v in vals):
        return "Cached fallback"
    return "; ".join(vals)


def confidence_label(run_dt: pd.Timestamp) -> str:
    horizon_hours = abs((run_dt - pd.Timestamp.now()).total_seconds()) / 3600.0
    cache_state = cache_status_text()
    if cache_state == "Live NWS" and horizon_hours <= 18:
        return "Higher"
    if horizon_hours <= 42:
        return "Moderate"
    return "Lower"


def hs_boundaries_f() -> list[float]:
    boundaries = set()
    for _name, low_c, high_c in HS_PRODUCTS:
        boundaries.add(low_c * 9.0 / 5.0 + 32.0)
        boundaries.add(high_c * 9.0 / 5.0 + 32.0)
    return sorted(boundaries)


def boundary_warning(weighted_f: float, melt_flag: bool) -> tuple[str, float]:
    if melt_flag:
        return ("Melt regime override active; liquid water matters more than strict snow temperature bands.", 0.0)
    boundaries = hs_boundaries_f()
    d = min(abs(weighted_f - b) for b in boundaries)
    if d <= 1.0:
        return (f"Very close to an HS boundary ({d:.1f}°F). Field testing or a backup pair is recommended.", d)
    if d <= 2.5:
        return (f"Near an HS boundary ({d:.1f}°F). Small forecast errors could move the wax call.", d)
    return (f"Comfortably inside the selected HS window ({d:.1f}°F from the nearest boundary).", d)


def uncertainty_band_f(confidence_text: str, boundary_dist_f: float, melt_flag: bool) -> float:
    base = 1.8 if confidence_text == "High" else 2.4 if confidence_text == "Medium" else 3.2
    if boundary_dist_f <= 1.0:
        base += 0.8
    elif boundary_dist_f <= 2.5:
        base += 0.4
    if melt_flag:
        base += 0.4
    return float(base)


def run_summary(model: pd.DataFrame, run_dt: pd.Timestamp, snow_mode: str, dirty: bool) -> dict:
    idx = int((model["time"] - run_dt).abs().idxmin())
    row = model.loc[idx]
    snow_type, snow_note, conf = infer_snow_type(model, run_dt, snow_mode)
    start_snow_f = float(row["snow_start_pred_f"])
    finish_snow_f = float(row["snow_finish_pred_f"])
    start_air_f = float(row["air_start_f"])
    finish_air_f = float(row["air_finish_f"])
    hs_name, hs_note, _weighted_c, hs_color, melt_flag = hs_call_from_conditions(start_snow_f, finish_snow_f, start_air_f, finish_air_f, snow_type)
    start_c = adjust_temp_for_snow_type(float(temp_to_c(start_snow_f)), snow_type)
    finish_c = adjust_temp_for_snow_type(float(temp_to_c(finish_snow_f)), snow_type)
    weighted_c = 0.45 * start_c + 0.55 * finish_c
    weighted_f = 0.45 * start_snow_f + 0.55 * finish_snow_f
    glide_regime, glide_note = classify_glide_regime(start_snow_f, finish_snow_f, start_air_f, finish_air_f, float(row["rh_pct"]) if pd.notna(row["rh_pct"]) else np.nan, snow_type, melt_flag)

    overlap_products = hs_candidates(weighted_c) if not melt_flag else []
    overlap_text = ""
    overlap_colors: list[str] = []
    split_box = False
    tie_note = "Single HS window."
    if melt_flag:
        primary = HS_PRODUCTS[-1]
        hs = f"{primary[0]} (melt trigger)"
        weighted_for_boundary = max(32.0, 0.45 * start_air_f + 0.55 * finish_air_f)
        primary_name = primary[0]
        primary_color = product_color(primary_name)
    else:
        if len(overlap_products) >= 2:
            split_box = True
            overlap_text = " / ".join([p[0] for p in overlap_products[:2]])
            overlap_colors = [product_color(p[0]) for p in overlap_products[:2]]
            primary, tie_note = choose_overlap_primary(overlap_products[:2], snow_type, glide_regime, 0.45 * start_air_f + 0.55 * finish_air_f, float(row["rh_pct"]) if pd.notna(row["rh_pct"]) else np.nan)
            primary_name = primary[0]
            primary_color = product_color(primary_name)
            hs = f"{primary_name} (primary)"
        else:
            primary = select_product_tuple(weighted_c, HS_PRODUCTS)
            primary_name = primary[0]
            primary_color = product_color(primary_name)
            hs = select_temp_product(weighted_c, HS_PRODUCTS)
        weighted_for_boundary = weighted_f

    tst = select_temp_product(0.45 * start_c + 0.55 * finish_c, TST_PRODUCTS)
    tsp = select_temp_product(0.45 * start_c + 0.55 * finish_c, TSP_PRODUCTS)
    if dirty:
        conf = max(0.55, conf - 0.10)
        snow_note += " Dirty / abrasive toggle nudged confidence downward."
    confidence = "High" if conf >= 0.78 else "Medium" if conf >= 0.58 else "Low"
    boundary_note, boundary_dist_f = boundary_warning(weighted_for_boundary, melt_flag)
    uncert_f = uncertainty_band_f(confidence, boundary_dist_f, melt_flag)
    chart_start_f = max(32.0, start_air_f) if hs_name == "HS10 Yellow" and melt_flag else start_snow_f
    energy = {
        "Solar": 0.45 * float(row.get("solar_wm2", np.nan)) + 0.55 * float(row.get("solar_wm2", np.nan)),
        "Sensible heat": 0.45 * float(row.get("sensible_start_wm2", np.nan)) + 0.55 * float(row.get("sensible_finish_wm2", np.nan)),
        "Clear-night cooling": -(0.45 * float(row.get("clear_night_start_wm2", np.nan)) + 0.55 * float(row.get("clear_night_finish_wm2", np.nan))),
        "Longwave": 0.45 * float(row.get("longwave_start_wm2", np.nan)) + 0.55 * float(row.get("longwave_finish_wm2", np.nan)),
        "Latent": 0.45 * float(row.get("latent_start_wm2", np.nan)) + 0.55 * float(row.get("latent_finish_wm2", np.nan)),
        "Ground conduction": 0.45 * float(row.get("ground_start_wm2", np.nan)) + 0.55 * float(row.get("ground_finish_wm2", np.nan)),
    }
    energy["Net"] = sum(v for v in energy.values() if pd.notna(v))
    chart_finish_f = max(32.0, finish_air_f) if hs_name == "HS10 Yellow" and melt_flag else finish_snow_f
    return {
        "model_time": row["time"],
        "snow_start_f": start_snow_f,
        "snow_finish_f": finish_snow_f,
        "air_start_f": start_air_f,
        "air_finish_f": finish_air_f,
        "deep_start_f": float(row["deep_snow_start_f"]),
        "deep_finish_f": float(row["deep_snow_finish_f"]),
        "air_range_f": format_range_f(start_air_f, finish_air_f),
        "snow_type": snow_type,
        "snow_type_note": snow_note,
        "snow_type_conf": conf,
        "glide_regime": glide_regime,
        "glide_note": glide_note,
        "hs": hs,
        "hs_name": primary_name,
        "hs_note": hs_note,
        "hs_overlap_text": overlap_text,
        "hs_overlap_split": split_box,
        "hs_overlap_colors": overlap_colors,
        "tie_note": tie_note,
        "tst": tst,
        "tsp": tsp,
        "card_color": primary_color,
        "confidence": confidence,
        "boundary_note": boundary_note,
        "boundary_distance_f": boundary_dist_f,
        "uncertainty_band_f": uncert_f,
        "melt_flag": melt_flag,
        "chart_start_f": chart_start_f,
        "chart_finish_f": chart_finish_f,
        "chart_mid_f": 0.45 * chart_start_f + 0.55 * chart_finish_f,
        "energy_contrib_wm2": energy,
    }


# ---------------------------------------------------------------------------
# Plotly chart builders (unchanged — return go.Figure objects)
# In Django: import plotly; json_str = plotly.io.to_json(fig)
# Then in template: <div id="chart"></div> + Plotly.newPlot('chart', JSON.parse(json_str))
# ---------------------------------------------------------------------------

def build_temperature_figure(df: pd.DataFrame, run1_dt: pd.Timestamp, run2_dt: pd.Timestamp) -> go.Figure:
    fig = go.Figure()
    styles = [
        ("snow_start_pred_f", "Start snow temp (°F)", "#14532d", None, 3.6),
        ("air_start_f", "Start air temp (°F)", "#22c55e", "dot", 2.0),
        ("snow_finish_pred_f", "Finish snow temp (°F)", "#b91c1c", None, 3.6),
        ("air_finish_f", "Finish air temp (°F)", "#f87171", "dot", 2.0),
    ]
    for col, label, color, dash, width in styles:
        fig.add_trace(go.Scatter(
            x=df["time"], y=df[col], mode="lines", name=label,
            line={"color": color, "width": width, **({"dash": dash} if dash else {})},
            hovertemplate="%{x|%a %b %d, %Y %I:%M %p}<br>" + label + ": %{y:.1f} °F<extra></extra>",
        ))
    for dt, label in [(run1_dt, "Run 1"), (run2_dt, "Run 2")]:
        fig.add_vline(x=dt, line_color="#111827", line_dash="dash", line_width=2, opacity=0.8)
        fig.add_annotation(x=dt, y=1.06, yref="paper", text=label, showarrow=False, bgcolor="rgba(255,255,255,0.0)", borderwidth=0, font={"size": 11, "color": "#111827"})
    fig.update_layout(title="Start and finish air / snow temperatures", hovermode="x unified", legend={"orientation": "h", "y": 1.02, "x": 0, "font": {"color": "#111827"}}, margin={"l": 60, "r": 60, "t": 78, "b": 82}, height=390, template="plotly_white", paper_bgcolor="#ffffff", plot_bgcolor="#ffffff", font={"color": "#111827"}, xaxis={"tickfont": {"color": "#111827"}, "title_font": {"color": "#111827"}}, yaxis={"tickfont": {"color": "#111827"}, "title_font": {"color": "#111827"}}, hoverlabel=dict(bgcolor="white", font=dict(color="#111827")))
    fig.update_xaxes(title_text="Date and time", tickformat="%a<br>%b %d %H:%M", hoverformat="%a %b %d, %Y %I:%M %p", showgrid=True, tickfont={"color": "#111827"}, title_font={"color": "#111827"})
    fig.update_yaxes(title_text="Temperature (°F)", showgrid=True, tickfont={"color": "#111827"}, title_font={"color": "#111827"})
    return fig


def build_meteorology_figure(df: pd.DataFrame, run1_dt: pd.Timestamp, run2_dt: pd.Timestamp) -> go.Figure:
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    left_series = [
        ("rh_pct", "Relative humidity (%)", "#2563eb"),
        ("sky_pct", "Sky cover (%)", "#64748b"),
    ]
    for col, label, color in left_series:
        fig.add_trace(go.Scatter(x=df["time"], y=df[col], mode="lines", name=label, line={"color": color, "width": 2.2}, hovertemplate="%{x|%a %b %d, %Y %I:%M %p}<br>" + label + ": %{y:.1f}<extra></extra>"), secondary_y=False)
    fig.add_trace(go.Scatter(x=df["time"], y=df["wind_start_mph"], mode="lines", name="Wind speed (mph)", line={"color": "#0f766e", "width": 3.0}, hovertemplate="%{x|%a %b %d, %Y %I:%M %p}<br>Wind speed: %{y:.1f} mph<extra></extra>"), secondary_y=True)
    for dt, label in [(run1_dt, "Run 1"), (run2_dt, "Run 2")]:
        fig.add_vline(x=dt, line_color="#111827", line_dash="dash", line_width=2, opacity=0.8)
        fig.add_annotation(x=dt, y=1.06, yref="paper", text=label, showarrow=False, bgcolor="rgba(255,255,255,0.0)", borderwidth=0, font={"size": 11, "color": "#111827"})
    fig.update_layout(title="Wind, humidity, and sky cover", hovermode="x unified", legend={"orientation": "h", "y": 1.02, "x": 0, "font": {"color": "#111827"}}, margin={"l": 60, "r": 60, "t": 78, "b": 82}, height=390, template="plotly_white", paper_bgcolor="#ffffff", plot_bgcolor="#ffffff", font={"color": "#111827"}, xaxis={"tickfont": {"color": "#111827"}, "title_font": {"color": "#111827"}}, yaxis={"tickfont": {"color": "#111827"}, "title_font": {"color": "#111827"}}, yaxis2={"tickfont": {"color": "#111827"}, "title_font": {"color": "#111827"}}, hoverlabel=dict(bgcolor="white", font=dict(color="#111827")))
    fig.update_xaxes(title_text="Date and time", tickformat="%a<br>%b %d %H:%M", hoverformat="%a %b %d, %Y %I:%M %p", showgrid=True, tickfont={"color": "#111827"}, title_font={"color": "#111827"})
    fig.update_yaxes(title_text="Humidity / sky cover (%)", showgrid=True, secondary_y=False, tickfont={"color": "#111827"}, title_font={"color": "#111827"})
    fig.update_yaxes(title_text="Wind speed (mph)", showgrid=False, secondary_y=True, tickfont={"color": "#111827"}, title_font={"color": "#111827"})
    return fig


def build_time_series_figure(df: pd.DataFrame, series: list[tuple[str, str]], title: str, yaxis_title: str, run1_dt: pd.Timestamp, run2_dt: pd.Timestamp) -> go.Figure:
    fig = go.Figure()
    palette = ["#1d4ed8", "#7c3aed", "#0f766e", "#f59e0b", "#dc2626"]
    for i, (col, label) in enumerate(series):
        fig.add_trace(go.Scatter(x=df["time"], y=df[col], mode="lines", name=label, line={"width": 2.4, "color": palette[i % len(palette)]}, hovertemplate="%{x|%a %b %d, %Y %I:%M %p}<br>" + label + ": %{y:.1f}<extra></extra>"))
    for dt, label in [(run1_dt, "Run 1"), (run2_dt, "Run 2")]:
        fig.add_vline(x=dt, line_color="#111827", line_dash="dash", line_width=2, opacity=0.8)
        fig.add_annotation(x=dt, y=1.06, yref="paper", text=label, showarrow=False, bgcolor="rgba(255,255,255,0.0)", borderwidth=0, font={"size": 11, "color": "#111827"})
    fig.update_layout(title=title, hovermode="x unified", legend={"orientation": "h", "y": 1.02, "x": 0, "font": {"color": "#111827"}}, margin={"l": 60, "r": 60, "t": 78, "b": 82}, height=390, template="plotly_white", paper_bgcolor="#ffffff", plot_bgcolor="#ffffff", font={"color": "#111827"}, xaxis={"tickfont": {"color": "#111827"}, "title_font": {"color": "#111827"}}, yaxis={"tickfont": {"color": "#111827"}, "title_font": {"color": "#111827"}}, hoverlabel=dict(bgcolor="white", font=dict(color="#111827")))
    fig.update_xaxes(title_text="Date and time", tickformat="%a<br>%b %d %H:%M", hoverformat="%a %b %d, %Y %I:%M %p", showgrid=True, tickfont={"color": "#111827"}, title_font={"color": "#111827"})
    fig.update_yaxes(title_text=yaxis_title, showgrid=True, tickfont={"color": "#111827"}, title_font={"color": "#111827"})
    return fig


def build_visual_wax_chart(run1: dict, run2: dict) -> go.Figure:
    fig = go.Figure()
    families = [("HS", HS_PRODUCTS, 3.0), ("TS Turbo", TST_PRODUCTS, 2.0), ("TSP", TSP_PRODUCTS, 1.0)]
    offsets = np.linspace(-0.28, 0.28, 5)
    height = 0.12
    for family, products, center in families:
        for offset, (name, low, high) in zip(offsets, products):
            y = center + float(offset)
            color = product_color(name)
            x0 = low * 9.0 / 5.0 + 32.0
            x1 = high * 9.0 / 5.0 + 32.0
            fig.add_shape(type="rect", x0=x0, x1=x1, y0=y - height, y1=y + height, line={"width": 1, "color": color}, fillcolor=hex_to_rgba(color, 0.88))
            fig.add_annotation(x=(x0 + x1) / 2.0, y=y, text=name.split()[0], showarrow=False, font={"size": 10, "color": text_color_for_wax(color)})
    markers = [
        (run1["chart_start_f"], 3.52, "Run 1 Start", "diamond", run1["melt_flag"]),
        (run1["chart_finish_f"], 0.48, "Run 1 Finish", "diamond-open", run1["melt_flag"]),
        (run2["chart_start_f"], 3.72, "Run 2 Start", "circle", run2["melt_flag"]),
        (run2["chart_finish_f"], 0.28, "Run 2 Finish", "circle-open", run2["melt_flag"]),
    ]
    for x, y, label, symbol, melt_flag in markers:
        metric_label = "Air-temp melt proxy" if melt_flag else "Predicted snow temp"
        fig.add_trace(go.Scatter(x=[x], y=[y], mode="markers+text", text=[label], textposition="top center" if "Start" in label else "bottom center", textfont={"size": 11, "color": "#111827"}, marker={"size": 14, "color": "#111827", "symbol": symbol, "line": {"width": 1, "color": "#111827"}}, name=label, hovertemplate=f"{label}<br>{metric_label}: %{{x:.1f}} °F<extra></extra>", showlegend=False, cliponaxis=False))
        fig.add_vline(x=x, line_color="#111827", line_dash="dot", line_width=1.5, opacity=0.65)
    fig.update_layout(title="Visual wax decision chart", template="plotly_white", height=390, margin={"l": 60, "r": 60, "t": 70, "b": 80}, hoverlabel=dict(bgcolor="white", font={"color": "#111827"}), paper_bgcolor="#ffffff", plot_bgcolor="#ffffff", font={"color": "#111827"}, xaxis_title="Predicted temperature for wax choice (°F)")
    fig.update_xaxes(range=[0, 50], dtick=4, showgrid=True, zeroline=True, tickfont={"color": "#111827"}, title_font={"color": "#111827"})
    fig.update_yaxes(range=[0.0, 4.02], tickmode="array", tickvals=[1.0, 2.0, 3.0], ticktext=["TSP", "TS Turbo", "HS"], showgrid=False, tickfont={"color": "#111827"}, title_font={"color": "#111827"})
    return fig


# ---------------------------------------------------------------------------
# CSV download helper (unchanged)
# ---------------------------------------------------------------------------

def make_download_csv(df: pd.DataFrame) -> bytes:
    keep = ["time", "air_upper_f", "air_lower_f", "lapse_f_per_1000ft", "air_start_f", "air_finish_f", "snow_start_pred_f", "snow_finish_pred_f", "deep_snow_start_f", "deep_snow_finish_f", "sky_upper_pct", "sky_lower_pct", "sky_pct", "sky_source", "wind_start_mph", "rh_pct", "solar_elevation_deg", "solar_azimuth_deg", "poa_global_wm2", "longwave_start_fph", "longwave_finish_fph", "latent_start_fph", "latent_finish_fph"]
    return df[keep].to_csv(index=False).encode("utf-8")


# ---------------------------------------------------------------------------
# HTML card renderers
# These replace the st.markdown() calls in the original.
# Each function returns an HTML string — pass to Django template with |safe.
# ---------------------------------------------------------------------------

def card_html(title: str, value: str, subtitle: str = "") -> str:
    return f'<div class="wax-mini-card"><div class="wax-mini-title">{html.escape(title)}</div><div class="wax-mini-value">{html.escape(value)}</div><div class="wax-mini-subtitle">{html.escape(subtitle)}</div></div>'


def render_run_card_html(label: str, run: dict) -> str:
    """Returns the full HTML block for a single run card. Use with |safe in Django template."""
    ts = pd.Timestamp(run["model_time"]).strftime("%a %b %d, %Y %I:%M %p")
    accent = str(run["card_color"])
    panel_bg = hex_to_rgba(accent, 0.10)
    pill_text = text_color_for_wax(accent)
    if run.get("hs_overlap_split") and len(run.get("hs_overlap_colors", [])) >= 2:
        c1, c2 = run["hs_overlap_colors"][:2]
        split_bg = f"linear-gradient(90deg,{c1} 0%, {c1} 50%, {c2} 50%, {c2} 100%)"
        split_label = run["hs_overlap_text"]
    else:
        split_bg = accent
        split_label = run["hs_name"]
    return f"""
    <div class="wax-run-card" style="border-color:{html.escape(accent)}; background:linear-gradient(180deg,{panel_bg} 0%, rgba(255,255,255,0.98) 42%);">
      <div class="wax-run-header"><div><div class="wax-run-eyebrow">{html.escape(label)}</div><div class="wax-run-time">{html.escape(ts)}</div></div><div class="wax-band-pill" style="background:{html.escape(accent)}; color:{pill_text};">{html.escape(str(run['hs_name']))}</div></div>
      <div class="wax-grid">
        {card_html('Start Snow Temp', f"{run['snow_start_f']:.1f} °F", f"{temp_to_c(run['snow_start_f']):.1f} °C")}
        {card_html('Finish Snow Temp', f"{run['snow_finish_f']:.1f} °F", f"{temp_to_c(run['snow_finish_f']):.1f} °C")}
        {card_html('Air Temp Range', str(run['air_range_f']), 'Start to finish on course')}
        {card_html('Snow type', str(run['snow_type']), f"conf {run['snow_type_conf']:.2f}")}
        {card_html('Glide regime', str(run['glide_regime']), str(run['glide_note']))}
        <div class="wax-mini-card" style="padding:0;overflow:hidden;">
          <div class="wax-split-top" style="background:{split_bg}; color:{'#111827' if run.get('hs_overlap_split') else text_color_for_wax(accent)};">Overlap / blend zone: {html.escape(split_label if split_label else run['hs_name'])}</div>
          <div class="wax-split-bottom">Primary HS choice: <strong>{html.escape(str(run['hs']))}</strong><br><span>{html.escape(str(run['tie_note']))}</span></div>
        </div>
        {card_html('TS Turbo', str(run['tst']), 'Optional race top coat')}
        {card_html('TSP', str(run['tsp']), 'Optional powder top coat')}
        {card_html('Melt check', 'HS10 trigger active' if run['melt_flag'] else 'No melt trigger', 'Uses air temp when snow is at 32°F')}
        {card_html('Deep snow temp', f"{run['deep_start_f']:.1f} → {run['deep_finish_f']:.1f} °F", 'Auto-estimated from season + recent weather')}
        {card_html('Confidence', str(run['confidence']), str(run['snow_type_note']))}
        {card_html('Boundary warning', str(run['boundary_note']), f"±{run['uncertainty_band_f']:.1f} °F uncertainty band")}
      </div>
    </div>
    """


def render_summary_strip_html(run1: dict, run2: dict, cache_state: str) -> str:
    """Returns the summary strip HTML. Use with |safe in Django template."""
    blocks = []
    for label, run in [("Run 1 wax call", run1), ("Run 2 wax call", run2)]:
        color = str(run["card_color"])
        text_color = text_color_for_wax(color)
        if run.get("hs_overlap_split") and len(run.get("hs_overlap_colors", [])) >= 2:
            c1, c2 = run["hs_overlap_colors"][:2]
            bg = f"linear-gradient(90deg,{c1} 0%, {c1} 50%, {c2} 50%, {c2} 100%)"
            main = run["hs_overlap_text"]
            sub = f"primary {run['hs_name']} · {run['tie_note']}"
            text_color = "#111827"
        else:
            bg = f"linear-gradient(180deg,{hex_to_rgba(color, 0.92)} 0%, {hex_to_rgba(color, 0.80)} 100%)"
            main = run["hs_name"]
            sub = f"snow {run['snow_start_f']:.1f} → {run['snow_finish_f']:.1f} °F · air {run['air_start_f']:.1f} → {run['air_finish_f']:.1f} °F · {run['confidence']} confidence"
        blocks.append(
            f'<div class="summary-card" style="background:{html.escape(bg)}; border-color:{html.escape(color)}; color:{text_color};">'
            f'<div class="summary-label" style="color:{text_color};">{html.escape(label)}</div>'
            f'<div class="summary-main" style="color:{text_color};">{html.escape(str(main))}</div>'
            f'<div class="summary-sub" style="color:{text_color}; opacity:0.96;">{html.escape(sub)}</div>'
            f'</div>'
        )
    return '<div class="summary-strip">' + ''.join(blocks) + '</div>'


def render_energy_panel_html(title: str, run: dict) -> str:
    """Returns the energy panel HTML including an embedded Plotly chart as JSON.
    In your Django template:
        <div id="energy-run1"></div>
        <script>Plotly.newPlot('energy-run1', JSON.parse('{{ energy_run1_json|escapejs }}'));</script>
    """
    contrib = run.get("energy_contrib_wm2", {})
    if not contrib:
        return f"<p><strong>{html.escape(title)} energy-contribution estimate</strong><br>Energy contributions unavailable.</p>"
    order = ["Solar", "Sensible heat", "Clear-night cooling", "Longwave", "Latent", "Ground conduction", "Net"]
    labels, values, colors = [], [], []
    for name in order:
        val = contrib.get(name)
        if val is None or (isinstance(val, float) and math.isnan(val)):
            continue
        labels.append(name)
        values.append(float(val))
        colors.append("#16a34a" if float(val) >= 0 else "#dc2626")
    fig = go.Figure(go.Bar(
        x=values, y=labels, orientation="h",
        marker={"color": colors, "line": {"color": "#111827", "width": 0.6}},
        text=[f"{v:+.0f} W/m²" for v in values],
        textposition="outside", cliponaxis=False,
        hovertemplate="%{y}: %{x:+.0f} W/m²<extra></extra>",
        showlegend=False,
    ))
    fig.update_layout(
        template="plotly_white", paper_bgcolor="#ffffff", plot_bgcolor="#ffffff",
        font={"color": "#111827"},
        xaxis={"title": "Contribution (W/m²)", "tickfont": {"color": "#111827"}, "title_font": {"color": "#111827"}, "zeroline": True, "zerolinecolor": "#111827"},
        yaxis={"tickfont": {"color": "#111827"}, "title_font": {"color": "#111827"}, "categoryorder": "array", "categoryarray": labels[::-1]},
        margin={"l": 10, "r": 40, "t": 10, "b": 20}, height=300,
    )
    import plotly
    chart_json = plotly.io.to_json(fig)
    rows = [{"Energy source": n, "Contribution": f"{contrib[n]:+.0f} W/m²"} for n in order if n in contrib and pd.notna(contrib[n])]
    table_rows = "".join(f"<tr><td>{html.escape(r['Energy source'])}</td><td>{html.escape(r['Contribution'])}</td></tr>" for r in rows)
    chart_id = f"energy-{title.lower().replace(' ', '-')}"
    return f"""
    <p><strong>{html.escape(title)} energy-contribution estimate</strong></p>
    <div id="{chart_id}"></div>
    <script>Plotly.newPlot('{chart_id}', JSON.parse('{chart_json.replace("'", "\\'")}'));</script>
    <table><thead><tr><th>Energy source</th><th>Contribution</th></tr></thead><tbody>{table_rows}</tbody></table>
    <small>Approximate equivalent surface-energy contributions for the active snow layer used by the model. Positive warms the surface; negative cools it.</small>
    """