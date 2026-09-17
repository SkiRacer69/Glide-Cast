from __future__ import annotations

import dataclasses
import hashlib
import hmac
import json as _json
import math
import traceback
from datetime import date, datetime, time
from io import BytesIO

import numpy as np
import pandas as pd
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.templatetags.static import static
from django.utils import timezone

from accounts.features import (
    basic_venues_for_engine,
    check_feature_access,
    get_upgrade_prompt,
    pdf_download_limit,
)
from accounts.models import Profile
from accounts.rate_limit import check_rate_limit
from billing.models import PDFDownload
from .engine_loader import ENGINE
from .forms import CalculatorForm
from .models import CalculationAuditLog, CalculationHistory


def _show_pro_calculator_results(request) -> bool:
    """Full Pro-style results for every subscriber while SHOW_PRO_CALCULATOR_RESULTS is on."""
    return bool(getattr(settings, "SHOW_PRO_CALCULATOR_RESULTS", True))


def _hero_schedule_from_form(form: CalculatorForm) -> tuple[date, time, time]:
    """Race date and run times for hero + display (handles valid, invalid, and GET)."""
    if form.is_valid():
        cd = form.cleaned_data
        return cd["race_date"], cd["run1_time"], cd["run2_time"]
    rd: date = form.initial.get("race_date") or pd.Timestamp.now().date()
    r1: time = form.initial.get("run1_time") or time(9, 30)
    r2: time = form.initial.get("run2_time") or time(12, 30)
    if form.is_bound:
        ds = form.data.get("race_date")
        if ds:
            try:
                rd = datetime.strptime(str(ds), "%Y-%m-%d").date()
            except ValueError:
                pass
        for fname in ("run1_time", "run2_time"):
            ts = form.data.get(fname)
            if not ts:
                continue
            try:
                parts = [int(x) for x in str(ts).strip().split(":")[:3]]
                if len(parts) >= 2:
                    tt = time(parts[0], parts[1], parts[2] if len(parts) > 2 else 0)
                    if fname == "run1_time":
                        r1 = tt
                    else:
                        r2 = tt
            except ValueError:
                pass
    return rd, r1, r2


VENUE_IMAGES = {
    "Sugarloaf": "surger Loaf.png",
    "Sunday River": None,
    "Gore Mountain": None,
    "Mount Snow": None,
    "Killington": None,
}


# European WC venues grouped by country (display order)
_EU_GROUPS = [
    ("🇦🇩 Andorra",        ["Soldeu"]),
    ("🇦🇹 Austria",        ["Altenmarkt-Zauchensee", "Flachau", "Hinterstoder", "Kitzbühel",
                             "Mayrhofen", "Pitztal", "Saalbach", "Schladming", "Semmering", "Sölden"]),
    ("🇧🇬 Bulgaria",       ["Bansko"]),
    ("🇨🇿 Czech Republic", ["Spindlerův Mlýn"]),
    ("🇫🇮 Finland",        ["Levi", "Ruka"]),
    ("🇫🇷 France",         ["Chamonix", "Courchevel", "Méribel", "Val d'Isère"]),
    ("🇩🇪 Germany",        ["Garmisch-Partenkirchen", "Ofterschwang"]),
    ("🇮🇹 Italy",          ["Alta Badia", "Bormio", "Cortina d'Ampezzo", "Madonna di Campiglio",
                             "Santa Caterina Valfurva", "Sestriere", "Val Gardena"]),
    ("🇳🇴 Norway",         ["Hafjell", "Kvitfjell", "Narvik"]),
    ("🇸🇰 Slovakia",       ["Jasná"]),
    ("🇸🇮 Slovenia",       ["Kranjska Gora"]),
    ("🇸🇪 Sweden",         ["Åre"]),
    ("🇨🇭 Switzerland",    ["Adelboden", "Crans-Montana", "Lenzerheide", "Meiringen-Hasliberg",
                             "Veysonnaz", "Wengen", "Zermatt"]),
]

