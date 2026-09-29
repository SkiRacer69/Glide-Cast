"""Nordic wax selector — multi-factor scoring engine.

Translates condition outputs (temp, snow_type, humidity, tier) into
PRIMARY + ALT1 + ALT2 recommendations for glide and kick wax.

DO NOT call this before classify_snow() has run — snow_type is required.
"""
from __future__ import annotations

from typing import Any

from .wax_db import BINDERS, GLIDE_WAX, KICK_WAX, KLISTER

# ---------------------------------------------------------------------------
# Dimension weights
# ---------------------------------------------------------------------------
_GLIDE_W = {
    "temperature": 0.50,
    "snow_type":   0.25,
    "humidity":    0.10,
    "durability":  0.08,
    "race_match":  0.07,
}

_KICK_W = {
    "temperature": 0.45,
    "snow_type":   0.55,
}


# ---------------------------------------------------------------------------
# Scoring helpers
# ---------------------------------------------------------------------------

def _temp_score(temp_c: float, temp_min: float, temp_max: float) -> float:
    """1.0 at band center, ~0.70 at band edges, falls to 0.0 at 5 °C outside."""
    if temp_c < temp_min:
        return max(0.0, 1.0 - (temp_min - temp_c) / 5.0)
    if temp_c > temp_max:
        return max(0.0, 1.0 - (temp_c - temp_max) / 5.0)
    mid = (temp_min + temp_max) / 2.0
    half_w = max((temp_max - temp_min) / 2.0, 0.5)
    return 1.0 - 0.30 * abs(temp_c - mid) / half_w


def _humidity_score(humidity_pct: float, humidity_max: float) -> float:
    if humidity_pct <= humidity_max:
        return 1.0
    return max(0.1, 1.0 - (humidity_pct - humidity_max) / 30.0)


def _durability_score(durability: int, tier: str) -> float:
    """Training/recreational prefers durability; race tier doesn't care."""
    if tier in ("training", "recreational"):
        return durability / 10.0
    return 1.0


def _race_match_score(product_tier: str, requested_tier: str) -> float:
    if product_tier == requested_tier:
        return 1.0
    order = ["recreational", "training", "race"]
    try:
        diff = abs(order.index(product_tier) - order.index(requested_tier))
    except ValueError:
        return 0.5
    return 0.6 if diff == 1 else 0.3


def _pct(score: float) -> int:
    return min(100, max(0, round(score * 100)))


# ---------------------------------------------------------------------------
# Glide wax selector
# ---------------------------------------------------------------------------

