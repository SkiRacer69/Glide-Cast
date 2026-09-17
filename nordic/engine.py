"""Nordic ski wax recommendation engine — Classic (grip + glide) and Skate (glide)."""
from __future__ import annotations

import math
from datetime import datetime, timedelta
from typing import Any

import sys
import types

import pandas as pd
import requests

if "streamlit" not in sys.modules:
    class _Noop:
        def __call__(self, *a, **kw):
            if a and callable(a[0]):
                return a[0]
            return self
        def __getattr__(self, name):
            return _Noop()

    class _StubModule(types.ModuleType):
        def __getattr__(self, name):
            return _Noop()

    sys.modules["streamlit"] = _StubModule("streamlit")

# Import the exact same energy-balance functions and solar model from the Alpine engine.
# Nordic uses the identical formula — GPX provides aspect_deg and slope_deg per segment
# instead of the fixed per-venue values the Alpine calculator uses.
from calculator.engine import (
    clear_night_cooling_term_f,
    latent_exchange_term_f,
    longwave_exchange_term_f,
    solar_geometry_and_irradiance,
)

# Same default coefficients as Alpine calculator (calculator/forms.py defaults)
_WIND_COEFF        = 0.12
_SOLAR_COEFF       = 2.0
_CLEAR_NIGHT_COEFF = 1.4
_LONGWAVE_COEFF    = -0.25
_LATENT_COEFF      = 0.06
_CLOUD_ATTENUATION = 0.75
_DIFFUSE_FLOOR_FRAC = 0.35
_ALBEDO            = 0.75

# ---------------------------------------------------------------------------
# Nordic FIS World Cup + major XC venues
# ---------------------------------------------------------------------------
VENUES: dict[str, dict] = {
    # ---- Scandinavia -------------------------------------------------------
    "Falun": {
        "lat": 60.603, "lon": 15.625, "elev_ft": 738, "country": "Sweden",
        "flag": "🇸🇪", "typical_snow": "transformed",
        "points": {
            "weather": {"lat": 60.603, "lon": 15.625},
        },
    },
    "Lahti": {
        "lat": 60.987, "lon": 25.655, "elev_ft": 394, "country": "Finland",
        "flag": "🇫🇮", "typical_snow": "transformed",
        "points": {"weather": {"lat": 60.987, "lon": 25.655}},
    },
    "Oslo/Holmenkollen": {
        "lat": 59.964, "lon": 10.669, "elev_ft": 1312, "country": "Norway",
        "flag": "🇳🇴", "typical_snow": "transformed",
        "points": {"weather": {"lat": 59.964, "lon": 10.669}},
    },
    "Trondheim/Granåsen": {
        "lat": 63.424, "lon": 10.337, "elev_ft": 591, "country": "Norway",
        "flag": "🇳🇴", "typical_snow": "packed",
        "points": {"weather": {"lat": 63.424, "lon": 10.337}},
    },
    "Beitostølen": {
        "lat": 61.292, "lon": 8.907, "elev_ft": 2953, "country": "Norway",
        "flag": "🇳🇴", "typical_snow": "new",
        "points": {"weather": {"lat": 61.292, "lon": 8.907}},
    },
    "Lillehammer": {
        "lat": 61.115, "lon": 10.464, "elev_ft": 853, "country": "Norway",
        "flag": "🇳🇴", "typical_snow": "transformed",
        "points": {"weather": {"lat": 61.115, "lon": 10.464}},
    },
    "Ruka/Kuusamo": {
        "lat": 66.170, "lon": 29.147, "elev_ft": 820, "country": "Finland",
        "flag": "🇫🇮", "typical_snow": "new",
        "points": {"weather": {"lat": 66.170, "lon": 29.147}},
    },
    "Gällivare": {
        "lat": 67.140, "lon": 20.652, "elev_ft": 1155, "country": "Sweden",
        "flag": "🇸🇪", "typical_snow": "new",
        "points": {"weather": {"lat": 67.140, "lon": 20.652}},
    },
    "Östersund": {
        "lat": 63.176, "lon": 14.637, "elev_ft": 1158, "country": "Sweden",
        "flag": "🇸🇪", "typical_snow": "packed",
        "points": {"weather": {"lat": 63.176, "lon": 14.637}},
    },
    # ---- Central Europe ----------------------------------------------------
    "Oberstdorf": {
        "lat": 47.408, "lon": 10.281, "elev_ft": 2756, "country": "Germany",
        "flag": "🇩🇪", "typical_snow": "transformed",
        "points": {"weather": {"lat": 47.408, "lon": 10.281}},
    },
    "Val di Fiemme": {
        "lat": 46.248, "lon": 11.378, "elev_ft": 3609, "country": "Italy",
        "flag": "🇮🇹", "typical_snow": "transformed",
        "points": {"weather": {"lat": 46.248, "lon": 11.378}},
    },
    "Davos": {
        "lat": 46.803, "lon": 9.838, "elev_ft": 5118, "country": "Switzerland",
        "flag": "🇨🇭", "typical_snow": "new",
        "points": {"weather": {"lat": 46.803, "lon": 9.838}},
    },
    "Planica": {
        "lat": 46.482, "lon": 13.726, "elev_ft": 2953, "country": "Slovenia",
        "flag": "🇸🇮", "typical_snow": "wet",
        "points": {"weather": {"lat": 46.482, "lon": 13.726}},
    },
    "Cogne": {
        "lat": 45.609, "lon": 7.355, "elev_ft": 4921, "country": "Italy",
        "flag": "🇮🇹", "typical_snow": "new",
        "points": {"weather": {"lat": 45.609, "lon": 7.355}},
    },
    "Lenzerheide": {
        "lat": 46.729, "lon": 9.560, "elev_ft": 4757, "country": "Switzerland",
        "flag": "🇨🇭", "typical_snow": "transformed",
        "points": {"weather": {"lat": 46.729, "lon": 9.560}},
    },
    # ---- North America -----------------------------------------------------
    "Canmore": {
        "lat": 51.089, "lon": -115.359, "elev_ft": 4511, "country": "Canada",
        "flag": "🇨🇦", "typical_snow": "new",
        "points": {"weather": {"lat": 51.089, "lon": -115.359}},
    },
    "Soldier Hollow": {
        "lat": 40.460, "lon": -111.418, "elev_ft": 5610, "country": "USA",
        "flag": "🇺🇸", "typical_snow": "transformed",
        "points": {"weather": {"lat": 40.460, "lon": -111.418}},
    },
    "Lake Placid": {
        "lat": 44.279, "lon": -73.980, "elev_ft": 1860, "country": "USA",
        "flag": "🇺🇸", "typical_snow": "packed",
        "points": {"weather": {"lat": 44.279, "lon": -73.980}},
    },
    "Craftsbury": {
        "lat": 44.647, "lon": -72.371, "elev_ft": 1340, "country": "USA",
        "flag": "🇺🇸", "typical_snow": "packed",
        "points": {"weather": {"lat": 44.647, "lon": -72.371}},
    },
    "Bozeman/Bohart Ranch": {
        "lat": 45.804, "lon": -110.778, "elev_ft": 5740, "country": "USA",
        "flag": "🇺🇸", "typical_snow": "new",
        "points": {"weather": {"lat": 45.804, "lon": -110.778}},
    },
}

# ---------------------------------------------------------------------------
# Wax product matrices
# ---------------------------------------------------------------------------