# US venues grouped by region (display order)
_US_GROUPS = [
    ("🇺🇸 New England", [
        "Sugarloaf", "Sunday River", "Saddleback", "Titcomb Mountain",
        "Burke Mountain", "Jay Peak Resort", "Killington", "Magic Mountain",
        "Middlebury College Snow Bowl", "Okemo Mountain", "Pico Peak",
        "Smugglers Notch Resort", "Stowe Mountain Resort / Spruce Peak",
        "Stratton Mountain", "Sugarbush/Lincoln Peak", "Sugarbush/Mount Ellen", "Suicide Six",
        "Attitash Ski Area", "Cranmore Mountain Resort", "Dartmouth Skiway",
        "Loon Mountain Resort", "Mittersill Cannon Mtn", "Mount Sunapee",
        "Pats Peak Ski Area", "Proctor Ski Area", "Waterville Valley",
        "Belleayre Mountain", "Catamount", "Gore Mountain", "Greek Peak",
        "Holiday Valley Resort", "Jiminy Peak Ski Area", "West Mountain", "Whiteface Mountain",
        "Berkshire East Mountain Resort",
    ]),
    ("🇺🇸 Mid-Atlantic & Midwest", [
        "Blue Mountain Resort",
        "Boyne Highlands", "Boyne Mountain", "Indianhead Mt", "Mont Ripley", "Snowriver",
        "Buck Hill", "Giants Ridge", "La Crosse", "Lutsen Mountain", "Spirit Mountain",
    ]),
    ("🇺🇸 Colorado", [
        "Aspen Mountain", "Aspen/Buttermilk", "Aspen/Highlands",
        "Beaver Creek Resort", "Breckenridge Ski Resort", "Copper Mountain",
        "Crested Butte Mountain Resort", "Eldora", "Keystone Ski Resort",
        "Loveland Valley", "Powderhorn",
        "Steamboat Springs/ Mount Werner CO", "Telluride", "Vail", "Winter Park",
    ]),
    ("🇺🇸 Utah", [
        "Park City Mountain Resort", "Snowbasin Resort Company",
        "Snowbird. Ski & Summer Resort UT", "Utah Olympic Park",
    ]),
    ("🇺🇸 Mountain West", [
        "Soldier Mountain", "Sun Valley",
        "Grand Targhee", "Hogadon Ski Area", "Jackson Hole", "Snow King",
        "Big Sky", "Bridger Bowl", "Maverick Mt",
        "Terry Peak Ski Area, Lead",
        "Arizona Snowbowl",
    ]),
    ("🇺🇸 Pacific Northwest", [
        "Crystal Mountain", "Mission Ridge", "Mount Spokane", "Stevens Pass",
        "Mount Bachelor", "Mt Hood Meadows", "Mt Hood Skibowl",
    ]),
    ("🇺🇸 California", [
        "Bear Canyon", "Boreal Mountain Resort", "Diamond Peak Ski Resort",
        "Heavenly Mountain Resort", "Mammoth Mountain", "Mt Rose Ski Tahoe",
        "Northstar California", "Palisades Tahoe", "Sugar Bowl",
    ]),
    ("🇺🇸 Alaska", [
        "Alyeska Resort", "Arctic Valley Ski Area",
    ]),
]


def _nearest_venue(lat: float, lon: float) -> str:
    """Return the name of the ENGINE venue closest to (lat, lon)."""
    best_name = next(iter(ENGINE.VENUES))
    best_dist = float("inf")
    for name, v in ENGINE.VENUES.items():
        dlat = math.radians(v["lat"] - lat)
        dlon = math.radians(v["lon"] - lon)
        a = (math.sin(dlat / 2) ** 2
             + math.cos(math.radians(lat)) * math.cos(math.radians(v["lat"])) * math.sin(dlon / 2) ** 2)
        dist = 6371.0 * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
        if dist < best_dist:
            best_dist = dist
            best_name = name
    return best_name


