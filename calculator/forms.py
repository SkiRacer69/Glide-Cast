from __future__ import annotations

from django import forms


class CalculatorForm(forms.Form):
    venue = forms.ChoiceField(choices=[("Sugarloaf", "Sugarloaf")])

    def __init__(self, *args, venue_choices=None, **kwargs):
        super().__init__(*args, **kwargs)
        if venue_choices:
            self.fields["venue"].choices = venue_choices
    discipline = forms.ChoiceField(choices=[("SL", "SL"), ("GS", "GS"), ("SuperG", "SuperG")])
    race_date = forms.DateField(widget=forms.DateInput(attrs={"type": "date"}))
    run1_time = forms.TimeField(widget=forms.TimeInput(attrs={"type": "time"}))
    run2_time = forms.TimeField(widget=forms.TimeInput(attrs={"type": "time"}))

    snow_mode = forms.ChoiceField(
        choices=[
            ("Auto", "Auto"),
            ("Fine / new snow", "Fine / new snow"),
            ("Coarse / transformed / artificial", "Coarse / transformed / artificial"),
            ("Aggressive cold / manmade", "Aggressive cold / manmade"),
            ("Injected / icy", "Injected / icy"),
        ]
    )
    dirty_abrasive = forms.BooleanField(required=False)

    slope_deg = forms.FloatField(min_value=0.0, max_value=45.0, initial=19.0)
    aspect_deg = forms.FloatField(min_value=0.0, max_value=359.0, initial=20.0)

    wind_coeff = forms.FloatField(min_value=0.01, max_value=0.40, initial=0.12)
    solar_coeff = forms.FloatField(min_value=0.0, max_value=8.0, initial=2.0)
    clear_night_coeff = forms.FloatField(min_value=0.0, max_value=6.0, initial=1.4)
    longwave_coeff = forms.FloatField(min_value=-2.0, max_value=2.0, initial=-0.25)
    latent_coeff = forms.FloatField(min_value=-0.5, max_value=0.5, initial=0.06)
    restore_coeff = forms.FloatField(min_value=0.0, max_value=0.30, initial=0.05)
    deep_auto_relax_coeff = forms.FloatField(min_value=0.0, max_value=0.10, initial=0.02)
    lapse_cap_f_per_1000ft = forms.FloatField(min_value=1.0, max_value=8.0, initial=4.5)

    use_manual_deep = forms.BooleanField(required=False)
    deep_start_f = forms.FloatField(required=False)
    deep_finish_f = forms.FloatField(required=False)

    cloud_attenuation = forms.FloatField(min_value=0.0, max_value=1.2, initial=0.75)
    diffuse_floor_frac = forms.FloatField(min_value=0.0, max_value=1.0, initial=0.35)
    albedo = forms.FloatField(min_value=0.2, max_value=0.95, initial=0.75)

    # v10 wet-snow / refreeze tuning (matches RaceWax Oracle V10 app defaults)
    wet_lock_band_f = forms.FloatField(min_value=0.0, max_value=1.0, initial=0.3)
    wet_refreeze_strength = forms.FloatField(min_value=0.0, max_value=10.0, initial=3.5)
    wet_deep_relax_scale = forms.FloatField(min_value=0.1, max_value=1.0, initial=0.4)

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("use_manual_deep"):
            if cleaned.get("deep_start_f") is None or cleaned.get("deep_finish_f") is None:
                raise forms.ValidationError("Provide both deep snow temps when manual override is enabled.")
        return cleaned

