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
    ("🇳🇴 Norway",         ["Kvitfjell", "Narvik"]),
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


def _venue_choices_for_user(user) -> list:
    engine_keys = set(ENGINE.VENUES.keys())
    has_multi = check_feature_access(user, "multiple_venues")
    groups = []

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


@login_required
def calculator(request):
    profile, _ = Profile.objects.get_or_create(user=request.user)
    if not profile.has_active_subscription():
        return redirect("paywall")

    if request.method == "POST":
        rate_err = check_rate_limit(request)
        if rate_err:
            return rate_err
        form = CalculatorForm(request.POST, venue_choices=_venue_choices_for_user(request.user))
        if form.is_valid():
            cd = form.cleaned_data

            venue = ENGINE.VENUES[cd["venue"]]
            discipline = cd["discipline"]
            if discipline not in venue["starts_ft"]:
                messages.error(request, f"{discipline} is not available at {cd['venue']}.")
                return redirect("calculator")
            start_ft = venue["starts_ft"][discipline]
            finish_ft = venue["finish_ft"]

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
                        "calc_venue": cd["venue"],
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
        },
    )


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
        c.setAuthor("GlideCast™")
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
        c.drawString(72, height - 72, "Race Day Report — GlideCast™")
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
