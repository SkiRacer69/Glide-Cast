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
    "Mount Snow": {
        "display_name": "Mount Snow Wax Tool",
        "course_name": "Mount Snow Race Venue",
        "lat": 42.9583,
        "lon": -72.8981,
        "elev_ft": 3600,
        "aspect_deg": 71.3,
        "slope_deg": 18.0,
        "finish_ft": 1900,
        "starts_ft": {"SL": 3300, "GS": 3600, "SuperG": 3600},
        "points": {
            "Upper NWS point": {"lat": 42.9583, "lon": -72.8981, "elev_ft": 3600},
            "Lower NWS point": {"lat": 42.9583, "lon": -72.8981, "elev_ft": 1900},
        },
    },
    "Alyeska Resort": {
        "display_name": "Alyeska Resort Wax Tool",
        "course_name": "Alyeska Resort Race Venue",
        "lat": 60.9703,
        "lon": -149.0987,
        "elev_ft": 2740,
        "aspect_deg": 281.5,
        "slope_deg": 18.0,
        "finish_ft": 299,
        "starts_ft": {
            "GS": 2740,
            "SL": 2625,
            "DH": 2740,
            "SuperG": 2740
        },
        "points": {
            "Upper NWS point": {"lat": 60.9703, "lon": -149.0987, "elev_ft": 2740},
            "Lower NWS point": {"lat": 60.9739, "lon": -149.135, "elev_ft": 299},
        },
    },
    "Arctic Valley Ski Area": {
        "display_name": "Arctic Valley Ski Area Wax Tool",
        "course_name": "Arctic Valley Ski Area Race Venue",
        "lat": 61.2477,
        "lon": -149.5204,
        "elev_ft": 3599,
        "aspect_deg": 281.6,
        "slope_deg": 18.0,
        "finish_ft": 2667,
        "starts_ft": {
            "SL": 3323,
            "GS": 3599
        },
        "points": {
            "Upper NWS point": {"lat": 61.2477, "lon": -149.5204, "elev_ft": 3599},
            "Lower NWS point": {"lat": 61.2513, "lon": -149.5571, "elev_ft": 2667},
        },
    },
    "Arizona Snowbowl": {
        "display_name": "Arizona Snowbowl Wax Tool",
        "course_name": "Arizona Snowbowl Race Venue",
        "lat": 35.33,
        "lon": -111.7053,
        "elev_ft": 10325,
        "aspect_deg": 275.8,
        "slope_deg": 18.0,
        "finish_ft": 9669,
        "starts_ft": {
            "GS": 10325,
            "SL": 10128
        },
        "points": {
            "Upper NWS point": {"lat": 35.33, "lon": -111.7053, "elev_ft": 10325},
            "Lower NWS point": {"lat": 35.3318, "lon": -111.7273, "elev_ft": 9669},
        },
    },
    "Aspen Mountain": {
        "display_name": "Aspen Mountain Wax Tool",
        "course_name": "Aspen Mountain Race Venue",
        "lat": 39.1513,
        "lon": -106.8197,
        "elev_ft": 10650,
        "aspect_deg": 20.6,
        "slope_deg": 18.0,
        "finish_ft": 8081,
        "starts_ft": {
            "SL": 9646,
            "SuperG": 10033,
            "DH": 10650,
            "GS": 9557
        },
        "points": {
            "Upper NWS point": {"lat": 39.1513, "lon": -106.8197, "elev_ft": 10650},
            "Lower NWS point": {"lat": 39.1681, "lon": -106.8115, "elev_ft": 8081},
        },
    },
    "Aspen/Buttermilk": {
        "display_name": "Aspen/Buttermilk Wax Tool",
        "course_name": "Aspen/Buttermilk Race Venue",
        "lat": 39.2056,
        "lon": -106.8599,
        "elev_ft": 9682,
        "aspect_deg": 22.5,
        "slope_deg": 18.0,
        "finish_ft": 8205,
        "starts_ft": {
            "SL": 8911,
            "GS": 9337,
            "SuperG": 9682,
            "DH": 9682
        },
        "points": {
            "Upper NWS point": {"lat": 39.2056, "lon": -106.8599, "elev_ft": 9682},
            "Lower NWS point": {"lat": 39.2222, "lon": -106.851, "elev_ft": 8205},
        },
    },
    "Aspen/Highlands": {
        "display_name": "Aspen/Highlands Wax Tool",
        "course_name": "Aspen/Highlands Race Venue",
        "lat": 39.1553,
        "lon": -106.8691,
        "elev_ft": 9672,
        "aspect_deg": 17.2,
        "slope_deg": 18.0,
        "finish_ft": 8140,
        "starts_ft": {
            "SL": 9544,
            "GS": 9580,
            "DH": 9672,
            "SuperG": 9672
        },
        "points": {
            "Upper NWS point": {"lat": 39.1553, "lon": -106.8691, "elev_ft": 9672},
            "Lower NWS point": {"lat": 39.1725, "lon": -106.8622, "elev_ft": 8140},
        },
    },
    "Attitash Ski Area": {
        "display_name": "Attitash Ski Area Wax Tool",
        "course_name": "Attitash Ski Area Race Venue",
        "lat": 44.0855,
        "lon": -71.2244,
        "elev_ft": 1969,
        "aspect_deg": 30.0,
        "slope_deg": 18.0,
        "finish_ft": 774,
        "starts_ft": {
            "GS": 1969,
            "SL": 1850,
            "SuperG": 1969
        },
        "points": {
            "Upper NWS point": {"lat": 44.0855, "lon": -71.2244, "elev_ft": 1969},
            "Lower NWS point": {"lat": 44.1011, "lon": -71.2119, "elev_ft": 774},
        },
    },
    "Bear Canyon": {
        "display_name": "Bear Canyon Wax Tool",
        "course_name": "Bear Canyon Race Venue",
        "lat": 45.6417,
        "lon": -110.9427,
        "elev_ft": 6102,
        "aspect_deg": 350.9,
        "slope_deg": 18.0,
        "finish_ft": 5512,
        "starts_ft": {
            "SL": 6102
        },
        "points": {
            "Upper NWS point": {"lat": 45.6417, "lon": -110.9427, "elev_ft": 6102},
            "Lower NWS point": {"lat": 45.6595, "lon": -110.9468, "elev_ft": 5512},
        },
    },
    "Beaver Creek Resort": {
        "display_name": "Beaver Creek Resort Wax Tool",
        "course_name": "Beaver Creek Resort Race Venue",
        "lat": 39.6034,
        "lon": -106.5157,
        "elev_ft": 11427,
        "aspect_deg": 359.5,
        "slope_deg": 18.0,
        "finish_ft": 8199,
        "starts_ft": {
            "SL": 9629,
            "GS": 10351,
            "SuperG": 10948,
            "DH": 11427
        },
        "points": {
            "Upper NWS point": {"lat": 39.6034, "lon": -106.5157, "elev_ft": 11427},
            "Lower NWS point": {"lat": 39.6214, "lon": -106.5159, "elev_ft": 8199},
        },
    },
    "Belleayre Mountain": {
        "display_name": "Belleayre Mountain Wax Tool",
        "course_name": "Belleayre Mountain Race Venue",
        "lat": 42.1269,
        "lon": -74.4741,
        "elev_ft": 3428,
        "aspect_deg": 31.4,
        "slope_deg": 18.0,
        "finish_ft": 2559,
        "starts_ft": {
            "SL": 3399,
            "GS": 3428
        },
        "points": {
            "Upper NWS point": {"lat": 42.1269, "lon": -74.4741, "elev_ft": 3428},
            "Lower NWS point": {"lat": 42.1423, "lon": -74.4615, "elev_ft": 2559},
        },
    },
    "Berkshire East Mountain Resort": {
        "display_name": "Berkshire East Mountain Resort Wax Tool",
        "course_name": "Berkshire East Mountain Resort Race Venue",
        "lat": 42.6286,
        "lon": -72.9066,
        "elev_ft": 1512,
        "aspect_deg": 329.2,
        "slope_deg": 18.0,
        "finish_ft": 643,
        "starts_ft": {
            "GS": 1512,
            "SL": 1512
        },
        "points": {
            "Upper NWS point": {"lat": 42.6286, "lon": -72.9066, "elev_ft": 1512},
            "Lower NWS point": {"lat": 42.6441, "lon": -72.9191, "elev_ft": 643},
        },
    },
    "Big Sky": {
        "display_name": "Big Sky Wax Tool",
        "course_name": "Big Sky Race Venue",
        "lat": 45.2551,
        "lon": -111.2662,
        "elev_ft": 8665,
        "aspect_deg": 38.0,
        "slope_deg": 18.0,
        "finish_ft": 7165,
        "starts_ft": {
            "DH": 8665,
            "SuperG": 8665,
            "GS": 8661,
            "SL": 8596
        },
        "points": {
            "Upper NWS point": {"lat": 45.2551, "lon": -111.2662, "elev_ft": 8665},
            "Lower NWS point": {"lat": 45.2693, "lon": -111.2505, "elev_ft": 7165},
        },
    },
    "Blue Mountain Resort": {
        "display_name": "Blue Mountain Resort Wax Tool",
        "course_name": "Blue Mountain Resort Race Venue",
        "lat": 40.8167,
        "lon": -75.5098,
        "elev_ft": 1476,
        "aspect_deg": 2.5,
        "slope_deg": 18.0,
        "finish_ft": 623,
        "starts_ft": {
            "GS": 1476
        },
        "points": {
            "Upper NWS point": {"lat": 40.8167, "lon": -75.5098, "elev_ft": 1476},
            "Lower NWS point": {"lat": 40.8347, "lon": -75.5088, "elev_ft": 623},
        },
    },
    "Boreal Mountain Resort": {
        "display_name": "Boreal Mountain Resort Wax Tool",
        "course_name": "Boreal Mountain Resort Race Venue",
        "lat": 39.3361,
        "lon": -120.3502,
        "elev_ft": 7671,
        "aspect_deg": 329.6,
        "slope_deg": 18.0,
        "finish_ft": 7313,
        "starts_ft": {
            "SL": 7671
        },
        "points": {
            "Upper NWS point": {"lat": 39.3361, "lon": -120.3502, "elev_ft": 7671},
            "Lower NWS point": {"lat": 39.3516, "lon": -120.362, "elev_ft": 7313},
        },
    },
    "Boyne Highlands": {
        "display_name": "Boyne Highlands Wax Tool",
        "course_name": "Boyne Highlands Race Venue",
        "lat": 45.477,
        "lon": -84.9454,
        "elev_ft": 1211,
        "aspect_deg": 86.0,
        "slope_deg": 18.0,
        "finish_ft": 814,
        "starts_ft": {
            "SL": 1211
        },
        "points": {
            "Upper NWS point": {"lat": 45.477, "lon": -84.9454, "elev_ft": 1211},
            "Lower NWS point": {"lat": 45.4783, "lon": -84.9198, "elev_ft": 814},
        },
    },
    "Boyne Mountain": {
        "display_name": "Boyne Mountain Wax Tool",
        "course_name": "Boyne Mountain Race Venue",
        "lat": 45.1586,
        "lon": -84.9389,
        "elev_ft": 1145,
        "aspect_deg": 54.7,
        "slope_deg": 18.0,
        "finish_ft": 732,
        "starts_ft": {
            "SL": 1145
        },
        "points": {
            "Upper NWS point": {"lat": 45.1586, "lon": -84.9389, "elev_ft": 1145},
            "Lower NWS point": {"lat": 45.169, "lon": -84.9181, "elev_ft": 732},
        },
    },
    "Breckenridge Ski Resort": {
        "display_name": "Breckenridge Ski Resort Wax Tool",
        "course_name": "Breckenridge Ski Resort Race Venue",
        "lat": 39.4808,
        "lon": -106.0666,
        "elev_ft": 11673,
        "aspect_deg": 44.4,
        "slope_deg": 18.0,
        "finish_ft": 10302,
        "starts_ft": {
            "SL": 11161,
            "GS": 11581,
            "DH": 11673,
            "SuperG": 11673
        },
        "points": {
            "Upper NWS point": {"lat": 39.4808, "lon": -106.0666, "elev_ft": 11673},
            "Lower NWS point": {"lat": 39.4937, "lon": -106.0503, "elev_ft": 10302},
        },
    },
    "Bridger Bowl": {
        "display_name": "Bridger Bowl Wax Tool",
        "course_name": "Bridger Bowl Race Venue",
        "lat": 45.8163,
        "lon": -110.9104,
        "elev_ft": 7815,
        "aspect_deg": 94.3,
        "slope_deg": 18.0,
        "finish_ft": 6627,
        "starts_ft": {
            "GS": 7815,
            "SL": 7382
        },
        "points": {
            "Upper NWS point": {"lat": 45.8163, "lon": -110.9104, "elev_ft": 7815},
            "Lower NWS point": {"lat": 45.815, "lon": -110.8846, "elev_ft": 6627},
        },
    },
    "Buck Hill": {
        "display_name": "Buck Hill Wax Tool",
        "course_name": "Buck Hill Race Venue",
        "lat": 44.7233,
        "lon": -93.2856,
        "elev_ft": 1211,
        "aspect_deg": 68.1,
        "slope_deg": 18.0,
        "finish_ft": 965,
        "starts_ft": {
            "SL": 1211
        },
        "points": {
            "Upper NWS point": {"lat": 44.7233, "lon": -93.2856, "elev_ft": 1211},
            "Lower NWS point": {"lat": 44.73, "lon": -93.2621, "elev_ft": 965},
        },
    },
    "Burke Mountain": {
        "display_name": "Burke Mountain Wax Tool",
        "course_name": "Burke Mountain Race Venue",
        "lat": 44.5705,
        "lon": -71.8928,
        "elev_ft": 3156,
        "aspect_deg": 332.6,
        "slope_deg": 18.0,
        "finish_ft": 1690,
        "starts_ft": {
            "GS": 3025,
            "SL": 2851,
            "SuperG": 3156
        },
        "points": {
            "Upper NWS point": {"lat": 44.5705, "lon": -71.8928, "elev_ft": 3156},
            "Lower NWS point": {"lat": 44.5865, "lon": -71.9044, "elev_ft": 1690},
        },
    },
    "Catamount": {
        "display_name": "Catamount Wax Tool",
        "course_name": "Catamount Race Venue",
        "lat": 44.5834,
        "lon": -74.0893,
        "elev_ft": 1795,
        "aspect_deg": 90.0,
        "slope_deg": 18.0,
        "finish_ft": 938,
        "starts_ft": {
            "SL": 1493,
            "GS": 1795
        },
        "points": {
            "Upper NWS point": {"lat": 44.5834, "lon": -74.0893, "elev_ft": 1795},
            "Lower NWS point": {"lat": 44.5834, "lon": -74.064, "elev_ft": 938},
        },
    },
    "Cochran's Ski Area": {
        "display_name": "Cochran's Ski Area Wax Tool",
        "course_name": "Cochran's Ski Area Race Venue",
        "lat": 44.393,
        "lon": -72.9819,
        "elev_ft": 755,
        "aspect_deg": 261.2,
        "slope_deg": 18.0,
        "finish_ft": 390,
        "starts_ft": {
            "SL": 755
        },
        "points": {
            "Upper NWS point": {"lat": 44.393, "lon": -72.9819, "elev_ft": 755},
            "Lower NWS point": {"lat": 44.3902, "lon": -73.0068, "elev_ft": 390},
        },
    },
    "Copper Mountain": {
        "display_name": "Copper Mountain Wax Tool",
        "course_name": "Copper Mountain Race Venue",
        "lat": 39.4781,
        "lon": -106.1629,
        "elev_ft": 12290,
        "aspect_deg": 9.8,
        "slope_deg": 18.0,
        "finish_ft": 9764,
        "starts_ft": {
            "GS": 12037,
            "SL": 11972,
            "DH": 12290,
            "SuperG": 11929
        },
        "points": {
            "Upper NWS point": {"lat": 39.4781, "lon": -106.1629, "elev_ft": 12290},
            "Lower NWS point": {"lat": 39.4958, "lon": -106.1589, "elev_ft": 9764},
        },
    },
    "Cranmore Mountain Resort": {
        "display_name": "Cranmore Mountain Resort Wax Tool",
        "course_name": "Cranmore Mountain Resort Race Venue",
        "lat": 44.0608,
        "lon": -71.0973,
        "elev_ft": 1542,
        "aspect_deg": 269.8,
        "slope_deg": 18.0,
        "finish_ft": 755,
        "starts_ft": {
            "SL": 1542
        },
        "points": {
            "Upper NWS point": {"lat": 44.0608, "lon": -71.0973, "elev_ft": 1542},
            "Lower NWS point": {"lat": 44.0607, "lon": -71.1223, "elev_ft": 755},
        },
    },
    "Crested Butte Mountain Resort": {
        "display_name": "Crested Butte Mountain Resort Wax Tool",
        "course_name": "Crested Butte Mountain Resort Race Venue",
        "lat": 38.897,
        "lon": -106.9447,
        "elev_ft": 9823,
        "aspect_deg": 20.0,
        "slope_deg": 18.0,
        "finish_ft": 9301,
        "starts_ft": {
            "SL": 9823
        },
        "points": {
            "Upper NWS point": {"lat": 38.897, "lon": -106.9447, "elev_ft": 9823},
            "Lower NWS point": {"lat": 38.9139, "lon": -106.9368, "elev_ft": 9301},
        },
    },
    "Crystal Mountain": {
        "display_name": "Crystal Mountain Wax Tool",
        "course_name": "Crystal Mountain Race Venue",
        "lat": 46.9327,
        "lon": -121.4877,
        "elev_ft": 5479,
        "aspect_deg": 84.5,
        "slope_deg": 18.0,
        "finish_ft": 4459,
        "starts_ft": {
            "SL": 5190,
            "GS": 5479
        },
        "points": {
            "Upper NWS point": {"lat": 46.9327, "lon": -121.4877, "elev_ft": 5479},
            "Lower NWS point": {"lat": 46.9344, "lon": -121.4615, "elev_ft": 4459},
        },
    },
    "Dartmouth Skiway": {
        "display_name": "Dartmouth Skiway Wax Tool",
        "course_name": "Dartmouth Skiway Race Venue",
        "lat": 43.7879,
        "lon": -72.0943,
        "elev_ft": 1890,
        "aspect_deg": 340.4,
        "slope_deg": 18.0,
        "finish_ft": 971,
        "starts_ft": {
            "SL": 1890,
            "GS": 1890
        },
        "points": {
            "Upper NWS point": {"lat": 43.7879, "lon": -72.0943, "elev_ft": 1890},
            "Lower NWS point": {"lat": 43.8049, "lon": -72.1027, "elev_ft": 971},
        },
    },
    "Diamond Peak Ski Resort": {
        "display_name": "Diamond Peak Ski Resort Wax Tool",
        "course_name": "Diamond Peak Ski Resort Race Venue",
        "lat": 39.2428,
        "lon": -119.9338,
        "elev_ft": 8524,
        "aspect_deg": 286.8,
        "slope_deg": 18.0,
        "finish_ft": 6906,
        "starts_ft": {
            "SL": 8399,
            "GS": 8524
        },
        "points": {
            "Upper NWS point": {"lat": 39.2428, "lon": -119.9338, "elev_ft": 8524},
            "Lower NWS point": {"lat": 39.248, "lon": -119.956, "elev_ft": 6906},
        },
    },
    "Eldora": {
        "display_name": "Eldora Wax Tool",
        "course_name": "Eldora Race Venue",
        "lat": 39.9569,
        "lon": -105.5829,
        "elev_ft": 10315,
        "aspect_deg": 61.9,
        "slope_deg": 18.0,
        "finish_ft": 9442,
        "starts_ft": {
            "SL": 10207,
            "GS": 10315
        },
        "points": {
            "Upper NWS point": {"lat": 39.9569, "lon": -105.5829, "elev_ft": 10315},
            "Lower NWS point": {"lat": 39.9654, "lon": -105.5622, "elev_ft": 9442},
        },
    },
    "Giants Ridge": {
        "display_name": "Giants Ridge Wax Tool",
        "course_name": "Giants Ridge Race Venue",
        "lat": 47.5714,
        "lon": -92.314,
        "elev_ft": 1844,
        "aspect_deg": 46.6,
        "slope_deg": 18.0,
        "finish_ft": 1414,
        "starts_ft": {
            "SL": 1844
        },
        "points": {
            "Upper NWS point": {"lat": 47.5714, "lon": -92.314, "elev_ft": 1844},
            "Lower NWS point": {"lat": 47.5838, "lon": -92.2946, "elev_ft": 1414},
        },
    },
    "Grand Targhee": {
        "display_name": "Grand Targhee Wax Tool",
        "course_name": "Grand Targhee Race Venue",
        "lat": 43.785,
        "lon": -110.947,
        "elev_ft": 9495,
        "aspect_deg": 264.2,
        "slope_deg": 18.0,
        "finish_ft": 8077,
        "starts_ft": {
            "SuperG": 9495,
            "SL": 8711,
            "GS": 8934
        },
        "points": {
            "Upper NWS point": {"lat": 43.785, "lon": -110.947, "elev_ft": 9495},
            "Lower NWS point": {"lat": 43.7832, "lon": -110.9718, "elev_ft": 8077},
        },
    },
    "Greek Peak": {
        "display_name": "Greek Peak Wax Tool",
        "course_name": "Greek Peak Race Venue",
        "lat": 42.4965,
        "lon": -76.1498,
        "elev_ft": 2034,
        "aspect_deg": 90.0,
        "slope_deg": 18.0,
        "finish_ft": 1545,
        "starts_ft": {
            "SL": 2034
        },
        "points": {
            "Upper NWS point": {"lat": 42.4965, "lon": -76.1498, "elev_ft": 2034},
            "Lower NWS point": {"lat": 42.4965, "lon": -76.1254, "elev_ft": 1545},
        },
    },
    "Heavenly Mountain Resort": {
        "display_name": "Heavenly Mountain Resort Wax Tool",
        "course_name": "Heavenly Mountain Resort Race Venue",
        "lat": 38.9405,
        "lon": -119.8974,
        "elev_ft": 9459,
        "aspect_deg": 355.0,
        "slope_deg": 18.0,
        "finish_ft": 8264,
        "starts_ft": {
            "SL": 9245,
            "GS": 9459
        },
        "points": {
            "Upper NWS point": {"lat": 38.9405, "lon": -119.8974, "elev_ft": 9459},
            "Lower NWS point": {"lat": 38.9584, "lon": -119.8994, "elev_ft": 8264},
        },
    },
    "Hogadon Ski Area": {
        "display_name": "Hogadon Ski Area Wax Tool",
        "course_name": "Hogadon Ski Area Race Venue",
        "lat": 42.7466,
        "lon": -106.3407,
        "elev_ft": 7897,
        "aspect_deg": 10.0,
        "slope_deg": 18.0,
        "finish_ft": 7382,
        "starts_ft": {
            "SL": 7897
        },
        "points": {
            "Upper NWS point": {"lat": 42.7466, "lon": -106.3407, "elev_ft": 7897},
            "Lower NWS point": {"lat": 42.7643, "lon": -106.3364, "elev_ft": 7382},
        },
    },
    "Holiday Valley Resort": {
        "display_name": "Holiday Valley Resort Wax Tool",
        "course_name": "Holiday Valley Resort Race Venue",
        "lat": 42.2631,
        "lon": -78.6636,
        "elev_ft": 2254,
        "aspect_deg": 20.3,
        "slope_deg": 18.0,
        "finish_ft": 1788,
        "starts_ft": {
            "SL": 2254
        },
        "points": {
            "Upper NWS point": {"lat": 42.2631, "lon": -78.6636, "elev_ft": 2254},
            "Lower NWS point": {"lat": 42.28, "lon": -78.6552, "elev_ft": 1788},
        },
    },
    "Indianhead Mt": {
        "display_name": "Indianhead Mt Wax Tool",
        "course_name": "Indianhead Mt Race Venue",
        "lat": 46.5093,
        "lon": -89.9799,
        "elev_ft": 1693,
        "aspect_deg": 11.1,
        "slope_deg": 18.0,
        "finish_ft": 1220,
        "starts_ft": {
            "SL": 1693
        },
        "points": {
            "Upper NWS point": {"lat": 46.5093, "lon": -89.9799, "elev_ft": 1693},
            "Lower NWS point": {"lat": 46.527, "lon": -89.9749, "elev_ft": 1220},
        },
    },
    "Jackson Hole": {
        "display_name": "Jackson Hole Wax Tool",
        "course_name": "Jackson Hole Race Venue",
        "lat": 43.6088,
        "lon": -110.738,
        "elev_ft": 9016,
        "aspect_deg": 60.0,
        "slope_deg": 18.0,
        "finish_ft": 6283,
        "starts_ft": {
            "SL": 8825,
            "GS": 8825,
            "DH": 9016,
            "SuperG": 9016
        },
        "points": {
            "Upper NWS point": {"lat": 43.6088, "lon": -110.738, "elev_ft": 9016},
            "Lower NWS point": {"lat": 43.6178, "lon": -110.7165, "elev_ft": 6283},
        },
    },
    "Jay Peak Resort": {
        "display_name": "Jay Peak Resort Wax Tool",
        "course_name": "Jay Peak Resort Race Venue",
        "lat": 44.936,
        "lon": -72.5079,
        "elev_ft": 2854,
        "aspect_deg": 53.3,
        "slope_deg": 18.0,
        "finish_ft": 2028,
        "starts_ft": {
            "SL": 2854,
            "GS": 2854
        },
        "points": {
            "Upper NWS point": {"lat": 44.936, "lon": -72.5079, "elev_ft": 2854},
            "Lower NWS point": {"lat": 44.9468, "lon": -72.4875, "elev_ft": 2028},
        },
    },
    "Jiminy Peak Ski Area": {
        "display_name": "Jiminy Peak Ski Area Wax Tool",
        "course_name": "Jiminy Peak Ski Area Race Venue",
        "lat": 42.6953,
        "lon": -73.2694,
        "elev_ft": 2356,
        "aspect_deg": 6.3,
        "slope_deg": 18.0,
        "finish_ft": 1453,
        "starts_ft": {
            "SL": 2165,
            "GS": 2356
        },
        "points": {
            "Upper NWS point": {"lat": 42.6953, "lon": -73.2694, "elev_ft": 2356},
            "Lower NWS point": {"lat": 42.7132, "lon": -73.2667, "elev_ft": 1453},
        },
    },
    "Keystone Ski Resort": {
        "display_name": "Keystone Ski Resort Wax Tool",
        "course_name": "Keystone Ski Resort Race Venue",
        "lat": 39.6069,
        "lon": -105.9681,
        "elev_ft": 11624,
        "aspect_deg": 335.8,
        "slope_deg": 18.0,
        "finish_ft": 9288,
        "starts_ft": {
            "SL": 10784,
            "GS": 11624
        },
        "points": {
            "Upper NWS point": {"lat": 39.6069, "lon": -105.9681, "elev_ft": 11624},
            "Lower NWS point": {"lat": 39.6233, "lon": -105.9777, "elev_ft": 9288},
        },
    },
    "Killington": {
        "display_name": "Killington Wax Tool",
        "course_name": "Killington Race Venue",
        "lat": 43.6743,
        "lon": -72.7784,
        "elev_ft": 3714,
        "aspect_deg": 55.2,
        "slope_deg": 18.0,
        "finish_ft": 2438,
        "starts_ft": {
            "SL": 3320,
            "GS": 3714
        },
        "points": {
            "Upper NWS point": {"lat": 43.6743, "lon": -72.7784, "elev_ft": 3714},
            "Lower NWS point": {"lat": 43.6743, "lon": -72.7784, "elev_ft": 2438},
        },
    },
    "La Crosse": {
        "display_name": "La Crosse Wax Tool",
        "course_name": "La Crosse Race Venue",
        "lat": 43.8123,
        "lon": -91.2514,
        "elev_ft": 1211,
        "aspect_deg": 18.8,
        "slope_deg": 18.0,
        "finish_ft": 751,
        "starts_ft": {
            "SL": 1211
        },
        "points": {
            "Upper NWS point": {"lat": 43.8123, "lon": -91.2514, "elev_ft": 1211},
            "Lower NWS point": {"lat": 43.8293, "lon": -91.2434, "elev_ft": 751},
        },
    },
    "Loon Mountain Resort": {
        "display_name": "Loon Mountain Resort Wax Tool",
        "course_name": "Loon Mountain Resort Race Venue",
        "lat": 44.0451,
        "lon": -71.6366,
        "elev_ft": 1991,
        "aspect_deg": 350.0,
        "slope_deg": 18.0,
        "finish_ft": 1030,
        "starts_ft": {
            "SL": 1991,
            "GS": 1991
        },
        "points": {
            "Upper NWS point": {"lat": 44.0451, "lon": -71.6366, "elev_ft": 1991},
            "Lower NWS point": {"lat": 44.0628, "lon": -71.6409, "elev_ft": 1030},
        },
    },
    "Loveland Valley": {
        "display_name": "Loveland Valley Wax Tool",
        "course_name": "Loveland Valley Race Venue",
        "lat": 39.6816,
        "lon": -105.8774,
        "elev_ft": 11893,
        "aspect_deg": 340.0,
        "slope_deg": 18.0,
        "finish_ft": 10636,
        "starts_ft": {
            "SL": 11617,
            "GS": 11893
        },
        "points": {
            "Upper NWS point": {"lat": 39.6816, "lon": -105.8774, "elev_ft": 11893},
            "Lower NWS point": {"lat": 39.6985, "lon": -105.8854, "elev_ft": 10636},
        },
    },
    "Lutsen Mountain": {
        "display_name": "Lutsen Mountain Wax Tool",
        "course_name": "Lutsen Mountain Race Venue",
        "lat": 47.6575,
        "lon": -90.7114,
        "elev_ft": 1693,
        "aspect_deg": 122.1,
        "slope_deg": 18.0,
        "finish_ft": 850,
        "starts_ft": {
            "GS": 1693,
            "SL": 1693
        },
        "points": {
            "Upper NWS point": {"lat": 47.6575, "lon": -90.7114, "elev_ft": 1693},
            "Lower NWS point": {"lat": 47.6479, "lon": -90.6888, "elev_ft": 850},
        },
    },
    "Magic Mountain": {
        "display_name": "Magic Mountain Wax Tool",
        "course_name": "Magic Mountain Race Venue",
        "lat": 43.1955,
        "lon": -72.764,
        "elev_ft": 2454,
        "aspect_deg": 321.6,
        "slope_deg": 18.0,
        "finish_ft": 1706,
        "starts_ft": {
            "SL": 2454
        },
        "points": {
            "Upper NWS point": {"lat": 43.1955, "lon": -72.764, "elev_ft": 2454},
            "Lower NWS point": {"lat": 43.2096, "lon": -72.7793, "elev_ft": 1706},
        },
    },
    "Mammoth Mountain": {
        "display_name": "Mammoth Mountain Wax Tool",
        "course_name": "Mammoth Mountain Race Venue",
        "lat": 37.6308,
        "lon": -119.0326,
        "elev_ft": 11020,
        "aspect_deg": 17.0,
        "slope_deg": 18.0,
        "finish_ft": 8737,
        "starts_ft": {
            "SL": 10249,
            "GS": 10978,
            "DH": 11020,
            "SuperG": 11020
        },
        "points": {
            "Upper NWS point": {"lat": 37.6308, "lon": -119.0326, "elev_ft": 11020},
            "Lower NWS point": {"lat": 37.648, "lon": -119.026, "elev_ft": 8737},
        },
    },
    "Maverick Mt": {
        "display_name": "Maverick Mt Wax Tool",
        "course_name": "Maverick Mt Race Venue",
        "lat": 45.4485,
        "lon": -113.1631,
        "elev_ft": 8399,
        "aspect_deg": 108.2,
        "slope_deg": 18.0,
        "finish_ft": 7018,
        "starts_ft": {
            "SL": 7359,
            "GS": 8399
        },
        "points": {
            "Upper NWS point": {"lat": 45.4485, "lon": -113.1631, "elev_ft": 8399},
            "Lower NWS point": {"lat": 45.4429, "lon": -113.1387, "elev_ft": 7018},
        },
    },
    "Middlebury College Snow Bowl": {
        "display_name": "Middlebury College Snow Bowl Wax Tool",
        "course_name": "Middlebury College Snow Bowl Race Venue",
        "lat": 43.9345,
        "lon": -72.9569,
        "elev_ft": 2648,
        "aspect_deg": 44.2,
        "slope_deg": 18.0,
        "finish_ft": 1827,
        "starts_ft": {
            "SL": 2552,
            "GS": 2648
        },
        "points": {
            "Upper NWS point": {"lat": 43.9345, "lon": -72.9569, "elev_ft": 2648},
            "Lower NWS point": {"lat": 43.9474, "lon": -72.9395, "elev_ft": 1827},
        },
    },
    "Mission Ridge": {
        "display_name": "Mission Ridge Wax Tool",
        "course_name": "Mission Ridge Race Venue",
        "lat": 47.3474,
        "lon": -120.4842,
        "elev_ft": 6742,
        "aspect_deg": 90.0,
        "slope_deg": 18.0,
        "finish_ft": 4587,
        "starts_ft": {
            "SL": 6224,
            "DH": 6601,
            "GS": 6414,
            "SuperG": 6742
        },
        "points": {
            "Upper NWS point": {"lat": 47.3474, "lon": -120.4842, "elev_ft": 6742},
            "Lower NWS point": {"lat": 47.3474, "lon": -120.4576, "elev_ft": 4587},
        },
    },
    "Mittersill Cannon Mtn": {
        "display_name": "Mittersill Cannon Mtn Wax Tool",
        "course_name": "Mittersill Cannon Mtn Race Venue",
        "lat": 44.1581,
        "lon": -71.7014,
        "elev_ft": 3077,
        "aspect_deg": 2.1,
        "slope_deg": 18.0,
        "finish_ft": 1877,
        "starts_ft": {
            "GS": 3077,
            "SL": 2638
        },
        "points": {
            "Upper NWS point": {"lat": 44.1581, "lon": -71.7014, "elev_ft": 3077},
            "Lower NWS point": {"lat": 44.1761, "lon": -71.7005, "elev_ft": 1877},
        },
    },
    "Mont Ripley": {
        "display_name": "Mont Ripley Wax Tool",
        "course_name": "Mont Ripley Race Venue",
        "lat": 47.1303,
        "lon": -88.5596,
        "elev_ft": 1073,
        "aspect_deg": 182.5,
        "slope_deg": 18.0,
        "finish_ft": 666,
        "starts_ft": {
            "SL": 1073
        },
        "points": {
            "Upper NWS point": {"lat": 47.1303, "lon": -88.5596, "elev_ft": 1073},
            "Lower NWS point": {"lat": 47.1123, "lon": -88.5608, "elev_ft": 666},
        },
    },
    "Mount Bachelor": {
        "display_name": "Mount Bachelor Wax Tool",
        "course_name": "Mount Bachelor Race Venue",
        "lat": 43.9794,
        "lon": -121.6885,
        "elev_ft": 9055,
        "aspect_deg": 14.0,
        "slope_deg": 18.0,
        "finish_ft": 6211,
        "starts_ft": {
            "GS": 7736,
            "SL": 7169,
            "SuperG": 8612,
            "DH": 9055
        },
        "points": {
            "Upper NWS point": {"lat": 43.9794, "lon": -121.6885, "elev_ft": 9055},
            "Lower NWS point": {"lat": 43.9969, "lon": -121.6824, "elev_ft": 6211},
        },
    },
    "Mount Spokane": {
        "display_name": "Mount Spokane Wax Tool",
        "course_name": "Mount Spokane Race Venue",
        "lat": 47.9213,
        "lon": -117.1141,
        "elev_ft": 5410,
        "aspect_deg": 85.4,
        "slope_deg": 18.0,
        "finish_ft": 4334,
        "starts_ft": {
            "GS": 5410,
            "SL": 4990
        },
        "points": {
            "Upper NWS point": {"lat": 47.9213, "lon": -117.1141, "elev_ft": 5410},
            "Lower NWS point": {"lat": 47.9227, "lon": -117.0873, "elev_ft": 4334},
        },
    },
    "Mount Sunapee": {
        "display_name": "Mount Sunapee Wax Tool",
        "course_name": "Mount Sunapee Race Venue",
        "lat": 43.3406,
        "lon": -72.0709,
        "elev_ft": 2231,
        "aspect_deg": 346.6,
        "slope_deg": 18.0,
        "finish_ft": 1312,
        "starts_ft": {
            "GS": 2231,
            "SL": 2231
        },
        "points": {
            "Upper NWS point": {"lat": 43.3406, "lon": -72.0709, "elev_ft": 2231},
            "Lower NWS point": {"lat": 43.3581, "lon": -72.0766, "elev_ft": 1312},
        },
    },
    "Mt Hood Meadows": {
        "display_name": "Mt Hood Meadows Wax Tool",
        "course_name": "Mt Hood Meadows Race Venue",
        "lat": 45.4746,
        "lon": -122.3717,
        "elev_ft": 6539,
        "aspect_deg": 173.2,
        "slope_deg": 18.0,
        "finish_ft": 5390,
        "starts_ft": {
            "GS": 6539,
            "SL": 6430
        },
        "points": {
            "Upper NWS point": {"lat": 45.4746, "lon": -122.3717, "elev_ft": 6539},
            "Lower NWS point": {"lat": 45.4567, "lon": -122.3687, "elev_ft": 5390},
        },
    },
    "Mt Hood Skibowl": {
        "display_name": "Mt Hood Skibowl Wax Tool",
        "course_name": "Mt Hood Skibowl Race Venue",
        "lat": 45.294,
        "lon": -121.7805,
        "elev_ft": 6539,
        "aspect_deg": 191.4,
        "slope_deg": 18.0,
        "finish_ft": 3675,
        "starts_ft": {
            "SL": 6539,
            "GS": 6539
        },
        "points": {
            "Upper NWS point": {"lat": 45.294, "lon": -121.7805, "elev_ft": 6539},
            "Lower NWS point": {"lat": 45.2764, "lon": -121.7856, "elev_ft": 3675},
        },
    },
    "Mt Rose Ski Tahoe": {
        "display_name": "Mt Rose Ski Tahoe Wax Tool",
        "course_name": "Mt Rose Ski Tahoe Race Venue",
        "lat": 39.3192,
        "lon": -119.8837,
        "elev_ft": 9531,
        "aspect_deg": 7.6,
        "slope_deg": 18.0,
        "finish_ft": 8346,
        "starts_ft": {
            "SL": 9101,
            "GS": 9531,
            "SuperG": 9531
        },
        "points": {
            "Upper NWS point": {"lat": 39.3192, "lon": -119.8837, "elev_ft": 9531},
            "Lower NWS point": {"lat": 39.337, "lon": -119.8806, "elev_ft": 8346},
        },
    },
    "Northstar California": {
        "display_name": "Northstar California Wax Tool",
        "course_name": "Northstar California Race Venue",
        "lat": 39.2745,
        "lon": -120.1218,
        "elev_ft": 8038,
        "aspect_deg": 3.2,
        "slope_deg": 18.0,
        "finish_ft": 6890,
        "starts_ft": {
            "GS": 8038,
            "SuperG": 7940,
            "SL": 7612
        },
        "points": {
            "Upper NWS point": {"lat": 39.2745, "lon": -120.1218, "elev_ft": 8038},
            "Lower NWS point": {"lat": 39.2925, "lon": -120.1205, "elev_ft": 6890},
        },
    },
    "Okemo Mountain": {
        "display_name": "Okemo Mountain Wax Tool",
        "course_name": "Okemo Mountain Race Venue",
        "lat": 43.4078,
        "lon": -72.7343,
        "elev_ft": 3130,
        "aspect_deg": 94.7,
        "slope_deg": 18.0,
        "finish_ft": 1608,
        "starts_ft": {
            "GS": 3130,
            "SuperG": 3130,
            "SL": 3130
        },
        "points": {
            "Upper NWS point": {"lat": 43.4078, "lon": -72.7343, "elev_ft": 3130},
            "Lower NWS point": {"lat": 43.4063, "lon": -72.7096, "elev_ft": 1608},
        },
    },
    "Palisades Tahoe": {
        "display_name": "Palisades Tahoe Wax Tool",
        "course_name": "Palisades Tahoe Race Venue",
        "lat": 39.1966,
        "lon": -120.2345,
        "elev_ft": 8694,
        "aspect_deg": 34.1,
        "slope_deg": 18.0,
        "finish_ft": 6253,
        "starts_ft": {
            "SL": 8694,
            "GS": 8346,
            "SuperG": 8510,
            "DH": 8510
        },
        "points": {
            "Upper NWS point": {"lat": 39.1966, "lon": -120.2345, "elev_ft": 8694},
            "Lower NWS point": {"lat": 39.2115, "lon": -120.2215, "elev_ft": 6253},
        },
    },
    "Park City Mountain Resort": {
        "display_name": "Park City Mountain Resort Wax Tool",
        "course_name": "Park City Mountain Resort Race Venue",
        "lat": 40.6541,
        "lon": -111.5624,
        "elev_ft": 8153,
        "aspect_deg": 28.8,
        "slope_deg": 18.0,
        "finish_ft": 6929,
        "starts_ft": {
            "GS": 8153,
            "SL": 7618,
            "SuperG": 8153
        },
        "points": {
            "Upper NWS point": {"lat": 40.6541, "lon": -111.5624, "elev_ft": 8153},
            "Lower NWS point": {"lat": 40.6699, "lon": -111.551, "elev_ft": 6929},
        },
    },
    "Pats Peak Ski Area": {
        "display_name": "Pats Peak Ski Area Wax Tool",
        "course_name": "Pats Peak Ski Area Race Venue",
        "lat": 43.1422,
        "lon": -71.5978,
        "elev_ft": 1283,
        "aspect_deg": 347.0,
        "slope_deg": 18.0,
        "finish_ft": 735,
        "starts_ft": {
            "SL": 1283
        },
        "points": {
            "Upper NWS point": {"lat": 43.1422, "lon": -71.5978, "elev_ft": 1283},
            "Lower NWS point": {"lat": 43.1597, "lon": -71.6033, "elev_ft": 735},
        },
    },
    "Pico Peak": {
        "display_name": "Pico Peak Wax Tool",
        "course_name": "Pico Peak Race Venue",
        "lat": 43.6394,
        "lon": -72.8364,
        "elev_ft": 2805,
        "aspect_deg": 350.0,
        "slope_deg": 18.0,
        "finish_ft": 2320,
        "starts_ft": {
            "SL": 2805
        },
        "points": {
            "Upper NWS point": {"lat": 43.6394, "lon": -72.8364, "elev_ft": 2805},
            "Lower NWS point": {"lat": 43.6571, "lon": -72.8407, "elev_ft": 2320},
        },
    },
    "Powderhorn": {
        "display_name": "Powderhorn Wax Tool",
        "course_name": "Powderhorn Race Venue",
        "lat": 38.2769,
        "lon": -107.0959,
        "elev_ft": 9642,
        "aspect_deg": 30.0,
        "slope_deg": 18.0,
        "finish_ft": 8451,
        "starts_ft": {
            "GS": 9642,
            "SL": 8976
        },
        "points": {
            "Upper NWS point": {"lat": 38.2769, "lon": -107.0959, "elev_ft": 9642},
            "Lower NWS point": {"lat": 38.2925, "lon": -107.0844, "elev_ft": 8451},
        },
    },
    "Proctor Ski Area": {
        "display_name": "Proctor Ski Area Wax Tool",
        "course_name": "Proctor Ski Area Race Venue",
        "lat": 43.4306,
        "lon": -71.8295,
        "elev_ft": 1083,
        "aspect_deg": 15.0,
        "slope_deg": 18.0,
        "finish_ft": 620,
        "starts_ft": {
            "SL": 1083
        },
        "points": {
            "Upper NWS point": {"lat": 43.4306, "lon": -71.8295, "elev_ft": 1083},
            "Lower NWS point": {"lat": 43.448, "lon": -71.8231, "elev_ft": 620},
        },
    },
    "Saddleback": {
        "display_name": "Saddleback Wax Tool",
        "course_name": "Saddleback Race Venue",
        "lat": 44.9789,
        "lon": -70.5194,
        "elev_ft": 3602,
        "aspect_deg": 328.7,
        "slope_deg": 18.0,
        "finish_ft": 2677,
        "starts_ft": {
            "SL": 3179,
            "GS": 3602
        },
        "points": {
            "Upper NWS point": {"lat": 44.9789, "lon": -70.5194, "elev_ft": 3602},
            "Lower NWS point": {"lat": 44.9943, "lon": -70.5326, "elev_ft": 2677},
        },
    },
    "Schweitzer Mtn": {
        "display_name": "Schweitzer Mtn Wax Tool",
        "course_name": "Schweitzer Mtn Race Venue",
        "lat": 48.368,
        "lon": -116.6232,
        "elev_ft": 5761,
        "aspect_deg": 58.5,
        "slope_deg": 18.0,
        "finish_ft": 4035,
        "starts_ft": {
            "SL": 5761,
            "GS": 5390,
            "DH": 5538,
            "SuperG": 5538
        },
        "points": {
            "Upper NWS point": {"lat": 48.368, "lon": -116.6232, "elev_ft": 5761},
            "Lower NWS point": {"lat": 48.3774, "lon": -116.6001, "elev_ft": 4035},
        },
    },
    "Smugglers Notch Resort": {
        "display_name": "Smugglers Notch Resort Wax Tool",
        "course_name": "Smugglers Notch Resort Race Venue",
        "lat": 44.5727,
        "lon": -72.7676,
        "elev_ft": 2546,
        "aspect_deg": 346.0,
        "slope_deg": 18.0,
        "finish_ft": 1680,
        "starts_ft": {
            "GS": 2546,
            "SL": 2546
        },
        "points": {
            "Upper NWS point": {"lat": 44.5727, "lon": -72.7676, "elev_ft": 2546},
            "Lower NWS point": {"lat": 44.5902, "lon": -72.7737, "elev_ft": 1680},
        },
    },
    "Snow King": {
        "display_name": "Snow King Wax Tool",
        "course_name": "Snow King Race Venue",
        "lat": 43.4655,
        "lon": -110.7563,
        "elev_ft": 7520,
        "aspect_deg": 4.5,
        "slope_deg": 18.0,
        "finish_ft": 6283,
        "starts_ft": {
            "SuperG": 7520
        },
        "points": {
            "Upper NWS point": {"lat": 43.4655, "lon": -110.7563, "elev_ft": 7520},
            "Lower NWS point": {"lat": 43.4834, "lon": -110.7544, "elev_ft": 6283},
        },
    },
    "Snowbasin Resort Company": {
        "display_name": "Snowbasin Resort Company Wax Tool",
        "course_name": "Snowbasin Resort Company Race Venue",
        "lat": 41.2163,
        "lon": -111.8571,
        "elev_ft": 7900,
        "aspect_deg": 54.0,
        "slope_deg": 18.0,
        "finish_ft": 6391,
        "starts_ft": {
            "SuperG": 7900,
            "GS": 7900,
            "SL": 7408
        },
        "points": {
            "Upper NWS point": {"lat": 41.2163, "lon": -111.8571, "elev_ft": 7900},
            "Lower NWS point": {"lat": 41.2269, "lon": -111.8377, "elev_ft": 6391},
        },
    },
    "Snowbird. Ski & Summer Resort UT": {
        "display_name": "Snowbird. Ski & Summer Resort UT Wax Tool",
        "course_name": "Snowbird. Ski & Summer Resort UT Race Venue",
        "lat": 40.6331,
        "lon": -111.8038,
        "elev_ft": 8983,
        "aspect_deg": 340.8,
        "slope_deg": 18.0,
        "finish_ft": 7923,
        "starts_ft": {
            "GS": 8983,
            "SL": 8448
        },
        "points": {
            "Upper NWS point": {"lat": 40.6331, "lon": -111.8038, "elev_ft": 8983},
            "Lower NWS point": {"lat": 40.6501, "lon": -111.8116, "elev_ft": 7923},
        },
    },
    "Snowriver": {
        "display_name": "Snowriver Wax Tool",
        "course_name": "Snowriver Race Venue",
        "lat": 46.5002,
        "lon": -89.9758,
        "elev_ft": 1621,
        "aspect_deg": 11.1,
        "slope_deg": 18.0,
        "finish_ft": 1204,
        "starts_ft": {
            "SL": 1621
        },
        "points": {
            "Upper NWS point": {"lat": 46.5002, "lon": -89.9758, "elev_ft": 1621},
            "Lower NWS point": {"lat": 46.5179, "lon": -89.9708, "elev_ft": 1204},
        },
    },
    "Soldier Mountain": {
        "display_name": "Soldier Mountain Wax Tool",
        "course_name": "Soldier Mountain Race Venue",
        "lat": 44.7094,
        "lon": -115.0909,
        "elev_ft": 7178,
        "aspect_deg": 5.0,
        "slope_deg": 18.0,
        "finish_ft": 5840,
        "starts_ft": {
            "DH": 7178,
            "GS": 6900,
            "SuperG": 7178,
            "SL": 6453
        },
        "points": {
            "Upper NWS point": {"lat": 44.7094, "lon": -115.0909, "elev_ft": 7178},
            "Lower NWS point": {"lat": 44.7273, "lon": -115.0887, "elev_ft": 5840},
        },
    },
    "Spirit Mountain": {
        "display_name": "Spirit Mountain Wax Tool",
        "course_name": "Spirit Mountain Race Venue",
        "lat": 46.7176,
        "lon": -92.2124,
        "elev_ft": 1207,
        "aspect_deg": 30.0,
        "slope_deg": 18.0,
        "finish_ft": 745,
        "starts_ft": {
            "SL": 1207
        },
        "points": {
            "Upper NWS point": {"lat": 46.7176, "lon": -92.2124, "elev_ft": 1207},
            "Lower NWS point": {"lat": 46.7332, "lon": -92.1993, "elev_ft": 745},
        },
    },
    "Steamboat Springs/ Mount Werner CO": {
        "display_name": "Steamboat Springs/ Mount Werner CO Wax Tool",
        "course_name": "Steamboat Springs/ Mount Werner CO Race Venue",
        "lat": 40.4586,
        "lon": -106.8067,
        "elev_ft": 8018,
        "aspect_deg": 10.0,
        "slope_deg": 18.0,
        "finish_ft": 6719,
        "starts_ft": {
            "GS": 8018,
            "SL": 8018
        },
        "points": {
            "Upper NWS point": {"lat": 40.4586, "lon": -106.8067, "elev_ft": 8018},
            "Lower NWS point": {"lat": 40.4763, "lon": -106.8026, "elev_ft": 6719},
        },
    },
    "Stevens Pass": {
        "display_name": "Stevens Pass Wax Tool",
        "course_name": "Stevens Pass Race Venue",
        "lat": 47.7456,
        "lon": -121.0892,
        "elev_ft": 5348,
        "aspect_deg": 46.5,
        "slope_deg": 18.0,
        "finish_ft": 4091,
        "starts_ft": {
            "GS": 5348,
            "SL": 4790,
            "SuperG": 5240
        },
        "points": {
            "Upper NWS point": {"lat": 47.7456, "lon": -121.0892, "elev_ft": 5348},
            "Lower NWS point": {"lat": 47.758, "lon": -121.0698, "elev_ft": 4091},
        },
    },
    "Stowe Mountain Resort / Spruce Peak": {
        "display_name": "Stowe Mountain Resort / Spruce Peak Wax Tool",
        "course_name": "Stowe Mountain Resort / Spruce Peak Race Venue",
        "lat": 44.5264,
        "lon": -72.7816,
        "elev_ft": 3241,
        "aspect_deg": 54.4,
        "slope_deg": 18.0,
        "finish_ft": 1565,
        "starts_ft": {
            "SL": 2861,
            "GS": 3241,
            "SuperG": 3241
        },
        "points": {
            "Upper NWS point": {"lat": 44.5264, "lon": -72.7816, "elev_ft": 3241},
            "Lower NWS point": {"lat": 44.5369, "lon": -72.7611, "elev_ft": 1565},
        },
    },
    "Stratton Mountain": {
        "display_name": "Stratton Mountain Wax Tool",
        "course_name": "Stratton Mountain Race Venue",
        "lat": 43.0863,
        "lon": -72.9249,
        "elev_ft": 3848,
        "aspect_deg": 52.9,
        "slope_deg": 18.0,
        "finish_ft": 2543,
        "starts_ft": {
            "SL": 3799,
            "GS": 3848,
            "SuperG": 3848
        },
        "points": {
            "Upper NWS point": {"lat": 43.0863, "lon": -72.9249, "elev_ft": 3848},
            "Lower NWS point": {"lat": 43.0972, "lon": -72.9052, "elev_ft": 2543},
        },
    },
    "Sugar Bowl": {
        "display_name": "Sugar Bowl Wax Tool",
        "course_name": "Sugar Bowl Race Venue",
        "lat": 39.3003,
        "lon": -120.344,
        "elev_ft": 8360,
        "aspect_deg": 4.9,
        "slope_deg": 18.0,
        "finish_ft": 6936,
        "starts_ft": {
            "SL": 7559,
            "GS": 8360,
            "SuperG": 8360
        },
        "points": {
            "Upper NWS point": {"lat": 39.3003, "lon": -120.344, "elev_ft": 8360},
            "Lower NWS point": {"lat": 39.3182, "lon": -120.342, "elev_ft": 6936},
        },
    },
    "Sugarbush/Lincoln Peak": {
        "display_name": "Sugarbush/Lincoln Peak Wax Tool",
        "course_name": "Sugarbush/Lincoln Peak Race Venue",
        "lat": 44.1268,
        "lon": -72.8995,
        "elev_ft": 2841,
        "aspect_deg": 82.5,
        "slope_deg": 18.0,
        "finish_ft": 1680,
        "starts_ft": {
            "GS": 2841,
            "SL": 2415
        },
        "points": {
            "Upper NWS point": {"lat": 44.1268, "lon": -72.8995, "elev_ft": 2841},
            "Lower NWS point": {"lat": 44.1291, "lon": -72.8746, "elev_ft": 1680},
        },
    },
    "Sugarbush/Mount Ellen": {
        "display_name": "Sugarbush/Mount Ellen Wax Tool",
        "course_name": "Sugarbush/Mount Ellen Race Venue",
        "lat": 44.1559,
        "lon": -72.9283,
        "elev_ft": 3770,
        "aspect_deg": 73.1,
        "slope_deg": 18.0,
        "finish_ft": 1608,
        "starts_ft": {
            "SL": 3770,
            "GS": 2671,
            "SuperG": 2674
        },
        "points": {
            "Upper NWS point": {"lat": 44.1559, "lon": -72.9283, "elev_ft": 3770},
            "Lower NWS point": {"lat": 44.1611, "lon": -72.9043, "elev_ft": 1608},
        },
    },
    "Suicide Six": {
        "display_name": "Suicide Six Wax Tool",
        "course_name": "Suicide Six Race Venue",
        "lat": 43.6627,
        "lon": -72.5474,
        "elev_ft": 1329,
        "aspect_deg": 14.4,
        "slope_deg": 18.0,
        "finish_ft": 794,
        "starts_ft": {
            "SL": 1329
        },
        "points": {
            "Upper NWS point": {"lat": 43.6627, "lon": -72.5474, "elev_ft": 1329},
            "Lower NWS point": {"lat": 43.6801, "lon": -72.5412, "elev_ft": 794},
        },
    },
    "Sun Valley": {
        "display_name": "Sun Valley Wax Tool",
        "course_name": "Sun Valley Race Venue",
        "lat": 43.6962,
        "lon": -114.3531,
        "elev_ft": 8796,
        "aspect_deg": 0.0,
        "slope_deg": 18.0,
        "finish_ft": 5991,
        "starts_ft": {
            "DH": 8796,
            "SuperG": 8192,
            "SL": 6952,
            "GS": 7503
        },
        "points": {
            "Upper NWS point": {"lat": 43.6962, "lon": -114.3531, "elev_ft": 8796},
            "Lower NWS point": {"lat": 43.7142, "lon": -114.3531, "elev_ft": 5991},
        },
    },
    "Telluride": {
        "display_name": "Telluride Wax Tool",
        "course_name": "Telluride Race Venue",
        "lat": 37.9375,
        "lon": -107.8123,
        "elev_ft": 10479,
        "aspect_deg": 346.3,
        "slope_deg": 18.0,
        "finish_ft": 9524,
        "starts_ft": {
            "GS": 10479,
            "SL": 10479
        },
        "points": {
            "Upper NWS point": {"lat": 37.9375, "lon": -107.8123, "elev_ft": 10479},
            "Lower NWS point": {"lat": 37.955, "lon": -107.8177, "elev_ft": 9524},
        },
    },
    "Terry Peak Ski Area, Lead": {
        "display_name": "Terry Peak Ski Area, Lead Wax Tool",
        "course_name": "Terry Peak Ski Area, Lead Race Venue",
        "lat": 44.3673,
        "lon": -103.8228,
        "elev_ft": 6988,
        "aspect_deg": 23.6,
        "slope_deg": 18.0,
        "finish_ft": 6102,
        "starts_ft": {
            "GS": 6988,
            "SL": 6759
        },
        "points": {
            "Upper NWS point": {"lat": 44.3673, "lon": -103.8228, "elev_ft": 6988},
            "Lower NWS point": {"lat": 44.3838, "lon": -103.8127, "elev_ft": 6102},
        },
    },
    "Titcomb Mountain": {
        "display_name": "Titcomb Mountain Wax Tool",
        "course_name": "Titcomb Mountain Race Venue",
        "lat": 44.6484,
        "lon": -70.1717,
        "elev_ft": 709,
        "aspect_deg": 22.1,
        "slope_deg": 18.0,
        "finish_ft": 400,
        "starts_ft": {
            "SL": 709
        },
        "points": {
            "Upper NWS point": {"lat": 44.6484, "lon": -70.1717, "elev_ft": 709},
            "Lower NWS point": {"lat": 44.6651, "lon": -70.1622, "elev_ft": 400},
        },
    },
    "Utah Olympic Park": {
        "display_name": "Utah Olympic Park Wax Tool",
        "course_name": "Utah Olympic Park Race Venue",
        "lat": 40.7074,
        "lon": -111.5646,
        "elev_ft": 8081,
        "aspect_deg": 33.1,
        "slope_deg": 18.0,
        "finish_ft": 6923,
        "starts_ft": {
            "SL": 7579,
            "GS": 8081,
            "SuperG": 8081
        },
        "points": {
            "Upper NWS point": {"lat": 40.7074, "lon": -111.5646, "elev_ft": 8081},
            "Lower NWS point": {"lat": 40.7225, "lon": -111.5516, "elev_ft": 6923},
        },
    },
    "Vail": {
        "display_name": "Vail Wax Tool",
        "course_name": "Vail Race Venue",
        "lat": 39.6438,
        "lon": -106.3888,
        "elev_ft": 10016,
        "aspect_deg": 343.9,
        "slope_deg": 18.0,
        "finish_ft": 8248,
        "starts_ft": {
            "SL": 10007,
            "GS": 10013,
            "DH": 10016,
            "SuperG": 10016
        },
        "points": {
            "Upper NWS point": {"lat": 39.6438, "lon": -106.3888, "elev_ft": 10016},
            "Lower NWS point": {"lat": 39.6611, "lon": -106.3953, "elev_ft": 8248},
        },
    },
    "Waterville Valley": {
        "display_name": "Waterville Valley Wax Tool",
        "course_name": "Waterville Valley Race Venue",
        "lat": 43.9496,
        "lon": -71.5057,
        "elev_ft": 3448,
        "aspect_deg": 60.5,
        "slope_deg": 18.0,
        "finish_ft": 1978,
        "starts_ft": {
            "SL": 2769,
            "SuperG": 3448,
            "GS": 3245
        },
        "points": {
            "Upper NWS point": {"lat": 43.9496, "lon": -71.5057, "elev_ft": 3448},
            "Lower NWS point": {"lat": 43.9585, "lon": -71.4839, "elev_ft": 1978},
        },
    },
    "West Mountain": {
        "display_name": "West Mountain Wax Tool",
        "course_name": "West Mountain Race Venue",
        "lat": 43.8601,
        "lon": -74.706,
        "elev_ft": 1381,
        "aspect_deg": 80.0,
        "slope_deg": 18.0,
        "finish_ft": 430,
        "starts_ft": {
            "SL": 1362,
            "GS": 1381
        },
        "points": {
            "Upper NWS point": {"lat": 43.8601, "lon": -74.706, "elev_ft": 1381},
            "Lower NWS point": {"lat": 43.8632, "lon": -74.6814, "elev_ft": 430},
        },
    },
    "Whiteface Mountain": {
        "display_name": "Whiteface Mountain Wax Tool",
        "course_name": "Whiteface Mountain Race Venue",
        "lat": 44.3658,
        "lon": -73.903,
        "elev_ft": 3117,
        "aspect_deg": 106.9,
        "slope_deg": 18.0,
        "finish_ft": 1280,
        "starts_ft": {
            "SL": 2723,
            "SuperG": 3117,
            "DH": 3117,
            "GS": 2943
        },
        "points": {
            "Upper NWS point": {"lat": 44.3658, "lon": -73.903, "elev_ft": 3117},
            "Lower NWS point": {"lat": 44.3606, "lon": -73.8789, "elev_ft": 1280},
        },
    },
    "Winter Park": {
        "display_name": "Winter Park Wax Tool",
        "course_name": "Winter Park Race Venue",
        "lat": 39.918,
        "lon": -105.7856,
        "elev_ft": 10705,
        "aspect_deg": 15.0,
        "slope_deg": 18.0,
        "finish_ft": 9068,
        "starts_ft": {
            "SuperG": 10705,
            "DH": 10705,
            "GS": 10545,
            "SL": 9790
        },
        "points": {
            "Upper NWS point": {"lat": 39.918, "lon": -105.7856, "elev_ft": 10705},
            "Lower NWS point": {"lat": 39.9354, "lon": -105.7795, "elev_ft": 9068},
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

