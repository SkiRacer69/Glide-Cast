"""
Feature gating by plan tier. Use check_feature_access(user, feature_name).
Never expose formulas or model internals — gate UI/API only.
"""
from __future__ import annotations

from accounts.models import Profile

# Plan tier order for comparison (higher index = higher tier)
PLAN_ORDER = (
    Profile.PlanTier.BASIC,
    Profile.PlanTier.PRO,
)

# Basic plan: these five mountains (subset of engine VENUES keys, stable order)
BASIC_VENUE_SLUGS = (
    "Sugarloaf",
    "Sunday River",
    "Gore Mountain",
    "Mount Snow",
    "Killington",
)


def basic_venues_for_engine(engine_venue_keys: list[str]) -> list[str]:
    """Mountains included on Basic; only keys that exist in the engine."""
    key_set = set(engine_venue_keys)
    return [v for v in BASIC_VENUE_SLUGS if v in key_set]


# feature_name -> minimum plan tier required
FEATURE_PLAN = {
    "pro_insights": Profile.PlanTier.PRO,
    "pdf_export": Profile.PlanTier.PRO,
    "energy_panel": Profile.PlanTier.PRO,
    "multiple_venues": Profile.PlanTier.PRO,
    "conditions_log": Profile.PlanTier.PRO,
    "team_profiles": Profile.PlanTier.PRO,
    "api_access": Profile.PlanTier.PRO,
    "custom_venue": Profile.PlanTier.PRO,
}

# Human-readable next tier and price for upgrade prompts
UPGRADE_PROMPTS = {
    Profile.PlanTier.BASIC: {
        "next_tier": "Pro",
        "price_monthly": 15,
        "price_annual": None,
    },
    Profile.PlanTier.PRO: {
        "next_tier": None,
        "price_monthly": None,
        "price_annual": None,
    },
}


def plan_rank(tier: str) -> int:
    try:
        return PLAN_ORDER.index(tier)
    except ValueError:
        return -1


def check_feature_access(user, feature_name: str) -> bool:
    """Returns True if the user's plan allows the feature."""
    if not user or not user.is_authenticated:
        return False
    try:
        profile = Profile.objects.get(user=user)
    except Profile.DoesNotExist:
        return False
    if profile.suspended_at or profile.terminated_at:
        return False
    required = FEATURE_PLAN.get(feature_name)
    if required is None:
        return False
    effective = profile.effective_plan_tier()
    return plan_rank(effective) >= plan_rank(required)


def get_upgrade_prompt(user):
    """Returns dict with next_tier, price_monthly, price_annual or None if no upgrade."""
    if not user or not user.is_authenticated:
        return None
    try:
        profile = Profile.objects.get(user=user)
    except Profile.DoesNotExist:
        return UPGRADE_PROMPTS.get(Profile.PlanTier.BASIC)
    effective = profile.effective_plan_tier()
    return UPGRADE_PROMPTS.get(effective)


def pdf_download_limit(profile: Profile) -> int | None:
    """None = unlimited. 0 = no PDF. N = N per billing period."""
    tier = profile.effective_plan_tier()
    if tier == Profile.PlanTier.BASIC:
        return 0
    return None