def _parse_gpx_samples(gpx_file):
    """Parse an uploaded GPX file and return (samples, slope_deg, aspect_deg, chart_html)."""
    import cmath as _cmath
    from nordic.gpx_parser import parse_gpx, sample_course

    raw_bytes = gpx_file.read()
    raw_points = parse_gpx(raw_bytes)
    samples = sample_course(raw_points, interval_m=100)

    if len(samples) < 2:
        raise ValueError("GPX track too short — need at least two points.")

    # Slope: total elevation drop / total distance (alpine run goes top → bottom)
    elev_sorted = sorted(samples, key=lambda s: s["elevation_m"])
    top_m    = elev_sorted[-1]["elevation_m"]
    bottom_m = elev_sorted[0]["elevation_m"]
    total_drop_m = max(0.0, top_m - bottom_m)
    total_dist_m = samples[-1]["cum_dist_m"] or 1.0
    slope_deg = round(min(45.0, math.degrees(math.atan(total_drop_m / total_dist_m))), 1)

    # Aspect: circular mean of all bearings
    bearings = [s["bearing_deg"] for s in samples if s.get("bearing_deg") is not None]
    if bearings:
        avg_angle = _cmath.phase(sum(_cmath.rect(1, math.radians(b)) for b in bearings))
        aspect_deg = round((math.degrees(avg_angle) + 360) % 360, 1)
    else:
        aspect_deg = 0.0

    # Elevation profile chart
    chart_html = ""
    try:
        import plotly.graph_objects as go
        dists = [s["cum_dist_m"] / 1000 for s in samples]
        elevs = [s["elevation_m"] for s in samples]
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=dists, y=elevs,
            mode="lines",
            line=dict(color="#60a5fa", width=2.5),
            fill="tozeroy",
            fillcolor="rgba(96,165,250,0.12)",
            hovertemplate="<b>%{x:.2f} km</b><br>Elev: %{y:.0f} m<extra></extra>",
        ))
        fig.update_layout(
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            font=dict(color="#e5e7eb", size=11),
            margin=dict(l=50, r=20, t=10, b=40),
            height=200,
            showlegend=False,
            xaxis=dict(title="Distance (km)", gridcolor="rgba(255,255,255,0.08)", zerolinecolor="rgba(255,255,255,0.08)"),
            yaxis=dict(title="Elevation (m)", gridcolor="rgba(255,255,255,0.08)", zerolinecolor="rgba(255,255,255,0.08)"),
        )
        chart_html = fig.to_html(full_html=False, include_plotlyjs="cdn")
    except Exception:
        pass

    return samples, slope_deg, aspect_deg, chart_html


def _venue_choices_for_user(user) -> list:
    engine_keys = set(ENGINE.VENUES.keys())
    has_multi = check_feature_access(user, "multiple_venues")
    groups = [("📍 GPX Upload", [("__gpx__", "📍 Upload GPX file")])]

    # FIS World Cup Europe — open to all plans
    for country, keys in _EU_GROUPS:
        opts = [(k, k) for k in keys if k in engine_keys]
        if opts:
            groups.append((f"FIS World Cup · {country}", opts))

    # US venues
    if has_multi:
        for region, keys in _US_GROUPS:
            opts = [(k, k) for k in keys if k in engine_keys]
            if opts:
                groups.append((region, opts))
    else:
        basic = basic_venues_for_engine(list(engine_keys))
        if basic:
            groups.append(("🇺🇸 US Venues", [(k, k) for k in basic]))

    return groups


def _first_venue_key(grouped_choices: list) -> str:
    """Extract the first venue key from grouped choices."""
    for _group_label, opts in grouped_choices:
        if opts:
            return opts[0][0]
    return "Sugarloaf"


def _require_active_subscription(request) -> bool:
    profile, _ = Profile.objects.get_or_create(user=request.user)
    return profile.has_active_subscription()


