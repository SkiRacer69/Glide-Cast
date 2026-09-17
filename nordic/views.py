from __future__ import annotations

from datetime import timedelta
from pathlib import Path

import pandas as pd

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.urls import reverse

from accounts.models import Profile

from .engine import recommend_from_gpx
from .forms import NordicCalculatorForm
from .gpx_parser import parse_gpx, sample_course
from .models import NordicCalculationHistory

_COURSES_DIR = Path(__file__).resolve().parent / "courses"


@login_required
def nordic_calculator(request):
    force_pro = bool(getattr(settings, "SHOW_PRO_CALCULATOR_RESULTS", True))
    if not force_pro:
        profile, _ = Profile.objects.get_or_create(user=request.user)
        if not profile.has_access_to_sport("nordic"):
            return redirect(reverse("paywall") + "?sport=nordic")

    if request.method == "POST":
        form = NordicCalculatorForm(request.POST, request.FILES)
        if form.is_valid():
            cd = form.cleaned_data

            # --- Resolve GPX bytes: uploaded file or pre-loaded course ---
            raw_bytes = None
            gpx_source = "uploaded"

            uploaded = cd.get("gpx_file")
            pre_loaded = cd.get("pre_loaded_course") or ""

            if uploaded:
                raw_bytes = uploaded.read()
                gpx_source = "uploaded"
            elif pre_loaded:
                course_path = _COURSES_DIR / f"{pre_loaded}.gpx"
                if not course_path.exists():
                    messages.error(request, f"Pre-loaded course not found: {pre_loaded}")
                    return render(request, "nordic/calculator.html", {"form": form})
                raw_bytes = course_path.read_bytes()
                gpx_source = pre_loaded

            # --- Parse GPX ---
            gpx_samples = None
            gpx_error = None
            try:
                raw_points = parse_gpx(raw_bytes)
                gpx_samples = sample_course(raw_points, interval_m=300)
            except ValueError as exc:
                gpx_error = str(exc)

            if gpx_error or not gpx_samples:
                messages.error(request, f"Could not read GPX file: {gpx_error or 'no track points found'}")
                return render(request, "nordic/calculator.html", {"form": form})

            # --- Race datetime (default: tomorrow 10 AM) ---
            race_dt_raw = cd.get("race_datetime")
            if race_dt_raw:
                race_dt = pd.Timestamp(race_dt_raw)
            else:
                tomorrow = pd.Timestamp.now().normalize() + timedelta(days=1)
                race_dt = tomorrow.replace(hour=10, minute=0, second=0)

            result = recommend_from_gpx(
                gpx_samples=gpx_samples,
                discipline=cd["discipline"],
                snow_mode=cd["snow_mode"],
                tier=cd["tier"],
                canopy=cd.get("canopy", "mixed"),
                race_dt=race_dt,
            )

            if not result.get("ok"):
                messages.error(request, result.get("error", "Recommendation failed."))
                return render(request, "nordic/calculator.html", {"form": form})

            NordicCalculationHistory.objects.create(
                user=request.user,
                venue=gpx_source,
                discipline=cd["discipline"],
                inputs={k: str(v) for k, v in cd.items() if k != "gpx_file"},
                results={k: v for k, v in result.items() if k != "course"},
            )

            return render(request, "nordic/results.html", {
                "form": form,
                "result": result,
                "discipline": cd["discipline"],
                "has_course": result.get("course") is not None,
                "gpx_source": gpx_source,
                "temp_unit": cd.get("temp_unit", "C"),
            })
        else:
            messages.error(request, "Please correct the errors below.")
    else:
        form = NordicCalculatorForm()

    return render(request, "nordic/calculator.html", {"form": form})
