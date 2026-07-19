from __future__ import annotations

import dataclasses
import json
import math
import sys
import traceback
from datetime import date, datetime, time
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import racewax_engine_v10 as ENGINE  # noqa: E402

from db import save_calculation, venues_for_user


def _jsonable(o):
    if isinstance(o, (pd.Timestamp, datetime, date, time)):
        return o.isoformat() if hasattr(o, "isoformat") else str(o)
    if hasattr(o, "dtype") and hasattr(o, "item"):
        try:
            val = o.item()
            if isinstance(val, float) and (math.isnan(val) or math.isinf(val)):
                return None
            return float(val) if isinstance(val, (float, np.floating)) else int(val)
        except Exception:
            return None
    if isinstance(o, float) and (math.isnan(o) or math.isinf(o)):
        return None
    if isinstance(o, dict):
        return {str(k): _jsonable(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_jsonable(v) for v in o]
    return o


def list_venues(user: dict) -> list[str]:
    return venues_for_user(user, list(ENGINE.VENUES.keys()))


def run_calculation(user: dict, payload: dict) -> dict:
    venue_name = payload["venue"]
    allowed = list_venues(user)
    if venue_name not in allowed:
        raise ValueError(f"Venue not available on your plan: {venue_name}")

    venue = ENGINE.VENUES[venue_name]
    discipline = payload["discipline"]
    race_date = datetime.strptime(payload["race_date"], "%Y-%m-%d").date()
    run1_time = datetime.strptime(payload["run1_time"], "%H:%M").time()
    run2_time = datetime.strptime(payload["run2_time"], "%H:%M").time()
    snow_mode = payload.get("snow_mode", "Auto")
    dirty_abrasive = bool(payload.get("dirty_abrasive", False))

    start_ft = venue["starts_ft"][discipline]
    finish_ft = venue["finish_ft"]

    mp_fields = {f.name for f in dataclasses.fields(ENGINE.ModelParams)}
    params_args = [
        float(payload.get("wind_coeff", 0.12)),
        float(payload.get("solar_coeff", 2.0)),
        float(payload.get("clear_night_coeff", 1.4)),
        float(payload.get("longwave_coeff", -0.25)),
        float(payload.get("latent_coeff", 0.06)),
        float(payload.get("restore_coeff", 0.05)),
        float(payload.get("lapse_cap_f_per_1000ft", 4.5)),
        float("nan"),
        float("nan"),
        float(payload.get("deep_auto_relax_coeff", 0.02)),
        float(payload.get("slope_deg", venue.get("slope_deg", 19.0))),
        float(payload.get("aspect_deg", venue.get("aspect_deg", 20.0))),
        float(payload.get("cloud_attenuation", 0.75)),
        float(payload.get("diffuse_floor_frac", 0.35)),
        float(payload.get("albedo", 0.75)),
    ]
    if "wet_lock_band_f" in mp_fields:
        params_args.extend(
            [
                float(payload.get("wet_lock_band_f", 0.3)),
                float(payload.get("wet_refreeze_strength", 3.5)),
                float(payload.get("wet_deep_relax_scale", 0.4)),
            ]
        )
    params = ENGINE.ModelParams(*params_args)

    upper = ENGINE.get_hourly_forecast(
        **{k: v for k, v in venue["points"]["Upper NWS point"].items() if k in {"lat", "lon"}}
    )
    lower = ENGINE.get_hourly_forecast(
        **{k: v for k, v in venue["points"]["Lower NWS point"].items() if k in {"lat", "lon"}}
    )
    merged = ENGINE.merge_forecasts(upper, lower)
    model = ENGINE.prepare_venue(
        merged,
        venue,
        start_ft,
        finish_ft,
        params,
        pd.Timestamp(race_date),
    )

    run1_dt = pd.Timestamp.combine(pd.to_datetime(race_date), run1_time)
    run2_dt = pd.Timestamp.combine(pd.to_datetime(race_date), run2_time)

    run1 = ENGINE.run_summary(model, run1_dt, snow_mode, dirty_abrasive)
    run2 = ENGINE.run_summary(model, run2_dt, snow_mode, dirty_abrasive)

    results = {"run1": _jsonable(run1), "run2": _jsonable(run2)}
    inputs = _jsonable(
        {
            "venue": venue_name,
            "discipline": discipline,
            "race_date": race_date.isoformat(),
            "run1_time": run1_time.strftime("%H:%M"),
            "run2_time": run2_time.strftime("%H:%M"),
            "snow_mode": snow_mode,
            "dirty_abrasive": dirty_abrasive,
        }
    )

    charts = {}
    licensed = user.get("email") or user.get("username") or "GlideCast user"
    show_pro = user.get("plan_tier") == "pro"
    if show_pro and hasattr(ENGINE, "build_visual_wax_chart"):
        try:
            wax_fig = ENGINE.build_visual_wax_chart(run1, run2)
            wax_fig.update_layout(title_text=f"Visual wax decision chart — Licensed to: {licensed}")
            charts["wax"] = wax_fig.to_html(full_html=False, include_plotlyjs="cdn")
            temp_fig = ENGINE.build_temperature_figure(model, run1_dt, run2_dt)
            temp_fig.update_layout(title_text=f"Start and finish air / snow temperatures — {licensed}")
            charts["temperature"] = temp_fig.to_html(full_html=False, include_plotlyjs=False)
            met_fig = ENGINE.build_meteorology_figure(model, run1_dt, run2_dt)
            charts["meteorology"] = met_fig.to_html(full_html=False, include_plotlyjs=False)
            solar_fig = ENGINE.build_time_series_figure(
                model,
                [
                    ("poa_global_wm2", "Slope irradiance (W/m²)"),
                    ("solar_elevation_deg", "Solar elevation (°)"),
                    ("clear_night_start_wm2", "Clear-night cooling start (W/m²)"),
                    ("longwave_start_wm2", "Longwave start (W/m²)"),
                ],
                "Slope solar and overnight radiative forcing",
                "Value",
                run1_dt,
                run2_dt,
            )
            charts["solar"] = solar_fig.to_html(full_html=False, include_plotlyjs=False)
        except Exception:
            traceback.print_exc()

    save_calculation(user["id"], json.dumps(inputs), json.dumps(results))

    return {
        "inputs": inputs,
        "results": results,
        "charts": charts,
        "show_pro_insights": show_pro,
        "show_energy_panel": show_pro,
        "licensed_to": licensed,
    }