def select_glide(
    temp_c: float,
    snow_type: str,
    humidity_pct: float,
    tier: str = "race",
    temp_range: tuple[float, float] | None = None,
) -> dict[str, Any]:
    """Return primary + alt1 + alt2 glide wax recommendations.

    temp_range: (course_min_temp, course_max_temp) — if provided, products are
    penalized if they don't cover the full course range.
    """
    scored = []
    for w in GLIDE_WAX:
        t_score = _temp_score(temp_c, w["temp_min"], w["temp_max"])

        # If there's a temp range across the course, penalize products that
        # miss part of it: blend the at-time score with the worst range endpoint.
        if temp_range:
            t_lo = _temp_score(temp_range[0], w["temp_min"], w["temp_max"])
            t_hi = _temp_score(temp_range[1], w["temp_min"], w["temp_max"])
            worst = min(t_lo, t_hi)
            t_score = 0.6 * t_score + 0.4 * worst

        sn_score  = w["snow"].get(snow_type, 0.0)
        hum_score = _humidity_score(humidity_pct, w["humidity_max"])
        dur_score = _durability_score(w["durability"], tier)
        rce_score = _race_match_score(w["tier"], tier)

        total = (
            _GLIDE_W["temperature"] * t_score
            + _GLIDE_W["snow_type"]  * sn_score
            + _GLIDE_W["humidity"]   * hum_score
            + _GLIDE_W["durability"] * dur_score
            + _GLIDE_W["race_match"] * rce_score
        )

        scored.append({
            **w,
            "score": total,
            "dim_scores": {
                "temperature": _pct(t_score),
                "snow_type":   _pct(sn_score),
                "humidity":    _pct(hum_score),
                "durability":  _pct(dur_score),
                "race_match":  _pct(rce_score),
            },
        })

    scored.sort(key=lambda x: x["score"], reverse=True)

    def _rec(w: dict) -> dict:
        return {
            "brand":          w["brand"],
            "product":        w["product"],
            "code":           w["code"],
            "tier":           w["tier"],
            "hex":            w["hex"],
            "notes":          w["notes"],
            "application":    w["application"],
            "temp_min":       w["temp_min"],
            "temp_max":       w["temp_max"],
            "in_band":        w["temp_min"] <= temp_c <= w["temp_max"],
            "confidence_pct": _pct(w["score"]),
            "dim_scores":     w["dim_scores"],
        }

    primary = _rec(scored[0]) if scored else {}
    alt1    = _rec(scored[1]) if len(scored) > 1 else None
    alt2    = _rec(scored[2]) if len(scored) > 2 else None

    return {
        "primary":               primary,
        "alt1":                  alt1,
        "alt2":                  alt2,
        "overall_confidence_pct": primary.get("confidence_pct", 0),
        "tier_used":             tier,
    }


# ---------------------------------------------------------------------------
# Kick wax selector (Classic only)
# ---------------------------------------------------------------------------

def _needs_klister(snow_type: str, temp_c: float) -> bool:
    if snow_type in {"icy", "hard_groomed", "wet", "spring"}:
        return True
    if snow_type == "transformed" and temp_c >= -1.5:
        return True
    return False


def select_kick(
    temp_c: float,
    snow_type: str,
    tier: str = "race",
) -> dict[str, Any]:
    """Return primary + alt1 + alt2 kick wax recommendations (Classic only)."""
    use_klister = _needs_klister(snow_type, temp_c)
    pool = KLISTER if use_klister else KICK_WAX

    scored = []
    for w in pool:
        t_score  = _temp_score(temp_c, w["temp_min"], w["temp_max"])
        sn_score = 1.0 if snow_type in w["snow_types"] else 0.2

        total = (
            _KICK_W["temperature"] * t_score
            + _KICK_W["snow_type"] * sn_score
        )

        scored.append({
            **w,
            "score": total,
            "dim_scores": {
                "temperature": _pct(t_score),
                "snow_type":   _pct(sn_score),
            },
        })

    scored.sort(key=lambda x: x["score"], reverse=True)

    def _rec(w: dict) -> dict:
        return {
            "brand":          w["brand"],
            "product":        w["product"],
            "code":           w["code"],
            "hex":            w["hex"],
            "notes":          w["notes"],
            "color":          w.get("color"),
            "is_klister":     use_klister,
            "temp_min":       w["temp_min"],
            "temp_max":       w["temp_max"],
            "in_band":        w["temp_min"] <= temp_c <= w["temp_max"],
            "confidence_pct": _pct(w["score"]),
            "dim_scores":     w["dim_scores"],
        }

    primary = _rec(scored[0]) if scored else {}
    alt1    = _rec(scored[1]) if len(scored) > 1 else None
    alt2    = _rec(scored[2]) if len(scored) > 2 else None

    binder = _pick_binder(use_klister)

    return {
        "primary":               primary,
        "alt1":                  alt1,
        "alt2":                  alt2,
        "is_klister":            use_klister,
        "binder":                binder,
        "overall_confidence_pct": primary.get("confidence_pct", 0),
    }


def _pick_binder(use_klister: bool) -> dict:
    pool = [b for b in BINDERS if b.get("use_with_klister") == use_klister]
    return (pool or BINDERS)[0]