# Classic grip: hard wax (cold/dry/new snow) — temp range in °C, all fluoro-free
HARD_WAX: list[dict] = [
    # Rex
    {"name": "Rex Blue Extra", "brand": "Rex", "temp_min": -30.0, "temp_max": -15.0,
     "snow_types": ["new", "cold_powder"], "fluoro_free": True,
     "color": "#1e3a8a", "hex": "#1e3a8a",
     "notes": "Extreme cold, very low humidity; ultra-hard wax"},
    {"name": "Rex Blue", "brand": "Rex", "temp_min": -12.0, "temp_max": -3.0,
     "snow_types": ["new", "packed", "transformed"], "fluoro_free": True,
     "color": "#1a56db", "hex": "#1a56db",
     "notes": "Cold, fine-grained snow; most common cold kick wax"},
    {"name": "Rex Violet", "brand": "Rex", "temp_min": -5.0, "temp_max": 0.0,
     "snow_types": ["packed", "transformed"], "fluoro_free": True,
     "color": "#7e3af2", "hex": "#7e3af2",
     "notes": "Borderline conditions; hardest to call"},
    {"name": "Rex Red", "brand": "Rex", "temp_min": -2.0, "temp_max": +2.0,
     "snow_types": ["transformed", "packed"], "fluoro_free": True,
     "color": "#e02424", "hex": "#e02424",
     "notes": "Around freezing; transformed snow"},
    {"name": "Rex Yellow", "brand": "Rex", "temp_min": 0.0, "temp_max": +5.0,
     "snow_types": ["wet", "transformed"], "fluoro_free": True,
     "color": "#c27803", "hex": "#c27803",
     "notes": "Soft snow near melting"},
    {"name": "Rex Special Yellow", "brand": "Rex", "temp_min": +3.0, "temp_max": +10.0,
     "snow_types": ["wet"], "fluoro_free": True,
     "color": "#c27803", "hex": "#c27803",
     "notes": "Very wet, sticky snow; alternative to klister on course"},
    # Swix
    {"name": "Swix V20 Extra Blue", "brand": "Swix", "temp_min": -30.0, "temp_max": -15.0,
     "snow_types": ["new", "cold_powder"], "fluoro_free": True,
     "color": "#1e3a8a", "hex": "#1e3a8a",
     "notes": "Extreme cold, low humidity new snow"},
    {"name": "Swix V30 Blue", "brand": "Swix", "temp_min": -15.0, "temp_max": -7.0,
     "snow_types": ["new", "cold_powder", "packed"], "fluoro_free": True,
     "color": "#1a56db", "hex": "#1a56db",
     "notes": "Cold new or packed snow"},
    {"name": "Swix V40 Violet", "brand": "Swix", "temp_min": -7.0, "temp_max": -1.0,
     "snow_types": ["packed", "transformed"], "fluoro_free": True,
     "color": "#7e3af2", "hex": "#7e3af2",
     "notes": "Medium cold, packed or transformed"},
    {"name": "Swix V45 Special Violet", "brand": "Swix", "temp_min": -4.0, "temp_max": +1.0,
     "snow_types": ["transformed", "packed"], "fluoro_free": True,
     "color": "#7e3af2", "hex": "#7e3af2",
     "notes": "Near-zero, tricky borderline conditions"},
    {"name": "Swix V50 Red", "brand": "Swix", "temp_min": -1.0, "temp_max": +2.0,
     "snow_types": ["transformed", "wet"], "fluoro_free": True,
     "color": "#e02424", "hex": "#e02424",
     "notes": "Around freezing, transformed snow"},
    {"name": "Swix V55 Yellow", "brand": "Swix", "temp_min": +1.0, "temp_max": +5.0,
     "snow_types": ["wet", "spring"], "fluoro_free": True,
     "color": "#c27803", "hex": "#c27803",
     "notes": "Soft, wet snow near melting"},
    # Rode
    {"name": "Rode Blue", "brand": "Rode", "temp_min": -14.0, "temp_max": -5.0,
     "snow_types": ["new", "cold_powder", "packed"], "fluoro_free": True,
     "color": "#1a56db", "hex": "#1a56db",
     "notes": "Cold fine-grained new or packed snow"},
    {"name": "Rode Viola", "brand": "Rode", "temp_min": -6.0, "temp_max": 0.0,
     "snow_types": ["packed", "transformed"], "fluoro_free": True,
     "color": "#7e3af2", "hex": "#7e3af2",
     "notes": "Medium cold, packed or transformed"},
    {"name": "Rode Rosso", "brand": "Rode", "temp_min": -2.0, "temp_max": +3.0,
     "snow_types": ["transformed", "wet"], "fluoro_free": True,
     "color": "#e02424", "hex": "#e02424",
     "notes": "Around freezing, transformed snow"},
]

# Classic grip: klister (transformed/icy/wet snow) — all fluoro-free
KLISTER: list[dict] = [
    # Rex
    {"name": "Rex Blue Klister", "brand": "Rex", "temp_min": -8.0, "temp_max": -2.0,
     "snow_types": ["icy", "hard_groomed"], "fluoro_free": True,
     "color": "#1a56db", "hex": "#1a56db",
     "notes": "Hard pack, icy conditions, refrozen crust"},
    {"name": "Rex Violet Klister", "brand": "Rex", "temp_min": -3.0, "temp_max": +2.0,
     "snow_types": ["icy", "hard_groomed", "wet"], "fluoro_free": True,
     "color": "#7e3af2", "hex": "#7e3af2",
     "notes": "Refrozen groomed or hard pack near zero"},
    {"name": "Rex Red Klister", "brand": "Rex", "temp_min": -1.0, "temp_max": +5.0,
     "snow_types": ["wet", "icy"], "fluoro_free": True,
     "color": "#e02424", "hex": "#e02424",
     "notes": "Wet or icy transformed snow"},
    {"name": "Rex Yellow Klister", "brand": "Rex", "temp_min": +2.0, "temp_max": +10.0,
     "snow_types": ["wet", "spring"], "fluoro_free": True,
     "color": "#c27803", "hex": "#c27803",
     "notes": "Wet, slushy, or corn snow"},
    {"name": "Rex Silver Klister", "brand": "Rex", "temp_min": +5.0, "temp_max": +15.0,
     "snow_types": ["spring", "wet"], "fluoro_free": True,
     "color": "#9ca3af", "hex": "#9ca3af",
     "notes": "Very wet spring conditions"},
    # Swix
    {"name": "Swix K21 Blue Klister", "brand": "Swix", "temp_min": -8.0, "temp_max": -2.0,
     "snow_types": ["icy", "hard_groomed"], "fluoro_free": True,
     "color": "#1a56db", "hex": "#1a56db",
     "notes": "Ice and hard pack, refrozen crust"},
    {"name": "Swix K22 Purple Klister", "brand": "Swix", "temp_min": -5.0, "temp_max": 0.0,
     "snow_types": ["icy", "transformed"], "fluoro_free": True,
     "color": "#7e3af2", "hex": "#7e3af2",
     "notes": "Hard pack near zero, icy groomed tracks"},
    {"name": "Swix K25 Violet Klister", "brand": "Swix", "temp_min": -3.0, "temp_max": +2.0,
     "snow_types": ["icy", "wet", "transformed"], "fluoro_free": True,
     "color": "#7e3af2", "hex": "#7e3af2",
     "notes": "Near-zero icy or wet transformed"},
    {"name": "Swix K70 Red Klister", "brand": "Swix", "temp_min": -1.0, "temp_max": +7.0,
     "snow_types": ["wet", "spring"], "fluoro_free": True,
     "color": "#e02424", "hex": "#e02424",
     "notes": "Wet or slushy conditions"},
    # Rode
    {"name": "Rode Blue Klister", "brand": "Rode", "temp_min": -8.0, "temp_max": -2.0,
     "snow_types": ["icy", "hard_groomed"], "fluoro_free": True,
     "color": "#1a56db", "hex": "#1a56db",
     "notes": "Ice and hard pack, cold"},
    {"name": "Rode Red Klister", "brand": "Rode", "temp_min": -2.0, "temp_max": +5.0,
     "snow_types": ["wet", "icy", "spring"], "fluoro_free": True,
     "color": "#e02424", "hex": "#e02424",
     "notes": "Wet or icy transformed snow"},
]

