from __future__ import annotations

import os
from pathlib import Path

from django import forms
from django.forms.widgets import DateTimeInput

_COURSES_DIR = Path(__file__).resolve().parent / "courses"

PRE_LOADED_CHOICES = [("", "— select a pre-loaded course —")] + sorted([
    (p.stem, p.stem.replace("_", " ").title())
    for p in _COURSES_DIR.glob("*.gpx")
], key=lambda x: x[1])

_DISPLAY_NAMES = {
    "beitostolen":        "Beitostølen",
    "canmore":            "Canmore",
    "cogne":              "Cogne",
    "craftsbury":         "Craftsbury",
    "davos":              "Davos",
    "falun":              "Falun",
    "gallivare":          "Gällivare",
    "lahti":              "Lahti",
    "lake_placid":        "Lake Placid",
    "lenzerheide":        "Lenzerheide",
    "lillehammer":        "Lillehammer",
    "oberstdorf":         "Oberstdorf",
    "oslo_holmenkollen":  "Oslo / Holmenkollen",
    "ostersund":          "Östersund",
    "planica":            "Planica",
    "ruka_kuusamo":       "Ruka / Kuusamo",
    "trondheim_granasen": "Trondheim / Granåsen",
    "val_di_fiemme":      "Val di Fiemme",
}

PRE_LOADED_CHOICES = [("", "— select a pre-loaded course —")] + sorted([
    (p.stem, _DISPLAY_NAMES.get(p.stem, p.stem.replace("_", " ").title()))
    for p in _COURSES_DIR.glob("*.gpx")
], key=lambda x: x[1])


class NordicCalculatorForm(forms.Form):
    temp_unit = forms.ChoiceField(
        choices=[("C", "Celsius (°C)"), ("F", "Fahrenheit (°F)")],
        initial="C",
        required=False,
    )
    discipline = forms.ChoiceField(
        choices=[("Classic", "Classic"), ("Skate", "Skate")],
    )
    snow_mode = forms.ChoiceField(
        choices=[
            ("auto", "Auto-detect"),
            ("new", "New / fresh snow"),
            ("packed", "Packed / groomed"),
            ("transformed", "Transformed / settled"),
            ("hard_groomed", "Hard-groomed / firm"),
            ("icy", "Icy / refrozen"),
            ("wet", "Wet / slushy"),
            ("spring", "Spring corn snow"),
        ]
    )
    tier = forms.ChoiceField(
        choices=[
            ("race", "Race"),
            ("training", "Training"),
            ("recreational", "Recreational"),
        ]
    )
    canopy = forms.ChoiceField(
        required=False,
        initial="mixed",
        choices=[
            ("open",   "Open — exposed ridges / alpine meadows"),
            ("mixed",  "Mixed — partial forest (typical Nordic venue)"),
            ("dense",  "Dense — deep boreal / spruce forest"),
        ],
        help_text="Tree canopy cover affects solar shade on snow surface.",
    )
    race_datetime = forms.DateTimeField(
        required=False,
        widget=DateTimeInput(attrs={"type": "datetime-local"}),
        help_text="Race or training start time (defaults to tomorrow 10:00 AM). Used for solar position calculation.",
        input_formats=["%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M"],
    )
    pre_loaded_course = forms.ChoiceField(
        choices=PRE_LOADED_CHOICES,
        required=False,
        help_text="Use a pre-loaded FIS World Cup course, or upload your own GPX below.",
    )
    gpx_file = forms.FileField(
        required=False,
        help_text="Upload your own GPX course file.",
    )

    def clean_gpx_file(self):
        f = self.cleaned_data.get("gpx_file")
        if f is None:
            return None
        if f.size > 10 * 1024 * 1024:
            raise forms.ValidationError("GPX file must be under 10 MB.")
        if not f.name.lower().endswith(".gpx"):
            raise forms.ValidationError("File must have a .gpx extension.")
        return f

    def clean_canopy(self):
        return self.cleaned_data.get("canopy") or "mixed"

    def clean_temp_unit(self):
        return self.cleaned_data.get("temp_unit") or "C"

    def clean(self):
        cd = super().clean()
        gpx = cd.get("gpx_file")
        course = cd.get("pre_loaded_course") or ""
        if not gpx and not course:
            raise forms.ValidationError(
                "Please either upload a GPX file or select a pre-loaded course."
            )
        return cd
