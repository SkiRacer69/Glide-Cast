from django import template

register = template.Library()


@register.filter
def to_f(value_c):
    """Convert Celsius float to Fahrenheit float."""
    try:
        return round(float(value_c) * 9 / 5 + 32, 1)
    except (TypeError, ValueError):
        return value_c


@register.filter
def temp(value_c, unit="C"):
    """Format a Celsius value as '−5.0°C' or '23.0°F' depending on unit."""
    try:
        v = float(value_c)
    except (TypeError, ValueError):
        return "—"
    if unit == "F":
        return f"{v * 9 / 5 + 32:.1f}°F"
    return f"{v:.1f}°C"


@register.filter
def temp_unit_label(unit):
    return "°F" if unit == "F" else "°C"