# Glide wax (Classic and Skate) — temp in °C, all fluoro-free (FIS 2023 rule)
GLIDE_WAX: list[dict] = [
    # Extreme cold: -30 to -12°C
    {"name": "Swix Pure Speed 6", "brand": "Swix", "tier": "race",
     "temp_min": -30.0, "temp_max": -12.0, "humidity_max": 60, "fluoro_free": True,
     "color": "#1e3a8a", "hex": "#1e3a8a",
     "notes": "Extreme cold race glide, low humidity powder snow"},
    {"name": "Swix LF6", "brand": "Swix", "tier": "training",
     "temp_min": -30.0, "temp_max": -12.0, "humidity_max": 70, "fluoro_free": True,
     "color": "#1e3a8a", "hex": "#1e3a8a",
     "notes": "Extreme cold training glide"},
    {"name": "Rode Cera G Blue Extra", "brand": "Rode", "tier": "race",
     "temp_min": -30.0, "temp_max": -12.0, "humidity_max": 65, "fluoro_free": True,
     "color": "#1e3a8a", "hex": "#1e3a8a",
     "notes": "Extreme cold fluoro-free race glide"},
    {"name": "Rex Racing Green", "brand": "Rex", "tier": "race",
     "temp_min": -30.0, "temp_max": -14.0, "humidity_max": 60, "fluoro_free": True,
     "color": "#14532d", "hex": "#14532d",
     "notes": "Extreme cold, very low humidity conditions"},
    {"name": "Swix CH6", "brand": "Swix", "tier": "recreational",
     "temp_min": -25.0, "temp_max": -12.0, "humidity_max": 70, "fluoro_free": True,
     "color": "#1e3a8a", "hex": "#1e3a8a",
     "notes": "Extreme cold recreational glide"},
    # Cold: -13 to -6°C
    {"name": "Swix Pure Speed 7", "brand": "Swix", "tier": "race",
     "temp_min": -13.0, "temp_max": -6.0, "humidity_max": 70, "fluoro_free": True,
     "color": "#1a56db", "hex": "#1a56db",
     "notes": "Cold, low humidity race glide"},
    {"name": "Swix LF7", "brand": "Swix", "tier": "training",
     "temp_min": -13.0, "temp_max": -6.0, "humidity_max": 80, "fluoro_free": True,
     "color": "#1a56db", "hex": "#1a56db",
     "notes": "Cold training glide"},
    {"name": "Rode Cera G Blue", "brand": "Rode", "tier": "race",
     "temp_min": -13.0, "temp_max": -6.0, "humidity_max": 75, "fluoro_free": True,
     "color": "#1a56db", "hex": "#1a56db",
     "notes": "Cold fluoro-free race glide"},
    {"name": "Rex Racing Blue", "brand": "Rex", "tier": "race",
     "temp_min": -15.0, "temp_max": -6.0, "humidity_max": 75, "fluoro_free": True,
     "color": "#1a56db", "hex": "#1a56db",
     "notes": "Cold dry race glide"},
    {"name": "Swix CH7", "brand": "Swix", "tier": "recreational",
     "temp_min": -12.0, "temp_max": -5.0, "humidity_max": 80, "fluoro_free": True,
     "color": "#1a56db", "hex": "#1a56db",
     "notes": "Cold recreational glide"},
    # Medium: -9 to -2°C
    {"name": "Swix Pure Speed 8", "brand": "Swix", "tier": "race",
     "temp_min": -9.0, "temp_max": -2.0, "humidity_max": 80, "fluoro_free": True,
     "color": "#7e3af2", "hex": "#7e3af2",
     "notes": "Medium-cold race glide; most versatile"},
    {"name": "Swix LF8", "brand": "Swix", "tier": "training",
     "temp_min": -9.0, "temp_max": -2.0, "humidity_max": 85, "fluoro_free": True,
     "color": "#7e3af2", "hex": "#7e3af2",
     "notes": "Medium training glide"},
    {"name": "Rode Cera G Yellow", "brand": "Rode", "tier": "race",
     "temp_min": -10.0, "temp_max": -2.0, "humidity_max": 85, "fluoro_free": True,
     "color": "#7e3af2", "hex": "#7e3af2",
     "notes": "Medium fluoro-free race glide"},
    {"name": "Rex Racing Violet", "brand": "Rex", "tier": "race",
     "temp_min": -8.0, "temp_max": -1.0, "humidity_max": 85, "fluoro_free": True,
     "color": "#7e3af2", "hex": "#7e3af2",
     "notes": "Medium cold dry/medium conditions"},
    {"name": "Swix CH8", "brand": "Swix", "tier": "recreational",
     "temp_min": -8.0, "temp_max": 0.0, "humidity_max": 85, "fluoro_free": True,
     "color": "#7e3af2", "hex": "#7e3af2",
     "notes": "Medium recreational glide"},
    # Warm: -3 to +10°C
    {"name": "Swix Pure Speed 10", "brand": "Swix", "tier": "race",
     "temp_min": -3.0, "temp_max": +10.0, "humidity_max": 100, "fluoro_free": True,
     "color": "#e02424", "hex": "#e02424",
     "notes": "Warm/wet race glide"},
    {"name": "Swix LF10", "brand": "Swix", "tier": "training",
     "temp_min": -3.0, "temp_max": +10.0, "humidity_max": 100, "fluoro_free": True,
     "color": "#e02424", "hex": "#e02424",
     "notes": "Warm/wet training glide"},
    {"name": "Rode Cera G Red", "brand": "Rode", "tier": "race",
     "temp_min": -3.0, "temp_max": +8.0, "humidity_max": 100, "fluoro_free": True,
     "color": "#e02424", "hex": "#e02424",
     "notes": "Warm fluoro-free race glide"},
    {"name": "Swix CH10", "brand": "Swix", "tier": "recreational",
     "temp_min": -2.0, "temp_max": +10.0, "humidity_max": 100, "fluoro_free": True,
     "color": "#e02424", "hex": "#e02424",
     "notes": "Warm recreational glide"},
]

# Binder wax (applied under kick wax for durability) — all fluoro-free
BINDERS: list[dict] = [
    {
        "name": "Swix V40 Binder",
        "brand": "Swix",
        "for_klister": False,
        "fluoro_free": True,
        "notes": "Universal hard wax binder. Apply 2 thin layers, iron in at low heat, cork smooth, let cool fully before applying kick wax.",
    },
    {
        "name": "Rex Binder K33",
        "brand": "Rex",
        "for_klister": False,
        "fluoro_free": True,
        "notes": "Cold-resistant hard wax binder. Cork in before kick wax — extends wax life on abrasive groomed snow.",
    },
    {
        "name": "Swix KR30 Klister Binder",
        "brand": "Swix",
        "for_klister": True,
        "fluoro_free": True,
        "notes": "Klister base layer. Apply thin coat, heat gun to spread evenly, let cool before klister.",
    },
    {
        "name": "Rex Klister Binder",
        "brand": "Rex",
        "for_klister": True,
        "fluoro_free": True,
        "notes": "Provides adhesion layer for klister in variable conditions; reduces icing in wet snow.",
    },
]


def select_binder(is_klister: bool) -> dict:
    """Return the recommended binder for hard wax or klister."""
    pool = [b for b in BINDERS if b["for_klister"] == is_klister]
    return pool[0] if pool else BINDERS[0]