def calculator(request):
    if not request.user.is_authenticated:
        return render(request, "calculator/landing.html", {})
    profile, _ = Profile.objects.get_or_create(user=request.user)
    if not profile.has_active_subscription():
        return redirect("paywall")

    if request.method == "POST":
        rate_err = check_rate_limit(request)
        if rate_err:
            return rate_err
        form = CalculatorForm(request.POST, request.FILES, venue_choices=_venue_choices_for_user(request.user))
        if form.is_valid():
            cd = form.cleaned_data

            gpx_chart_html = ""
            gpx_slope_deg = None
            gpx_aspect_deg = None
            discipline = cd["discipline"]

            if cd["venue"] == "__gpx__":
                # ── GPX mode ─────────────────────────────────────────────────
                gpx_file = cd.get("gpx_file")
                if not gpx_file:
                    messages.error(request, "Please upload a GPX file when 'Upload GPX file' is selected.")
                    vc = _venue_choices_for_user(request.user)
                    form = CalculatorForm(request.POST, request.FILES, venue_choices=vc)
                    return render(request, "calculator/calculator.html", {
                        "form": form,
                        "hero_venue": "GPX", "hero_discipline": discipline,
                        "hero_race_date": cd["race_date"],
                        "hero_run1_time": cd["run1_time"], "hero_run2_time": cd["run2_time"],
                        "venues_json": _json.dumps({
                            k: {"aspect_deg": v["aspect_deg"], "slope_deg": v["slope_deg"],
                                "disciplines": list(v["starts_ft"].keys())}
                            for k, v in ENGINE.VENUES.items()
                        }),
                        "debug": settings.DEBUG,
                    })
                try:
                    samples, gpx_slope_deg, gpx_aspect_deg, gpx_chart_html = _parse_gpx_samples(gpx_file)
                except Exception as exc:
                    messages.error(request, f"Could not read GPX file: {exc}")
                    vc = _venue_choices_for_user(request.user)
                    form = CalculatorForm(request.POST, request.FILES, venue_choices=vc)
                    return render(request, "calculator/calculator.html", {
                        "form": form,
                        "hero_venue": "GPX", "hero_discipline": discipline,
                        "hero_race_date": cd["race_date"],
                        "hero_run1_time": cd["run1_time"], "hero_run2_time": cd["run2_time"],
                        "venues_json": _json.dumps({
                            k: {"aspect_deg": v["aspect_deg"], "slope_deg": v["slope_deg"],
                                "disciplines": list(v["starts_ft"].keys())}
                            for k, v in ENGINE.VENUES.items()
                        }),
                        "debug": settings.DEBUG,
                    })

                cd["slope_deg"] = gpx_slope_deg
                cd["aspect_deg"] = gpx_aspect_deg

                # Use GPX elevation range for start/finish
                elev_sorted = sorted(samples, key=lambda s: s["elevation_m"])
                start_ft = elev_sorted[-1]["elevation_m"] * 3.28084
                finish_ft = elev_sorted[0]["elevation_m"] * 3.28084

                # Find nearest venue for weather data
                mid = samples[len(samples) // 2]
                nearest_name = _nearest_venue(mid["lat"], mid["lon"])
                venue = ENGINE.VENUES[nearest_name]
                calc_venue_display = f"GPX upload (weather: {nearest_name})"

            else:
                # ── Venue mode ────────────────────────────────────────────────
                gpx_file = cd.get("gpx_file")
                if gpx_file:
                    try:
                        samples, gpx_slope_deg, gpx_aspect_deg, gpx_chart_html = _parse_gpx_samples(gpx_file)
                        cd["slope_deg"] = gpx_slope_deg
                        cd["aspect_deg"] = gpx_aspect_deg
                    except Exception:
                        pass

                venue = ENGINE.VENUES[cd["venue"]]
                if discipline not in venue["starts_ft"]:
                    messages.error(request, f"{discipline} is not available at {cd['venue']}.")
                    return redirect("calculator")
                start_ft = venue["starts_ft"][discipline]
                finish_ft = venue["finish_ft"]
                calc_venue_display = cd["venue"]

            mp_fields = {f.name for f in dataclasses.fields(ENGINE.ModelParams)}
            params_args = [
                cd["wind_coeff"],
                cd["solar_coeff"],
                cd["clear_night_coeff"],
                cd["longwave_coeff"],
                cd["latent_coeff"],
                cd["restore_coeff"],
                cd["lapse_cap_f_per_1000ft"],
                cd["deep_start_f"] if cd["use_manual_deep"] else float("nan"),
                cd["deep_finish_f"] if cd["use_manual_deep"] else float("nan"),
                cd["deep_auto_relax_coeff"],
                cd["slope_deg"],
                cd["aspect_deg"],
                cd["cloud_attenuation"],
                cd["diffuse_floor_frac"],
                cd["albedo"],
            ]
            if "wet_lock_band_f" in mp_fields:
                params_args.extend(
                    [cd["wet_lock_band_f"], cd["wet_refreeze_strength"], cd["wet_deep_relax_scale"]]
                )
            params = ENGINE.ModelParams(*params_args)

            try:
                _weather_api = venue.get("weather_api", "nws")
                upper = ENGINE.get_hourly_forecast(
                    weather_api=_weather_api,
                    **{k: v for k, v in venue["points"]["Upper NWS point"].items() if k in {"lat", "lon"}}
                )
                lower = ENGINE.get_hourly_forecast(
                    weather_api=_weather_api,
                    **{k: v for k, v in venue["points"]["Lower NWS point"].items() if k in {"lat", "lon"}}
                )
                merged = ENGINE.merge_forecasts(upper, lower)
                model = ENGINE.prepare_venue(
                    merged,
                    venue,
                    start_ft,
                    finish_ft,
                    params,
                    pd.Timestamp(cd["race_date"]),
                )

                run1_dt = pd.Timestamp.combine(pd.to_datetime(cd["race_date"]), cd["run1_time"])
                run2_dt = pd.Timestamp.combine(pd.to_datetime(cd["race_date"]), cd["run2_time"])

                run1 = ENGINE.run_summary(model, run1_dt, cd["snow_mode"], cd["dirty_abrasive"])
                run2 = ENGINE.run_summary(model, run2_dt, cd["snow_mode"], cd["dirty_abrasive"])

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

                results = {"run1": _jsonable(run1), "run2": _jsonable(run2)}
                CalculationHistory.objects.create(user=request.user, inputs=_jsonable(cd), results=results)
                CalculationAuditLog.objects.create(
                    user=request.user,
                    plan_tier=profile.effective_plan_tier(),
                )

                # Pro: RaceWax Oracle v10 Plotly charts (same builders as the macOS app)
                chart_html = ""
                chart_wax_html = ""
                chart_met_html = ""
                chart_solar_html = ""
                if _show_pro_calculator_results(request) or check_feature_access(request.user, "pro_insights"):
                    try:
                        licensed = getattr(request.user, "email", "") or request.user.username
                        if not hasattr(ENGINE, "build_visual_wax_chart"):
                            raise AttributeError("Engine missing v10 chart builders")
                        wax_fig = ENGINE.build_visual_wax_chart(run1, run2)
                        wax_fig.update_layout(title_text=f"Visual wax decision chart — Licensed to: {licensed}")
                        chart_wax_html = wax_fig.to_html(full_html=False, include_plotlyjs="cdn")
                        temp_fig = ENGINE.build_temperature_figure(model, run1_dt, run2_dt)
                        temp_fig.update_layout(title_text=f"Start and finish air / snow temperatures — {licensed}")
                        chart_html = temp_fig.to_html(full_html=False, include_plotlyjs=False)
                        met_fig = ENGINE.build_meteorology_figure(model, run1_dt, run2_dt)
                        chart_met_html = met_fig.to_html(full_html=False, include_plotlyjs=False)
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
                        chart_solar_html = solar_fig.to_html(full_html=False, include_plotlyjs=False)
                    except Exception:
                        chart_html = ""
                        chart_wax_html = ""
                        chart_met_html = ""
                        chart_solar_html = ""

                runs = [{"label": "Run 1", "run": results["run1"]}, {"label": "Run 2", "run": results["run2"]}]
                force_pro = _show_pro_calculator_results(request)
                show_pro = force_pro or check_feature_access(request.user, "pro_insights")
                can_pdf = force_pro or check_feature_access(request.user, "pdf_export")
                limit = None if force_pro else pdf_download_limit(profile)
                period_start = profile.pdf_period_start or timezone.now().replace(year=2000, month=1, day=1)
                pdf_count = PDFDownload.objects.filter(user=request.user, created_at__gte=period_start).count() if limit is not None else 0
                pdf_remaining = (max(0, limit - pdf_count) if limit else None) if can_pdf else 0
                results_venue_image = None
                if cd["venue"] == "Sugarloaf" and VENUE_IMAGES.get("Sugarloaf"):
                    results_venue_image = static(VENUE_IMAGES["Sugarloaf"])
                return render(
                    request,
                    "calculator/results.html",
                    {
                        "form": form,
                        "runs": runs,
                        "calc_venue": calc_venue_display,
                        "calc_discipline": cd["discipline"],
                        "calc_race_date": cd["race_date"],
                        "calc_run1_time": cd["run1_time"],
                        "calc_run2_time": cd["run2_time"],
                        "results_venue_image": results_venue_image,
                        "chart_html": chart_html,
                        "chart_wax_html": chart_wax_html,
                        "chart_met_html": chart_met_html,
                        "chart_solar_html": chart_solar_html,
                        "show_pro_insights": show_pro,
                        "show_energy_panel": force_pro or check_feature_access(request.user, "energy_panel"),
                        "licensed_to_email": getattr(request.user, "email", "") or request.user.username,
                        "upgrade_prompt": get_upgrade_prompt(request.user) or {},
                        "can_download_pdf": can_pdf and (pdf_remaining is None or pdf_remaining > 0),
                        "pdf_remaining": pdf_remaining,
                        "gpx_chart_html": gpx_chart_html,
                        "gpx_slope_deg": gpx_slope_deg,
                        "gpx_aspect_deg": gpx_aspect_deg,
                    },
                )
            except Exception as exc:
                # Surface engine errors during development so you can see why the calc failed.
                traceback.print_exc()
                messages.error(request, f"Could not compute a recommendation: {exc}")
        else:
            messages.error(request, "Please correct the errors below.")
    else:
        vc = _venue_choices_for_user(request.user)
        default_venue = _first_venue_key(vc)
        form = CalculatorForm(
            venue_choices=vc,
            initial={
                "venue": default_venue,
                "discipline": "GS",
                "race_date": pd.Timestamp.now().date(),
                "run1_time": pd.Timestamp("09:30").time(),
                "run2_time": pd.Timestamp("12:30").time(),
                "snow_mode": "Auto",
                "wet_lock_band_f": 0.3,
                "wet_refreeze_strength": 3.5,
                "wet_deep_relax_scale": 0.4,
            },
        )

    hero_venue = (form.data.get("venue") if form.is_bound else form.initial.get("venue")) or "Sugarloaf"
    hero_discipline = (form.data.get("discipline") if form.is_bound else form.initial.get("discipline")) or "GS"
    hero_race_date, hero_run1_time, hero_run2_time = _hero_schedule_from_form(form)

    # Per-venue data for JS: aspect, slope, available disciplines
    venues_json = _json.dumps({
        key: {
            "aspect_deg": v["aspect_deg"],
            "slope_deg": v["slope_deg"],
            "disciplines": list(v["starts_ft"].keys()),
        }
        for key, v in ENGINE.VENUES.items()
    })

    return render(
        request,
        "calculator/calculator.html",
        {
            "form": form,
            "hero_venue": hero_venue,
            "hero_discipline": hero_discipline,
            "hero_race_date": hero_race_date,
            "hero_run1_time": hero_run1_time,
            "hero_run2_time": hero_run2_time,
            "venues_json": venues_json,
            "debug": settings.DEBUG,
        },
    )


@login_required
def venue_map(request):
    """Full-screen 3D globe showing all FIS venues, colored by current wax recommendation."""
    import json as _json_mod

    force_pro = bool(getattr(settings, "SHOW_PRO_CALCULATOR_RESULTS", True))
    if not force_pro:
        profile, _ = Profile.objects.get_or_create(user=request.user)
        if not profile.has_active_subscription():
            return redirect("paywall")

    venues = []
    for name, v in ENGINE.VENUES.items():
        discs = list(v.get("starts_ft", {}).keys())
        region = "Europe" if v.get("weather_api") == "open-meteo" else "North America"
        venues.append({
            "name": name,
            "lat": v["lat"],
            "lon": v["lon"],
            "elev_ft": v["elev_ft"],
            "finish_ft": v["finish_ft"],
            "disciplines": discs,
            "region": region,
        })

    return render(request, "calculator/map.html", {
        "venues_json": _json_mod.dumps(venues),
        "venue_count": len(venues),
        "can_see_wax_colors": True,
    })


def globe_wax_data(request):
    """Return current wax call per venue using the WaxOracle engine's actual hs_call_from_conditions."""
    from django.http import JsonResponse

    if not request.user.is_authenticated:
        return JsonResponse({"error": "authentication required"}, status=401)

    force_pro = bool(getattr(settings, "SHOW_PRO_CALCULATOR_RESULTS", True))
    if not force_pro:
        profile, _ = Profile.objects.get_or_create(user=request.user)
        if not profile.has_active_subscription():
            return JsonResponse({"error": "subscription required"}, status=403)

    import requests as _requests
    from django.core.cache import cache

    CACHE_KEY = "globe_wax_v3"
    cached = cache.get(CACHE_KEY)
    if cached is not None:
        return JsonResponse(cached, safe=False)

    from .engine_loader import ENGINE

    # Standard lapse rate for snow surface temp vs elevation
    LAPSE_F_PER_1000FT = 3.5

    names = list(ENGINE.VENUES.keys())
    venues_list = [ENGINE.VENUES[n] for n in names]
    result = {}

    BATCH = 50
    try:
        for start in range(0, len(names), BATCH):
            end = min(start + BATCH, len(names))
            b_names = names[start:end]
            b_lats  = [venues_list[i]["lat"] for i in range(start, end)]
            b_lons  = [venues_list[i]["lon"] for i in range(start, end)]
            b_elevs = [int(venues_list[i]["elev_ft"] * 0.3048) for i in range(start, end)]

            resp = _requests.get(
                "https://api.open-meteo.com/v1/forecast",
                params={
                    "latitude":  ",".join(str(x) for x in b_lats),
                    "longitude": ",".join(str(x) for x in b_lons),
                    "elevation": ",".join(str(x) for x in b_elevs),
                    "current": "temperature_2m",
                    "timezone": "auto",
                    "forecast_days": "1",
                },
                timeout=12,
                headers={"User-Agent": "WaxOracle/1.0"},
            )
            resp.raise_for_status()
            data = resp.json()
            if isinstance(data, dict):
                data = [data]

            for i, item in enumerate(data):
                n = b_names[i]
                v = venues_list[start + i]
                try:
                    temp_c = item["current"]["temperature_2m"]
                    start_f = temp_c * 9 / 5 + 32
                    vert_ft = max(0, v.get("elev_ft", 0) - v.get("finish_ft", 0))
                    finish_f = start_f + (vert_ft / 1000) * LAPSE_F_PER_1000FT

                    wax_name, _, weighted_c, color, _ = ENGINE.hs_call_from_conditions(
                        start_f, finish_f, start_f, finish_f, "Packed / groomed"
                    )
                    result[n] = {
                        "color": color,
                        "label": wax_name,
                        "temp_c": round(temp_c, 1),
                        "weighted_c": round(float(weighted_c), 1),
                    }
                except Exception:
                    result[n] = {"color": "#6b7280", "label": "No data", "temp_c": None, "weighted_c": None}

    except Exception:
        pass

    for n in names:
        if n not in result:
            result[n] = {"color": "#6b7280", "label": "No data", "temp_c": None, "weighted_c": None}

    cache.set(CACHE_KEY, result, 60 * 60 * 2)
    return JsonResponse(result)


def _watermark_token(user_id: int, secret: str) -> str:
    return hmac.new(secret.encode(), str(user_id).encode(), hashlib.sha256).hexdigest()[:32]


@login_required
def export_race_report_pdf(request):
    """Generate PDF race day report with watermark and metadata token. Enforces plan and rate limit."""
    rate_err = check_rate_limit(request)
    if rate_err:
        return rate_err
    profile, _ = Profile.objects.get_or_create(user=request.user)
    force_pro = _show_pro_calculator_results(request)
    if not force_pro and not check_feature_access(request.user, "pdf_export"):
        return render(
            request,
            "accounts/upgrade_prompt.html",
            {"feature": "PDF export", "upgrade_prompt": get_upgrade_prompt(request.user) or {}},
        )
    limit = None if force_pro else pdf_download_limit(profile)
    if not force_pro and limit == 0:
        return render(
            request,
            "accounts/upgrade_prompt.html",
            {"feature": "PDF export (not included in your plan)", "upgrade_prompt": get_upgrade_prompt(request.user) or {}},
        )
    period_start = profile.pdf_period_start or timezone.now().replace(year=2000, month=1, day=1)
    pdf_count = PDFDownload.objects.filter(user=request.user, created_at__gte=period_start).count()
    if not force_pro and limit is not None and pdf_count >= limit:
        return render(
            request,
            "calculator/pdf_limit_reached.html",
            {"upgrade_prompt": get_upgrade_prompt(request.user) or {}, "pdf_limit": limit},
        )
    history = CalculationHistory.objects.filter(user=request.user).order_by("-created_at").first()
    if not history or not history.results:
        messages.error(request, "No calculation to export. Run the calculator first.")
        return redirect("calculator")
    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import letter
        from reportlab.lib.units import inch
        from reportlab.pdfgen import canvas

        buf = BytesIO()
        c = canvas.Canvas(buf, pagesize=letter)
        width, height = letter
        name = getattr(request.user, "get_full_name", lambda: "")() or request.user.username
        email = getattr(request.user, "email", "") or ""
        watermark_text = f"{name}  —  {email}"

        secret = getattr(settings, "WATERMARK_SECRET", settings.SECRET_KEY)
        token = _watermark_token(request.user.id, secret)
        c.setAuthor("WaxOracle™")
        c.setTitle("Race Day Report")
        c.setSubject(f"glidecast-{token}")

        c.setFont("Helvetica", 10)
        c.setFillColor(colors.HexColor("#D0D0D0"))
        c.saveState()
        c.translate(width / 2, height / 2)
        c.rotate(45)
        for i in range(-3, 4):
            for j in range(-2, 3):
                c.drawCentredString(i * 2.2 * inch, j * 1.8 * inch, watermark_text)
        c.restoreState()
        c.setFillColor(colors.black)
        c.setFont("Helvetica", 14)
        c.drawString(72, height - 72, "Race Day Report — WaxOracle™")
        y = height - 110
        c.setFont("Helvetica", 12)
        runs = history.results.get("run1"), history.results.get("run2")
        for i, run in enumerate(runs or []):
            if not run:
                continue
            c.drawString(72, y, f"Run {i + 1}: {run.get('hs_name', run.get('hs', '—'))}")
            y -= 22
            c.drawString(72, y, f"  Snow: {run.get('snow_start_f')} – {run.get('snow_finish_f')} °F")
            y -= 22
        y -= 24
        c.setFont("Helvetica", 9)
        c.drawString(72, y, f"Licensed to: {email}")
        c.drawString(72, y - 14, f"Account token: {token}")
        c.save()
        buf.seek(0)
        PDFDownload.objects.create(user=request.user)
        response = HttpResponse(buf.getvalue(), content_type="application/pdf")
        response["Content-Disposition"] = 'attachment; filename="race-day-report.pdf"'
        return response
    except Exception as e:
        messages.error(request, f"Could not generate PDF: {e}")
        return redirect("calculator")
