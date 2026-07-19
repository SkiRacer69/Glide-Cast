from __future__ import annotations

import html
import json
import math
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import pvlib
import requests
import streamlit as st
from pvlib.location import Location
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

st.set_page_config(page_title="glideCast v9", layout="wide")

st.markdown(
    """
    <style>
    .stApp, [data-testid="stAppViewContainer"], [data-testid="stHeader"], [data-testid="stToolbar"], .main .block-container { background: #ffffff !important; color: #111827 !important; }
    [data-testid="stSidebar"], section[data-testid="stSidebar"] > div { background: #f8fafc !important; }
    [data-testid="stSidebar"] * { color: #111827 !important; }
    h1, h2, h3, h4, h5, h6, p, div, span, label, small { color: #111827 !important; }
    .stMarkdown, .stText, .stCaption { color: #111827 !important; }

    /* Core widgets */
    div[data-baseweb="select"] > div,
    div[data-baseweb="base-input"] > div,
    div[data-baseweb="input"] > div,
    .stDateInput > div > div,
    .stTimeInput > div > div,
    .stSelectbox > div > div,
    .stNumberInput > div > div,
    [data-testid="stFileUploaderDropzone"],
    [data-testid="stFileUploaderDropzone"] * {
        background: #ffffff !important;
        color: #111827 !important;
        border-color: #d1d5db !important;
        -webkit-text-fill-color: #111827 !important;
    }
    div[data-baseweb="select"] *,
    div[data-baseweb="base-input"] *,
    div[data-baseweb="input"] *,
    .stDateInput *,
    .stTimeInput *,
    .stSelectbox *,
    .stNumberInput * {
        color: #111827 !important;
        -webkit-text-fill-color: #111827 !important;
    }
    div[data-baseweb="select"] input,
    div[data-baseweb="select"] span,
    div[data-baseweb="base-input"] input,
    .stDateInput input,
    .stTimeInput input,
    .stNumberInput input {
        color: #111827 !important;
        -webkit-text-fill-color: #111827 !important;
        background: #ffffff !important;
    }

    /* Dropdowns / popovers / calendars */
    div[role="listbox"], ul[role="listbox"],
    div[role="option"], li[role="option"],
    [data-baseweb="menu"], [data-baseweb="menu"] *,
    [data-baseweb="popover"], [data-baseweb="popover"] *,
    .stDateInput [role="dialog"], .stDateInput [role="dialog"] *,
    .stTimeInput [role="dialog"], .stTimeInput [role="dialog"] *,
    div[data-baseweb="calendar"], div[data-baseweb="calendar"] *,
    [data-baseweb="calendar"] button,
    [data-baseweb="calendar"] div,
    [data-baseweb="calendar"] span {
        background: #ffffff !important;
        color: #111827 !important;
        -webkit-text-fill-color: #111827 !important;
        border-color: #d1d5db !important;
    }
    div[role="option"]:hover, li[role="option"]:hover,
    [data-baseweb="calendar"] button:hover {
        background: #f3f4f6 !important;
        color: #111827 !important;
    }

    /* Number input +/- buttons */
    .stNumberInput button, .stDateInput button, .stTimeInput button {
        background: #ffffff !important;
        color: #111827 !important;
        border: 1px solid #d1d5db !important;
    }
    .stNumberInput button *, .stDateInput button *, .stTimeInput button * {
        color: #111827 !important;
        fill: #111827 !important;
    }

    /* Checkbox styling */
    div[data-baseweb="checkbox"] > label,
    div[data-baseweb="checkbox"] span,
    div[data-baseweb="checkbox"] svg {
        color: #111827 !important;
        fill: #111827 !important;
    }
    div[data-baseweb="checkbox"] div[aria-checked] {
        background: #ffffff !important;
        border: 1px solid #111827 !important;
    }

    /* Plotly chart containers */
    [data-testid="stPlotlyChart"] > div,
    [data-testid="stPlotlyChart"] .js-plotly-plot,
    [data-testid="stPlotlyChart"] .plot-container {
        background: #ffffff !important;
    }

    /* Tables / dataframes / expanders */
    [data-testid="stDataFrame"], [data-testid="stDataFrame"] *,
    .stTable, .stTable *,
    [data-testid="stExpander"], [data-testid="stExpander"] * {
        color: #111827 !important;
    }
    [data-testid="stDataFrame"] {
        background: #ffffff !important;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


USER_AGENT = "glideCast/2.0 (educational-use; local launcher)"
HEADERS = {"User-Agent": USER_AGENT, "Accept": "application/geo+json"}
LOCAL_TZ = "America/New_York"
SUPPORT_DIR = Path(os.path.expanduser("~/Library/Application Support/GlideCastV9"))
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

ACTIVE_LAYER_WM2_PER_FPH = 4.9  # Approximate conversion using a ~5 cm, 300 kg m^-3 active snow layer.


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
        or "f59e0b" in c
        or "facc15" in c
        or "eab308" in c
        or "1bb3c8" in c
    ):
        return "#111827"
    return "#ffffff"


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
    emiss_air = np.clip(
        0.70 + 0.00025 * rh * saturation_vapor_pressure_hpa((air_f - 32.0) * 5.0 / 9.0) * 100.0, 0.72, 0.99
    )
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


def clear_night_cooling_term_f(
    rh_pct: float, cloud_frac: float, wind_mph: float, solar_elev_deg: float, coeff: float
) -> float:
    """Extra nocturnal radiative cooling term for clear, dry, light-wind nights.

    Returns a cooling tendency in model units of °F per hour. The term decays as
    clouds, humidity, or wind increase, and vanishes in daylight.
    """
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


@st.cache_data(ttl=1800, show_spinner=False)
def get_hourly_forecast(lat: float, lon: float) -> pd.DataFrame:
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
    a = upper.rename(
        columns={
            "air_temp_f": "air_upper_f",
            "air_temp_c": "air_upper_c",
            "wind_mph": "wind_upper_mph",
            "rh_pct": "rh_upper_pct",
            "sky_cover_pct": "sky_upper_pct",
            "sky_cover_source": "sky_upper_source",
            "precip_prob_pct": "pop_upper_pct",
            "short_forecast": "forecast_upper",
            "is_day": "is_day_upper",
        }
    )
    b = lower.rename(
        columns={
            "air_temp_f": "air_lower_f",
            "air_temp_c": "air_lower_c",
            "wind_mph": "wind_lower_mph",
            "rh_pct": "rh_lower_pct",
            "sky_cover_pct": "sky_lower_pct",
            "sky_cover_source": "sky_lower_source",
            "precip_prob_pct": "pop_lower_pct",
            "short_forecast": "forecast_lower",
            "is_day": "is_day_lower",
        }
    )
    return pd.merge(a, b, on="time", how="inner").sort_values("time").reset_index(drop=True)


@st.cache_data(ttl=1800, show_spinner=False)
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
    dni = clearsky["dni"].to_numpy() * np.clip(trans**1.3, 0.02, 1.0)
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
    out = pd.DataFrame(
        {
            "time": times.tz_localize(None),
            "solar_zenith_deg": solpos["apparent_zenith"].to_numpy(),
            "solar_elevation_deg": solpos["elevation"].to_numpy(),
            "solar_azimuth_deg": solpos["azimuth"].to_numpy(),
            "poa_global_wm2": np.clip(poa["poa_global"].to_numpy(), 0.0, None),
        }
    )
    out["solar_norm"] = (out["poa_global_wm2"] / 1000.0).clip(0.0, 1.2)
    return out


def seasonal_deep_snow_baseline_f(day_of_year: int) -> float:
    # Simple seasonal baseline for New England race snowpacks: coldest in late January, warmest near spring melt.
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


def prepare_venue(
    df: pd.DataFrame, venue: dict, start_ft: float, finish_ft: float, params: ModelParams, race_date: pd.Timestamp
) -> pd.DataFrame:
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
    both_grid = out["sky_upper_source"].fillna("").str.contains("skyCover") & out["sky_lower_source"].fillna("").str.contains(
        "skyCover"
    )
    one_grid = out[["sky_upper_pct", "sky_lower_pct"]].notna().any(axis=1)
    out["sky_source"] = np.where(
        both_grid, "NWS grid sky cover (both points)", np.where(one_grid, "NWS grid sky cover (one point)", "Fallback default")
    )
    out["rh_pct"] = out[["rh_upper_pct", "rh_lower_pct"]].mean(axis=1).fillna(70.0)
    out["cloud_frac"] = (out["sky_pct"] / 100.0).clip(0.0, 1.0)

    solar = solar_geometry_and_irradiance(
        tuple(out["time"]),
        venue["lat"],
        venue["lon"],
        venue["elev_ft"] * 0.3048,
        params.slope_deg,
        params.aspect_deg,
        tuple(out["cloud_frac"]),
        params.cloud_attenuation,
        params.diffuse_floor_frac,
        params.albedo,
    )
    out = out.merge(solar, on="time", how="left")
    out["solar_norm"] = out["solar_norm"].fillna(0.0)
    out["poa_global_wm2"] = out["poa_global_wm2"].fillna(0.0)

    out["clear_night_start_fph"] = [
        clear_night_cooling_term_f(rh, cf, w, se, params.clear_night_coeff)
        for rh, cf, w, se in zip(out["rh_pct"], out["cloud_frac"], out["wind_start_mph"], out["solar_elevation_deg"])
    ]
    out["clear_night_finish_fph"] = [
        clear_night_cooling_term_f(rh, cf, w, se, params.clear_night_coeff)
        for rh, cf, w, se in zip(out["rh_pct"], out["cloud_frac"], out["wind_finish_mph"], out["solar_elevation_deg"])
    ]

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
        lw_start = longwave_exchange_term_f(
            row_prev["air_start_f"], prev_start, row_prev["rh_pct"], row_prev["cloud_frac"], params.longwave_coeff
        )
        lw_finish = longwave_exchange_term_f(
            row_prev["air_finish_f"], prev_finish, row_prev["rh_pct"], row_prev["cloud_frac"], params.longwave_coeff
        )
        latent_start = latent_exchange_term_f(
            row_prev["air_start_f"], prev_start, row_prev["rh_pct"], row_prev["wind_start_mph"], params.latent_coeff
        )
        latent_finish = latent_exchange_term_f(
            row_prev["air_finish_f"], prev_finish, row_prev["rh_pct"], row_prev["wind_finish_mph"], params.latent_coeff
        )
        clear_start = row_prev["clear_night_start_fph"]
        sensible_start = params.wind_coeff * (1 + 0.08 * row_prev["wind_start_mph"]) * (row_prev["air_start_f"] - prev_start)
        ground_start = params.restore_coeff * (row_prev["deep_snow_start_f"] - prev_start)
        solar_term = params.solar_coeff * row_prev["solar_norm"]
        next_start = prev_start + (sensible_start + solar_term - clear_start + lw_start + latent_start + ground_start)
        clear_finish = row_prev["clear_night_finish_fph"]
        sensible_finish = params.wind_coeff * (1 + 0.08 * row_prev["wind_finish_mph"]) * (
            row_prev["air_finish_f"] - prev_finish
        )
        ground_finish = params.restore_coeff * (row_prev["deep_snow_finish_f"] - prev_finish)
        next_finish = prev_finish + (sensible_finish + solar_term - clear_finish + lw_finish + latent_finish + ground_finish)
        snow_start.append(min(next_start, 32.0))
        snow_finish.append(min(next_finish, 32.0))
    out["snow_start_pred_f"] = snow_start
    out["snow_finish_pred_f"] = snow_finish
    out["snow_start_pred_c"] = temp_to_c(out["snow_start_pred_f"])
    out["snow_finish_pred_c"] = temp_to_c(out["snow_finish_pred_f"])
    out["solar_fph"] = params.solar_coeff * out["solar_norm"]
    out["sensible_start_fph"] = params.wind_coeff * (1 + 0.08 * out["wind_start_mph"]) * (
        out["air_start_f"] - out["snow_start_pred_f"]
    )
    out["sensible_finish_fph"] = params.wind_coeff * (1 + 0.08 * out["wind_finish_mph"]) * (
        out["air_finish_f"] - out["snow_finish_pred_f"]
    )
    out["ground_start_fph"] = params.restore_coeff * (out["deep_snow_start_f"] - out["snow_start_pred_f"])
    out["ground_finish_fph"] = params.restore_coeff * (out["deep_snow_finish_f"] - out["snow_finish_pred_f"])
    out["longwave_start_fph"] = [
        longwave_exchange_term_f(a, s, rh, cf, params.longwave_coeff)
        for a, s, rh, cf in zip(out["air_start_f"], out["snow_start_pred_f"], out["rh_pct"], out["cloud_frac"])
    ]
    out["longwave_finish_fph"] = [
        longwave_exchange_term_f(a, s, rh, cf, params.longwave_coeff)
        for a, s, rh, cf in zip(out["air_finish_f"], out["snow_finish_pred_f"], out["rh_pct"], out["cloud_frac"])
    ]
    out["latent_start_fph"] = [
        latent_exchange_term_f(a, s, rh, w, params.latent_coeff)
        for a, s, rh, w in zip(out["air_start_f"], out["snow_start_pred_f"], out["rh_pct"], out["wind_start_mph"])
    ]
    out["latent_finish_fph"] = [
        latent_exchange_term_f(a, s, rh, w, params.latent_coeff)
        for a, s, rh, w in zip(out["air_finish_f"], out["snow_finish_pred_f"], out["rh_pct"], out["wind_finish_mph"])
    ]
    out["net_start_fph"] = (
        out["solar_fph"]
        + out["sensible_start_fph"]
        - out["clear_night_start_fph"]
        + out["longwave_start_fph"]
        + out["latent_start_fph"]
        + out["ground_start_fph"]
    )
    out["net_finish_fph"] = (
        out["solar_fph"]
        + out["sensible_finish_fph"]
        - out["clear_night_finish_fph"]
        + out["longwave_finish_fph"]
        + out["latent_finish_fph"]
        + out["ground_finish_fph"]
    )
    for col in [
        "solar_fph",
        "sensible_start_fph",
        "sensible_finish_fph",
        "clear_night_start_fph",
        "clear_night_finish_fph",
        "longwave_start_fph",
        "longwave_finish_fph",
        "latent_start_fph",
        "latent_finish_fph",
        "ground_start_fph",
        "ground_finish_fph",
        "net_start_fph",
        "net_finish_fph",
    ]:
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


def choose_overlap_primary(
    candidates: list[tuple[str, float, float]], snow_type: str, glide_regime: str, avg_air_f: float, rh_pct: float
) -> tuple[tuple[str, float, float], str]:
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


def adjust_temp_for_snow_type(temp_c: float, snow_type: str) -> float:
    offsets = {
        "Fine / new snow": 0.5,
        "Coarse / transformed / artificial": 0.0,
        "Aggressive cold / manmade": -0.7,
        "Injected / icy": -1.2,
    }
    return temp_c + offsets.get(snow_type, 0.0)


def hs_call_from_conditions(
    start_snow_f: float, finish_snow_f: float, start_air_f: float, finish_air_f: float, snow_type: str
) -> tuple[str, str, float, str, bool]:
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
    lookback["mixed_word"] = lookback["combined_text"].apply(
        lambda t: _forecast_text_has(t, ["sleet", "wintry mix", "mix", "rain/snow", "rain and snow"])
    )
    lookback["rain_word"] = lookback["combined_text"].apply(lambda t: _forecast_text_has(t, ["rain", "drizzle", "showers", "freezing rain"]))

    snow_event = lookback[
        (lookback["snow_word"]) & (~lookback["mixed_word"]) & (lookback["max_pop_pct"] >= 35) & (lookback["mean_air_f"] <= 33.5)
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


def classify_glide_regime(
    start_snow_f: float,
    finish_snow_f: float,
    start_air_f: float,
    finish_air_f: float,
    rh_pct: float,
    snow_type: str,
    melt_flag: bool,
) -> tuple[str, str]:
    avg_snow_f = float(np.nanmean([start_snow_f, finish_snow_f]))
    max_air_f = float(np.nanmax([start_air_f, finish_air_f]))
    avg_air_f = float(np.nanmean([start_air_f, finish_air_f]))
    rh = float(rh_pct) if pd.notna(rh_pct) else 65.0
    if melt_flag or avg_snow_f >= 31.3 or (max_air_f > 32.0 and max(start_snow_f, finish_snow_f) >= 31.0):
        return ("Wet suction / free water", "Surface is at or near melting with above-freezing air, so liquid water and suction dominate glide.")
    if avg_snow_f >= 26.0 or (snow_type in {"Coarse / transformed / artificial", "Injected / icy"} and avg_air_f >= 27.0) or (
        rh >= 80 and avg_snow_f >= 24.0
    ):
        return ("Transitional mixed", "Near-freezing snow suggests mixed dry friction and emerging wet-suction behavior.")
    return ("Cold dry friction", "Snow remains below freezing enough that dry friction and crystal interaction dominate glide.")


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


def run_summary(model: pd.DataFrame, run_dt: pd.Timestamp, snow_mode: str, dirty: bool) -> dict[str, str | float | pd.Timestamp]:
    idx = int((model["time"] - run_dt).abs().idxmin())
    row = model.loc[idx]
    snow_type, snow_note, conf = infer_snow_type(model, run_dt, snow_mode)
    start_snow_f = float(row["snow_start_pred_f"])
    finish_snow_f = float(row["snow_finish_pred_f"])
    start_air_f = float(row["air_start_f"])
    finish_air_f = float(row["air_finish_f"])
    hs_name, hs_note, _weighted_c, hs_color, melt_flag = hs_call_from_conditions(
        start_snow_f, finish_snow_f, start_air_f, finish_air_f, snow_type
    )
    start_c = adjust_temp_for_snow_type(float(temp_to_c(start_snow_f)), snow_type)
    finish_c = adjust_temp_for_snow_type(float(temp_to_c(finish_snow_f)), snow_type)
    weighted_c = 0.45 * start_c + 0.55 * finish_c
    weighted_f = 0.45 * start_snow_f + 0.55 * finish_snow_f
    glide_regime, glide_note = classify_glide_regime(
        start_snow_f,
        finish_snow_f,
        start_air_f,
        finish_air_f,
        float(row["rh_pct"]) if pd.notna(row["rh_pct"]) else np.nan,
        snow_type,
        melt_flag,
    )

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
            primary, tie_note = choose_overlap_primary(
                overlap_products[:2],
                snow_type,
                glide_regime,
                0.45 * start_air_f + 0.55 * finish_air_f,
                float(row["rh_pct"]) if pd.notna(row["rh_pct"]) else np.nan,
            )
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