# ---------------------------------------------------------------------------
# Weather fetching — NWS for CONUS, Open-Meteo globally (mirrors Alpine engine)
# ---------------------------------------------------------------------------

def get_conditions(lat: float, lon: float) -> dict[str, Any]:
    """Fetch current conditions — NWS for US coordinates, Open-Meteo elsewhere."""
    if _is_conus(lat, lon):
        return _get_conditions_nws(lat, lon)
    return _get_conditions_openmeteo(lat, lon)


def _nws_snow_signal(df: pd.DataFrame, now: pd.Timestamp) -> tuple[float, int]:
    """
    Scan 48 h of NWS forecast text + precip probability to produce a
    recent_snow_mm proxy and a WMO-style code for classify_snow.

    Returns (recent_snow_mm, wmo_code).
    Same credibility rules as the Alpine engine:
      snow keyword + POP ≥ 35 % + air temp ≤ 33.5 °F → credible snow event.
    Persistence decays with above-freezing hours after the event, exactly as
    Alpine's fresh-snow persistence score does.
    """
    def _has(text: str, phrases: list[str]) -> bool:
        t = str(text).lower()
        return any(p in t for p in phrases)

    window = df[(df["time"] >= now - pd.Timedelta(hours=48)) & (df["time"] <= now)].copy()
    if window.empty:
        window = df.iloc[: min(48, len(df))].copy()

    window["_text"] = window.get("short_forecast", pd.Series(dtype=str)).fillna("")
    window["_pop"]  = window.get("precip_prob_pct", pd.Series(dtype=float)).fillna(0.0)
    window["_tf"]   = window.get("air_temp_f", pd.Series(dtype=float)).fillna(32.0)

    window["_snow"] = window["_text"].apply(
        lambda t: _has(t, ["snow", "flurries", "snow showers", "wintry mix", "snow squalls"])
    )
    window["_rain"] = window["_text"].apply(
        lambda t: _has(t, ["rain", "drizzle", "freezing rain", "sleet"])
    )

    credible = window[window["_snow"] & (window["_pop"] >= 35) & (window["_tf"] <= 33.5)]
    if credible.empty:
        return 0.0, 0

    last_snow_time = credible["time"].max()
    after = window[window["time"] >= last_snow_time]

    # Fresh-snow persistence — same decay table as Alpine
    persistence = 1.0
    for t_f in after["_tf"].fillna(32.0):
        if t_f <= 20:
            persistence -= 0.005
        elif t_f <= 25:
            persistence -= 0.010
        elif t_f <= 30:
            persistence -= 0.025
        elif t_f <= 32:
            persistence -= 0.050
        else:
            persistence -= 0.080
    if after["_rain"].any():
        persistence -= 0.40
    persistence = float(max(0.0, min(1.0, persistence)))

    recent_snow_mm = 5.0 * persistence  # 5 mm base signal, scaled by persistence

    hours_ago = (now - last_snow_time).total_seconds() / 3600.0
    wmo_code = 73 if (hours_ago <= 3 and persistence >= 0.5) else 0  # 73 = moderate snow

    return recent_snow_mm, wmo_code


def _get_conditions_nws(lat: float, lon: float) -> dict[str, Any]:
    """Current conditions via NWS hourly forecast (CONUS only)."""
    from calculator.engine import get_hourly_forecast
    try:
        df = get_hourly_forecast(lat, lon)  # no extra kwargs — function takes only lat/lon
        now = pd.Timestamp.now()
        past = df[df["time"] <= now]
        row = past.iloc[-1] if not past.empty else df.iloc[0]

        temp_c = (float(row["air_temp_f"]) - 32.0) * 5.0 / 9.0
        humidity = float(row.get("rh_pct", 70.0) or 70.0)
        wind_kmh = float(row.get("wind_mph", 0.0) or 0.0) * 1.60934
        sky_pct  = float(row.get("sky_cover_pct", 50.0) or 50.0)

        recent_snow_mm, wmo_code = _nws_snow_signal(df, now)

        return {
            "temp_c": temp_c,
            "temp_f": float(row["air_temp_f"]),
            "humidity_pct": humidity,
            "precip_mm": 0.0,
            "wind_kmh": wind_kmh,
            "cloud_pct": sky_pct,
            "snow_depth_m": 0.0,
            "recent_snow_mm": recent_snow_mm,
            "wmo_code": wmo_code,
            "ok": True,
            "source": "nws",
        }
    except Exception as exc:
        return _get_conditions_openmeteo(lat, lon)


def _get_conditions_openmeteo(lat: float, lon: float) -> dict[str, Any]:
    """Current conditions via Open-Meteo (global)."""
    try:
        r = requests.get(
            "https://api.open-meteo.com/v1/forecast",
            params={
                "latitude": lat,
                "longitude": lon,
                "current": [
                    "temperature_2m", "relative_humidity_2m", "apparent_temperature",
                    "precipitation", "weather_code", "wind_speed_10m",
                    "cloud_cover", "snow_depth",
                ],
                "hourly": "temperature_2m,relative_humidity_2m,precipitation",
                "forecast_days": 2,
                "timezone": "auto",
            },
            timeout=10,
            headers={"User-Agent": "GlideCast-Nordic/1.0"},
        )
        r.raise_for_status()
        data = r.json()
        cur = data.get("current", {})
        temp_c = cur.get("temperature_2m", 0.0)
        humidity = cur.get("relative_humidity_2m", 70)
        precip = cur.get("precipitation", 0.0)
        wind_kmh = cur.get("wind_speed_10m", 0.0)
        cloud_pct = cur.get("cloud_cover", 50.0)
        snow_depth_m = cur.get("snow_depth", 0.0)
        wmo_code = cur.get("weather_code", 0)
        hourly_precip = (data.get("hourly", {}).get("precipitation") or [])[:3]
        recent_snow_mm = sum(hourly_precip) if hourly_precip else 0.0

        return {
            "temp_c": temp_c,
            "temp_f": temp_c * 9 / 5 + 32,
            "humidity_pct": humidity,
            "precip_mm": precip,
            "wind_kmh": wind_kmh,
            "cloud_pct": cloud_pct,
            "snow_depth_m": snow_depth_m,
            "recent_snow_mm": recent_snow_mm,
            "wmo_code": wmo_code,
            "ok": True,
            "source": "open-meteo",
        }
    except Exception as exc:
        return {
            "ok": False, "error": str(exc),
            "temp_c": 0.0, "temp_f": 32.0,
            "humidity_pct": 70, "precip_mm": 0.0, "wind_kmh": 0.0,
            "cloud_pct": 50.0, "snow_depth_m": 0.0, "recent_snow_mm": 0.0,
            "wmo_code": 0, "source": "open-meteo",
        }


# ---------------------------------------------------------------------------
# Snow condition classifier
# ---------------------------------------------------------------------------

def classify_snow(
    temp_c: float,
    humidity_pct: float,
    recent_snow_mm: float,
    snow_depth_m: float,
    wmo_code: int,
    user_override: str = "auto",
) -> tuple[str, str]:
    """Return (snow_type, reason).

    snow_type values: 'new', 'cold_powder', 'packed', 'transformed',
                      'hard_groomed', 'icy', 'wet', 'spring'
    """
    if user_override != "auto":
        reasons = {
            "new": "freshly fallen snow",
            "cold_powder": "cold, low-density powder",
            "packed": "packed, machine-groomed",
            "transformed": "settled, transformed snow",
            "hard_groomed": "hard-groomed / firm surface",
            "icy": "icy or refrozen surface",
            "wet": "wet, saturated snow",
            "spring": "spring corn snow",
        }
        return user_override, reasons.get(user_override, "manually selected")

    # WMO codes 71-77 = snowfall, 85-86 = snow showers
    is_snowing = wmo_code in {71, 72, 73, 74, 75, 76, 77, 85, 86}
    # WMO 56-57 = freezing drizzle, 66-67 = freezing rain
    is_freezing_precip = wmo_code in {56, 57, 66, 67}

    if is_freezing_precip or (temp_c < -1.0 and humidity_pct > 85 and not is_snowing):
        return "icy", "freezing precipitation or high humidity near zero — icy surface likely"

    if is_snowing and recent_snow_mm > 1.0:
        if temp_c < -8.0:
            return "cold_powder", f"fresh snowfall ({recent_snow_mm:.1f} mm recent) at cold temps"
        return "new", f"fresh snowfall ({recent_snow_mm:.1f} mm recent)"

    # Snowed recently but not actively snowing now — fresh-snow signal from NWS text/POP
    if recent_snow_mm > 2.5:
        if temp_c < -8.0:
            return "cold_powder", f"recent snowfall signal ({recent_snow_mm:.1f} mm) — cold powder likely still intact"
        return "packed", f"recent snowfall ({recent_snow_mm:.1f} mm signal) — groomed packed surface"

    if temp_c >= +3.0 and humidity_pct >= 80:
        if temp_c >= +6.0:
            return "spring", "warm spring conditions, wet corn snow"
        return "wet", "warm and humid — wet surface snow"

    if temp_c >= -1.0 and temp_c < +3.0:
        return "transformed", "near-zero temperatures, settled transformed snow"

    if temp_c < -8.0:
        if snow_depth_m < 0.1:
            return "hard_groomed", "cold with thin snowpack — likely hard groomed base"
        return "packed", "cold, packed snow"

    return "packed", "typical cold groomed conditions"


# ---------------------------------------------------------------------------
# Kick wax selector (Classic only)
# ---------------------------------------------------------------------------

def _needs_klister(snow_type: str, temp_c: float) -> bool:
    """Klister is needed for icy, hard-groomed, or wet/spring snow."""
    klister_types = {"icy", "hard_groomed", "wet", "spring"}
    if snow_type in klister_types:
        return True
    # At or just below zero with marginal humidity — klister often beats hard wax
    if snow_type == "transformed" and temp_c >= -1.5:
        return True
    return False


def select_grip_wax(
    temp_c: float,
    snow_type: str,
) -> dict[str, Any]:
    """Return the best kick wax product dict and alternates."""
    use_klister = _needs_klister(snow_type, temp_c)
    matrix = KLISTER if use_klister else HARD_WAX

    # Score each product: temperature overlap + snow type match
    def _score(p: dict) -> float:
        if temp_c < p["temp_min"] or temp_c > p["temp_max"]:
            # Outside band: allow negative scores so closest product still wins
            dist = min(abs(temp_c - p["temp_min"]), abs(temp_c - p["temp_max"]))
            band_score = 1.0 - dist / 5.0
        else:
            # Inside band: prefer center
            mid = (p["temp_min"] + p["temp_max"]) / 2
            half_width = (p["temp_max"] - p["temp_min"]) / 2
            band_score = 1.0 - abs(temp_c - mid) / max(half_width, 0.5)

        snow_score = 1.0 if snow_type in p["snow_types"] else 0.4
        return band_score * snow_score

    scored = sorted(matrix, key=_score, reverse=True)
    best = scored[0] if scored else matrix[0]
    alternates = [p["name"] for p in scored[1:3]]

    # Confidence: how well does the temp sit in the band?
    in_band = best["temp_min"] <= temp_c <= best["temp_max"]
    temp_margin = min(abs(temp_c - best["temp_min"]), abs(temp_c - best["temp_max"])) if in_band else 0.0
    band_width = best["temp_max"] - best["temp_min"]
    confidence = 0.95 if (in_band and temp_margin > 0.5) else (0.70 if in_band else 0.50)
    if not in_band:
        # Near edge — suggest layering
        alternates = [scored[1]["name"]] if len(scored) > 1 else []

    return {
        "product": best["name"],
        "brand": best["brand"],
        "notes": best["notes"],
        "color": best["color"],
        "hex": best["hex"],
        "alternates": alternates,
        "is_klister": use_klister,
        "confidence": confidence,
        "in_band": in_band,
        "temp_c": round(temp_c, 1),
        "band_min_c": best["temp_min"],
        "band_max_c": best["temp_max"],
    }


# ---------------------------------------------------------------------------
# Glide wax selector
# ---------------------------------------------------------------------------

def select_glide_wax(
    temp_c: float,
    humidity_pct: float,
    tier: str = "race",
) -> dict[str, Any]:
    """Return glide wax recommendation. tier = 'race' | 'training' | 'recreational'."""
    # Filter by tier
    pool = [w for w in GLIDE_WAX if w["tier"] == tier]
    if not pool:
        pool = GLIDE_WAX

    def _score(w: dict) -> float:
        if temp_c < w["temp_min"] or temp_c > w["temp_max"]:
            dist = min(abs(temp_c - w["temp_min"]), abs(temp_c - w["temp_max"]))
            temp_s = 1.0 - dist / 5.0
        else:
            mid = (w["temp_min"] + w["temp_max"]) / 2
            half_w = (w["temp_max"] - w["temp_min"]) / 2
            temp_s = 1.0 - abs(temp_c - mid) / max(half_w, 0.5)
        hum_s = 1.0 if humidity_pct <= w["humidity_max"] else max(0.2, 1.0 - (humidity_pct - w["humidity_max"]) / 30)
        return temp_s * hum_s

    scored = sorted(pool, key=_score, reverse=True)
    best = scored[0]
    alternates = [w["name"] for w in scored[1:2]]

    in_band = best["temp_min"] <= temp_c <= best["temp_max"]
    confidence = 0.90 if in_band else 0.65

    return {
        "product": best["name"],
        "brand": best["brand"],
        "notes": best["notes"],
        "color": best["color"],
        "hex": best["hex"],
        "alternates": alternates,
        "tier": tier,
        "confidence": confidence,
        "in_band": in_band,
        "temp_c": round(temp_c, 1),
        "band_min_c": best["temp_min"],
        "band_max_c": best["temp_max"],
        "humidity_pct": humidity_pct,
    }


# ---------------------------------------------------------------------------
# Top-level recommendation function
# ---------------------------------------------------------------------------

def recommend(
    venue_key: str,
    discipline: str,
    snow_mode: str = "auto",
    tier: str = "race",
) -> dict[str, Any]:
    """Full Nordic wax recommendation for a venue + discipline.

    discipline: 'Classic' | 'Skate'
    snow_mode:  'auto' | 'new' | 'packed' | 'transformed' | 'icy' | 'wet' | 'spring'
    tier:       'race' | 'training' | 'recreational'
    """
    venue = VENUES.get(venue_key)
    if venue is None:
        return {"error": f"Unknown venue: {venue_key}", "ok": False}

    wp = venue["points"]["weather"]
    conditions = get_conditions(wp["lat"], wp["lon"])

    temp_c = conditions["temp_c"]
    humidity_pct = conditions["humidity_pct"]
    recent_snow_mm = conditions["recent_snow_mm"]
    snow_depth_m = conditions["snow_depth_m"]
    wmo_code = conditions["wmo_code"]

    snow_type, snow_reason = classify_snow(
        temp_c, humidity_pct, recent_snow_mm, snow_depth_m, wmo_code, snow_mode
    )

    glide = select_glide_wax(temp_c, humidity_pct, tier)

    result: dict[str, Any] = {
        "ok": True,
        "venue": venue_key,
        "discipline": discipline,
        "conditions": {
            "temp_c": round(temp_c, 1),
            "temp_f": round(temp_c * 9 / 5 + 32, 1),
            "humidity_pct": humidity_pct,
            "wind_kmh": round(conditions.get("wind_kmh", 0.0), 1),
            "snow_depth_m": round(snow_depth_m, 2),
            "recent_snow_mm": round(recent_snow_mm, 1),
            "weather_ok": conditions.get("ok", False),
        },
        "snow_type": snow_type,
        "snow_reason": snow_reason,
        "glide": glide,
    }

    if discipline == "Classic":
        grip = select_grip_wax(temp_c, snow_type)
        result["grip"] = grip
        # Overall confidence = weighted average
        result["confidence"] = round(
            0.55 * grip["confidence"] + 0.45 * glide["confidence"], 2
        )
    else:
        # Skate: glide only
        result["grip"] = None
        result["confidence"] = round(glide["confidence"], 2)

    # Confidence label
    c = result["confidence"]
    if c >= 0.80:
        result["confidence_label"] = "High"
        result["confidence_color"] = "#16a34a"
    elif c >= 0.60:
        result["confidence_label"] = "Medium"
        result["confidence_color"] = "#d97706"
    else:
        result["confidence_label"] = "Low"
        result["confidence_color"] = "#dc2626"

    return result


# ---------------------------------------------------------------------------
# Course-aware analysis (Phase 2) — GPX + real per-point weather + canopy
# ---------------------------------------------------------------------------

# Canopy shade factors: fraction of solar radiation blocked by forest cover.
# Reduces snow surface warming on sunny days.
_CANOPY_SHADE = {
    "open":   0.00,
    "mixed":  0.35,
    "dense":  0.72,
}

def _is_conus(lat: float, lon: float) -> bool:
    """True if coordinates are within the continental United States."""
    return 24.0 <= lat <= 50.0 and -125.0 <= lon <= -65.0


def _fetch_weather_nws(samples: list[dict]) -> list[dict]:
    """Fetch weather for a US trail using NWS — same upper/lower point approach as Alpine.

    Picks the highest and lowest elevation samples as the two NWS query points,
    fetches hourly forecasts for each, then interpolates to every segment by elevation
    using the lapse rate between those two points (identical to how Alpine does it).
    """
    from calculator.engine import get_hourly_forecast, merge_forecasts

    sorted_elev = sorted(samples, key=lambda s: s["elevation_m"])
    lower_s = sorted_elev[0]
    upper_s = sorted_elev[-1]

    try:
        upper_df = get_hourly_forecast(upper_s["lat"], upper_s["lon"])
        lower_df = get_hourly_forecast(lower_s["lat"], lower_s["lon"])
        merged   = merge_forecasts(upper_df, lower_df)

        # Find the row closest to now
        now = pd.Timestamp.now()
        past = merged[merged["time"] <= now]
        row  = past.iloc[-1] if not past.empty else merged.iloc[0]

        upper_elev_m = upper_s["elevation_m"]
        lower_elev_m = lower_s["elevation_m"]
        elev_range   = upper_elev_m - lower_elev_m

        upper_f = float(row["air_upper_f"])
        lower_f = float(row["air_lower_f"])
        lapse_f_per_m = (upper_f - lower_f) / elev_range if elev_range > 1 else 0.0

        rh_pct    = float(row.get("rh_upper_pct", row.get("rh_lower_pct", 70.0)) or 70.0)
        wind_mph  = float(row.get("wind_upper_mph", 0.0) or 0.0)
        sky_pct   = float(row.get("sky_upper_pct", row.get("sky_lower_pct", 50.0)) or 50.0)
        is_day    = bool(row.get("is_day_upper", True))

        # Snow signal from NWS forecast text — same 48-hour lookback as _get_conditions_nws
        recent_snow_mm, snow_wmo = _nws_snow_signal(upper_df, now)

        for s in samples:
            interp_f = lower_f + lapse_f_per_m * (s["elevation_m"] - lower_elev_m)
            s["weather_temp_c"]         = (interp_f - 32.0) * 5.0 / 9.0
            s["weather_humidity_pct"]   = rh_pct
            s["weather_wind_kmh"]       = wind_mph * 1.60934
            s["weather_cloud_pct"]      = sky_pct
            s["weather_is_day"]         = is_day
            s["weather_precip_mm"]      = 0.0
            s["weather_recent_snow_mm"] = recent_snow_mm
            s["weather_wmo_code"]       = snow_wmo
            s["weather_snow_depth_m"]   = 0.0
            s["weather_ok"]             = True
    except Exception:
        for s in samples:
            s.setdefault("weather_temp_c", None)
            s.setdefault("weather_humidity_pct", None)
            s.setdefault("weather_wind_kmh", 0.0)
            s.setdefault("weather_cloud_pct", 0.0)
            s.setdefault("weather_is_day", True)
            s.setdefault("weather_ok", False)

    return samples


def _fetch_weather_openmeteo(samples: list[dict]) -> list[dict]:
    """Batch-fetch Open-Meteo current conditions at each GPX sample point.

    Same variables as the Alpine Open-Meteo path: temp, humidity, wind,
    cloud cover, is_day, precipitation, weather_code, snow_depth.
    Batches in groups of 50 (Open-Meteo multi-location limit).
    """
    BATCH = 50
    _CURRENT_VARS = (
        "temperature_2m,relative_humidity_2m,wind_speed_10m,"
        "cloud_cover,is_day,precipitation,weather_code,snow_depth"
    )
    for start in range(0, len(samples), BATCH):
        batch = samples[start: start + BATCH]
        lats  = ",".join(str(round(s["lat"], 5)) for s in batch)
        lons  = ",".join(str(round(s["lon"], 5)) for s in batch)
        elevs = ",".join(str(int(s["elevation_m"])) for s in batch)
        try:
            r = requests.get(
                "https://api.open-meteo.com/v1/forecast",
                params={
                    "latitude":  lats,
                    "longitude": lons,
                    "elevation": elevs,
                    "current":   _CURRENT_VARS,
                    "timezone":  "auto",
                    "forecast_days": "1",
                },
                timeout=15,
                headers={"User-Agent": "GlideCast-Nordic/1.0"},
            )
            r.raise_for_status()
            data = r.json()
            if isinstance(data, dict):
                data = [data]
            for i, item in enumerate(data):
                cur = item.get("current", {})
                batch[i]["weather_temp_c"]       = cur.get("temperature_2m", None)
                batch[i]["weather_humidity_pct"]  = cur.get("relative_humidity_2m", None)
                batch[i]["weather_wind_kmh"]      = cur.get("wind_speed_10m", 0.0)
                batch[i]["weather_cloud_pct"]     = cur.get("cloud_cover", 0.0)
                batch[i]["weather_is_day"]        = bool(cur.get("is_day", 1))
                batch[i]["weather_precip_mm"]     = cur.get("precipitation", 0.0)
                batch[i]["weather_wmo_code"]        = cur.get("weather_code", 0)
                batch[i]["weather_snow_depth_m"]   = cur.get("snow_depth", 0.0)
                # Use current precipitation as a recent-snow proxy for per-segment classify_snow
                batch[i]["weather_recent_snow_mm"] = cur.get("precipitation", 0.0)
                batch[i]["weather_ok"]             = True
        except Exception:
            for s in batch:
                s.setdefault("weather_temp_c", None)
                s.setdefault("weather_humidity_pct", None)
                s.setdefault("weather_wind_kmh", 0.0)
                s.setdefault("weather_cloud_pct", 0.0)
                s.setdefault("weather_is_day", True)
                s.setdefault("weather_ok", False)
    return samples


def fetch_segment_weather(samples: list[dict]) -> list[dict]:
    """Fetch weather for all GPX samples — NWS for US trails, Open-Meteo elsewhere.

    Mirrors the Alpine engine's per-region API routing.
    """
    if not samples:
        return samples
    mid = samples[len(samples) // 2]
    if _is_conus(mid["lat"], mid["lon"]):
        return _fetch_weather_nws(samples)
    return _fetch_weather_openmeteo(samples)


def _snow_surface_temp(
    air_temp_c: float,
    lat: float,
    lon: float,
    elevation_m: float,
    bearing_deg: float,
    slope_deg: float,
    cloud_pct: float,
    wind_kmh: float,
    humidity_pct: float,
    canopy: str,
    race_dt: "pd.Timestamp | None" = None,
) -> float:
    """Exact same energy-balance formula as the Alpine engine.

    bearing_deg and slope_deg come from the GPX track instead of a fixed venue value.
    Canopy attenuates solar by increasing the effective cloud attenuation coefficient.
    """
    air_f      = air_temp_c * 9.0 / 5.0 + 32.0
    wind_mph   = wind_kmh * 0.621371
    cloud_frac = cloud_pct / 100.0

    # Canopy shade: denser canopy is treated as additional cloud attenuation
    canopy_shade           = _CANOPY_SHADE.get(canopy, 0.35)
    effective_cloud_atten  = min(1.0, _CLOUD_ATTENUATION + canopy_shade * (1.0 - _CLOUD_ATTENUATION))

    # Solar geometry at this exact lat/lon/elevation using GPX bearing as aspect
    now_naive = (race_dt if race_dt is not None else pd.Timestamp.now()).replace(tzinfo=None)
    try:
        solar_df     = solar_geometry_and_irradiance(
            times_local_naive=(now_naive,),
            lat=lat, lon=lon, elev_m=elevation_m,
            slope_deg=slope_deg, aspect_deg=bearing_deg,
            cloud_tuple=(cloud_frac,),
            cloud_attenuation=effective_cloud_atten,
            diffuse_floor_frac=_DIFFUSE_FLOOR_FRAC,
            albedo=_ALBEDO,
        )
        solar_norm    = float(solar_df["solar_norm"].iloc[0])
        solar_elev_deg = float(solar_df["solar_elevation_deg"].iloc[0])
    except Exception:
        solar_norm     = 0.0
        solar_elev_deg = -6.0  # treat as dark on failure

    # Same energy-balance terms as Alpine (single-step snapshot at current conditions)
    snow_f = air_f
    solar_term  = _SOLAR_COEFF * solar_norm
    lw          = longwave_exchange_term_f(air_f, snow_f, humidity_pct, cloud_frac, _LONGWAVE_COEFF)
    latent      = latent_exchange_term_f(air_f, snow_f, humidity_pct, wind_mph, _LATENT_COEFF)
    clear_night = clear_night_cooling_term_f(humidity_pct, cloud_frac, wind_mph, solar_elev_deg, _CLEAR_NIGHT_COEFF)

    snow_f = air_f + solar_term + lw + latent - clear_night
    snow_f = min(snow_f, 32.0)  # snow surface cannot exceed 0 °C
    return (snow_f - 32.0) * 5.0 / 9.0


def analyze_course(
    samples: list[dict],
    fallback_conditions: dict,
    discipline: str,
    canopy: str,
    snow_mode: str,
    tier: str,
    venue_elev_m: float,  # kept for signature compat, not used for lapse rate
    race_dt: "pd.Timestamp | None" = None,
) -> dict[str, Any]:
    """Run per-segment wax analysis using real weather at each GPX coordinate.

    Each sample gets its own Open-Meteo temperature at its actual lat/lon/elevation.
    Canopy shade and aspect are applied on top of the real air temperature to derive
    snow surface temperature.  Fallback_conditions is used only when the API fails.
    """
    from .gpx_parser import course_stats

    # Fetch real weather at every sample point
    samples = fetch_segment_weather(samples)

    fb_temp     = fallback_conditions["temp_c"]
    fb_humidity = fallback_conditions["humidity_pct"]
    fb_precip   = fallback_conditions["recent_snow_mm"]
    fb_depth    = fallback_conditions["snow_depth_m"]
    fb_wmo      = fallback_conditions["wmo_code"]

    _mid = samples[len(samples) // 2]
    _using_nws = _is_conus(_mid["lat"], _mid["lon"])

    seg_results = []
    for i, s in enumerate(samples):
        ok          = s.get("weather_ok", False)
        air_temp    = s.get("weather_temp_c")       if ok else None
        humidity    = s.get("weather_humidity_pct") if ok else None
        wind_kmh    = s.get("weather_wind_kmh",  fallback_conditions.get("wind_kmh", 0.0))
        cloud_pct   = s.get("weather_cloud_pct", 0.0)
        recent_snow = s.get("weather_recent_snow_mm", fb_precip)
        snow_depth  = s.get("weather_snow_depth_m", fb_depth)
        wmo_code    = s.get("weather_wmo_code",  fb_wmo)

        if air_temp is None:
            air_temp = fb_temp
        if humidity is None:
            humidity = fb_humidity

        # Slope in degrees from GPX elevation change over horizontal distance
        elev_gain_m  = s.get("elev_gain_m", 0.0)
        horiz_m      = s.get("dist_m", 300.0) or 300.0
        slope_deg    = math.degrees(math.atan(abs(elev_gain_m) / horiz_m)) if horiz_m > 0 else 0.0
        slope_deg    = min(slope_deg, 45.0)

        # Same Alpine energy-balance formula; GPX bearing replaces fixed venue aspect_deg
        snow_temp = _snow_surface_temp(
            air_temp,
            lat=s["lat"], lon=s["lon"], elevation_m=s["elevation_m"],
            bearing_deg=s.get("bearing_deg", 0.0),
            slope_deg=slope_deg,
            cloud_pct=cloud_pct, wind_kmh=wind_kmh, humidity_pct=humidity,
            canopy=canopy,
            race_dt=race_dt,
        )

        snow_type, _ = classify_snow(
            snow_temp, humidity, recent_snow, snow_depth, wmo_code, snow_mode
        )
        glide = select_glide_wax(snow_temp, humidity, tier)
        grip  = select_grip_wax(snow_temp, snow_type) if discipline == "Classic" else None

        seg_results.append({
            "dist_km":         round(s["cum_dist_m"] / 1000, 2),
            "elevation_m":     round(s["elevation_m"], 1),
            "elev_gain_m":     round(elev_gain_m, 1),
            "slope_deg":       round(slope_deg, 1),
            "bearing_deg":     round(s.get("bearing_deg", 0.0), 1),
            "aspect_class":    s.get("aspect_class", "flat"),
            "air_temp_c":      round(air_temp, 1),
            "wind_kmh":        round(wind_kmh, 1),
            "cloud_pct":       round(cloud_pct, 0),
            "temp_c":          round(snow_temp, 1),
            "humidity_pct":    round(humidity, 0),
            "snow_type":       snow_type,
            "weather_ok":      ok,
            "grip_product":    grip["product"] if grip else None,
            "grip_hex":        grip["hex"] if grip else None,
            "grip_is_klister": grip["is_klister"] if grip else False,
            "glide_product":   glide["product"],
            "glide_hex":       glide["hex"],
        })

    zones = _build_zones(seg_results, discipline)
    stats = course_stats(samples)
    chart_html = _build_course_chart(seg_results, zones, discipline)

    return {
        "segments":   seg_results,
        "zones":      zones,
        "stats":      stats,
        "chart_html": chart_html,
        "canopy":     canopy,
        "discipline": discipline,
        "weather_source": "nws per-segment" if _using_nws else "open-meteo per-point",
    }


def _build_zones(segments: list[dict], discipline: str) -> list[dict]:
    """Group consecutive segments with the same wax call into zones."""
    if not segments:
        return []

    zones = []
    key_field = "grip_product" if discipline == "Classic" else "glide_product"
    color_field = "grip_hex" if discipline == "Classic" else "glide_hex"

    current = None
    for s in segments:
        label = s[key_field] or "Glide only"
        color = s[color_field] or "#6b7280"
        if current is None or current["wax"] != label:
            if current:
                zones.append(current)
            current = {
                "wax": label,
                "color": color,
                "start_km": s["dist_km"],
                "end_km": s["dist_km"],
                "is_klister": s.get("grip_is_klister", False),
                "avg_temp_c": s["temp_c"],
                "snow_types": [s["snow_type"]],
                "count": 1,
            }
        else:
            current["end_km"] = s["dist_km"]
            current["avg_temp_c"] = round(
                (current["avg_temp_c"] * current["count"] + s["temp_c"]) / (current["count"] + 1), 1
            )
            current["snow_types"].append(s["snow_type"])
            current["count"] += 1
    if current:
        zones.append(current)

    # Deduplicate snow types list
    for z in zones:
        z["snow_types"] = list(dict.fromkeys(z["snow_types"]))

    return zones


def _build_course_chart(segments: list[dict], zones: list[dict], discipline: str) -> str:
    """Build a Plotly elevation profile chart with wax zone color bands."""
    try:
        import plotly.graph_objects as go

        dists = [s["dist_km"] for s in segments]
        elevs = [s["elevation_m"] for s in segments]
        temps = [s["temp_c"] for s in segments]

        fig = go.Figure()

        # Shade zones as filled rectangles behind the elevation line
        y_min = min(elevs) - 15
        y_max = max(elevs) + 25
        for z in zones:
            fig.add_shape(
                type="rect",
                x0=z["start_km"], x1=z["end_km"],
                y0=y_min, y1=y_max,
                fillcolor=z["color"],
                opacity=0.18,
                line_width=0,
                layer="below",
            )
            # Zone label midpoint
            mid_x = (z["start_km"] + z["end_km"]) / 2
            label = z["wax"]
            if z.get("is_klister"):
                label += " (K)"
            fig.add_annotation(
                x=mid_x, y=y_max - 8,
                text=label,
                showarrow=False,
                font=dict(size=9, color=z["color"]),
                bgcolor="rgba(0,0,0,0.55)",
                borderpad=2,
            )

        # Elevation profile
        fig.add_trace(go.Scatter(
            x=dists, y=elevs,
            mode="lines",
            line=dict(color="#60a5fa", width=2.5),
            fill="tozeroy",
            fillcolor="rgba(96,165,250,0.12)",
            name="Elevation (m)",
            hovertemplate="<b>%{x:.1f} km</b><br>Elev: %{y:.0f} m<extra></extra>",
        ))

        # Temperature overlay (secondary y-axis)
        fig.add_trace(go.Scatter(
            x=dists, y=temps,
            mode="lines",
            line=dict(color="#fb923c", width=1.5, dash="dot"),
            name="Snow surface temp (°C)",
            yaxis="y2",
            hovertemplate="<b>%{x:.1f} km</b><br>Temp: %{y:.1f}°C<extra></extra>",
        ))

        fig.update_layout(
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            font=dict(color="#e5e7eb", size=11),
            margin=dict(l=50, r=60, t=20, b=40),
            height=260,
            legend=dict(
                orientation="h", y=-0.22, x=0.5, xanchor="center",
                bgcolor="rgba(0,0,0,0)",
                font=dict(size=10),
            ),
            xaxis=dict(
                title="Distance (km)",
                gridcolor="rgba(255,255,255,0.08)",
                zerolinecolor="rgba(255,255,255,0.08)",
            ),
            yaxis=dict(
                title="Elevation (m)",
                gridcolor="rgba(255,255,255,0.08)",
                zerolinecolor="rgba(255,255,255,0.08)",
            ),
            yaxis2=dict(
                title="Temp (°C)",
                overlaying="y",
                side="right",
                gridcolor="rgba(255,255,255,0.04)",
                color="#fb923c",
                showgrid=False,
            ),
            hovermode="x unified",
        )

        return fig.to_html(full_html=False, include_plotlyjs="cdn")
    except Exception:
        return ""


def recommend_from_gpx(
    gpx_samples: list[dict],
    discipline: str,
    snow_mode: str,
    tier: str,
    canopy: str = "mixed",
    race_dt: "pd.Timestamp | None" = None,
) -> dict[str, Any]:
    """Full Nordic wax recommendation derived entirely from a GPX track.

    Location and elevation come from the GPX — no venue required.
    Base conditions are fetched from the track's midpoint; then per-segment
    weather is fetched at each sample's actual lat/lon/elevation.
    """
    if not gpx_samples or len(gpx_samples) < 2:
        return {"error": "GPX track is too short (need at least 2 points).", "ok": False}

    # Use the track midpoint for the overall base conditions fetch
    mid = gpx_samples[len(gpx_samples) // 2]
    conditions = get_conditions(mid["lat"], mid["lon"])

    temp_c = conditions["temp_c"]
    humidity_pct = conditions["humidity_pct"]
    recent_snow_mm = conditions["recent_snow_mm"]
    snow_depth_m = conditions["snow_depth_m"]
    wmo_code = conditions["wmo_code"]

    snow_type, snow_reason = classify_snow(
        temp_c, humidity_pct, recent_snow_mm, snow_depth_m, wmo_code, snow_mode
    )
    glide = select_glide_wax(temp_c, humidity_pct, tier)

    result: dict[str, Any] = {
        "ok": True,
        "venue": None,
        "discipline": discipline,
        "conditions": {
            "temp_c": round(temp_c, 1),
            "temp_f": round(temp_c * 9 / 5 + 32, 1),
            "humidity_pct": humidity_pct,
            "wind_kmh": round(conditions.get("wind_kmh", 0.0), 1),
            "snow_depth_m": round(snow_depth_m, 2),
            "recent_snow_mm": round(recent_snow_mm, 1),
            "weather_ok": conditions.get("ok", False),
        },
        "snow_type": snow_type,
        "snow_reason": snow_reason,
        "glide": glide,
        "canopy": canopy,
    }

    if discipline == "Classic":
        grip = select_grip_wax(temp_c, snow_type)
        result["grip"] = grip
        result["binder"] = select_binder(grip["is_klister"])
        result["confidence"] = round(0.55 * grip["confidence"] + 0.45 * glide["confidence"], 2)
    else:
        result["grip"] = None
        result["binder"] = None
        result["confidence"] = round(glide["confidence"], 2)

    c = result["confidence"]
    if c >= 0.80:
        result["confidence_label"] = "High"
        result["confidence_color"] = "#16a34a"
    elif c >= 0.60:
        result["confidence_label"] = "Medium"
        result["confidence_color"] = "#d97706"
    else:
        result["confidence_label"] = "Low"
        result["confidence_color"] = "#dc2626"

    # Per-segment course analysis with real weather at each point
    course_data = analyze_course(
        gpx_samples,
        conditions,
        discipline,
        canopy,
        snow_mode,
        tier,
        mid["elevation_m"],
        race_dt=race_dt,
    )
    result["course"] = course_data

    # Aggregate snow surface temps across all segments for the summary card
    segs = course_data.get("segments", [])
    if segs:
        snow_temps = [s["temp_c"] for s in segs]
        result["snow_temp_c"]     = round(sum(snow_temps) / len(snow_temps), 1)
        result["snow_temp_min_c"] = round(min(snow_temps), 1)
        result["snow_temp_max_c"] = round(max(snow_temps), 1)
    else:
        result["snow_temp_c"]     = None
        result["snow_temp_min_c"] = None
        result["snow_temp_max_c"] = None

    return result
