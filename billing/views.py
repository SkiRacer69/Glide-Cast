from __future__ import annotations

import json
from datetime import datetime, timezone

import stripe
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.csrf import csrf_exempt

from accounts.models import Profile


def _stripe():
    stripe.api_key = settings.STRIPE_SECRET_KEY
    return stripe


# Map Stripe price ID -> (plan_tier, billing_interval) for webhook
def _price_to_plan():
    m = {}
    for key, attr in [
        ("STRIPE_PRICE_BASIC_MONTHLY", (Profile.PlanTier.BASIC, Profile.BillingInterval.MONTHLY)),
        ("STRIPE_PRICE_BASIC_ANNUAL", (Profile.PlanTier.BASIC, Profile.BillingInterval.ANNUAL)),
        ("STRIPE_PRICE_PRO_MONTHLY", (Profile.PlanTier.PRO, Profile.BillingInterval.MONTHLY)),
        ("STRIPE_PRICE_PRO_ANNUAL", (Profile.PlanTier.PRO, Profile.BillingInterval.ANNUAL)),
        ("STRIPE_PRICE_NORDIC_BASIC_MONTHLY", (Profile.PlanTier.BASIC, Profile.BillingInterval.MONTHLY)),
        ("STRIPE_PRICE_NORDIC_BASIC_ANNUAL", (Profile.PlanTier.BASIC, Profile.BillingInterval.ANNUAL)),
        ("STRIPE_PRICE_NORDIC_PRO_MONTHLY", (Profile.PlanTier.PRO, Profile.BillingInterval.MONTHLY)),
        ("STRIPE_PRICE_NORDIC_PRO_ANNUAL", (Profile.PlanTier.PRO, Profile.BillingInterval.ANNUAL)),
        ("STRIPE_PRICE_ALL_MONTHLY", (Profile.PlanTier.ALL, Profile.BillingInterval.MONTHLY)),
        ("STRIPE_PRICE_ALL_ANNUAL", (Profile.PlanTier.ALL, Profile.BillingInterval.ANNUAL)),
        # Legacy Stripe price env vars → Basic / Pro
        ("STRIPE_PRICE_CLUB_MONTHLY", (Profile.PlanTier.BASIC, Profile.BillingInterval.MONTHLY)),
        ("STRIPE_PRICE_CLUB_ANNUAL", (Profile.PlanTier.BASIC, Profile.BillingInterval.ANNUAL)),
        ("STRIPE_PRICE_INDIVIDUAL_MONTHLY", (Profile.PlanTier.PRO, Profile.BillingInterval.MONTHLY)),
        ("STRIPE_PRICE_INDIVIDUAL_ANNUAL", (Profile.PlanTier.PRO, Profile.BillingInterval.ANNUAL)),
        ("STRIPE_PRICE_COACH_MONTHLY", (Profile.PlanTier.PRO, Profile.BillingInterval.MONTHLY)),
        ("STRIPE_PRICE_COACH_ANNUAL", (Profile.PlanTier.PRO, Profile.BillingInterval.ANNUAL)),
        ("STRIPE_PRICE_RACE_DEPT_MONTHLY", (Profile.PlanTier.PRO, Profile.BillingInterval.MONTHLY)),
        ("STRIPE_PRICE_RACE_DEPT_ANNUAL", (Profile.PlanTier.PRO, Profile.BillingInterval.ANNUAL)),
    ]:
        pid = getattr(settings, key, "") or ""
        if pid:
            m[pid] = attr
    if getattr(settings, "STRIPE_PRICE_ID", ""):
        m[settings.STRIPE_PRICE_ID] = (Profile.PlanTier.PRO, Profile.BillingInterval.MONTHLY)
    return m


PRICE_TO_PLAN = None


def get_price_to_plan():
    global PRICE_TO_PLAN
    if PRICE_TO_PLAN is None:
        PRICE_TO_PLAN = _price_to_plan()
    return PRICE_TO_PLAN


def get_price_id(plan_tier: str, interval: str, sport: str = "alpine") -> str | None:
    # All Access tier
    if plan_tier == Profile.PlanTier.ALL:
        key = "STRIPE_PRICE_ALL_MONTHLY" if interval == "monthly" else "STRIPE_PRICE_ALL_ANNUAL"
        return getattr(settings, key, "") or None

    if sport == "nordic":
        nordic_key = {
            (Profile.PlanTier.BASIC, "monthly"): "STRIPE_PRICE_NORDIC_BASIC_MONTHLY",
            (Profile.PlanTier.BASIC, "annual"):  "STRIPE_PRICE_NORDIC_BASIC_ANNUAL",
            (Profile.PlanTier.PRO,   "monthly"): "STRIPE_PRICE_NORDIC_PRO_MONTHLY",
            (Profile.PlanTier.PRO,   "annual"):  "STRIPE_PRICE_NORDIC_PRO_ANNUAL",
        }.get((plan_tier, interval))
        if nordic_key:
            pid = getattr(settings, nordic_key, "") or ""
            if pid:
                return pid
        # Fall through to alpine prices if Nordic-specific ones aren't configured yet

    primary = {
        (Profile.PlanTier.BASIC, "monthly"): "STRIPE_PRICE_BASIC_MONTHLY",
        (Profile.PlanTier.BASIC, "annual"): "STRIPE_PRICE_BASIC_ANNUAL",
        (Profile.PlanTier.PRO, "monthly"): "STRIPE_PRICE_PRO_MONTHLY",
        (Profile.PlanTier.PRO, "annual"): "STRIPE_PRICE_PRO_ANNUAL",
    }.get((plan_tier, interval))
    legacy = {
        (Profile.PlanTier.BASIC, "monthly"): "STRIPE_PRICE_CLUB_MONTHLY",
        (Profile.PlanTier.BASIC, "annual"): "STRIPE_PRICE_CLUB_ANNUAL",
        (Profile.PlanTier.PRO, "monthly"): "STRIPE_PRICE_INDIVIDUAL_MONTHLY",
        (Profile.PlanTier.PRO, "annual"): "STRIPE_PRICE_INDIVIDUAL_ANNUAL",
    }.get((plan_tier, interval))
    for key in (primary, legacy):
        if not key:
            continue
        pid = getattr(settings, key, "") or ""
        if pid:
            return pid
    if plan_tier == Profile.PlanTier.PRO and interval == "monthly":
        return getattr(settings, "STRIPE_PRICE_ID", "") or None
    return None


_SPORT_PRICING = {
    "alpine": [
        {"id": Profile.PlanTier.BASIC, "name": "Basic", "monthly": 5},
        {"id": Profile.PlanTier.PRO,   "name": "Pro",   "monthly": 15},
        {"id": Profile.PlanTier.ALL,   "name": "All Access", "monthly": 30},
    ],
    "nordic": [
        {"id": Profile.PlanTier.BASIC, "name": "Basic", "monthly": 7},
        {"id": Profile.PlanTier.PRO,   "name": "Pro",   "monthly": 20},
        {"id": Profile.PlanTier.ALL,   "name": "All Access", "monthly": 30},
    ],
}


def paywall(request):
    if request.user.is_authenticated:
        profile, _ = Profile.objects.get_or_create(user=request.user)
        if profile.has_active_subscription():
            return redirect("calculator")
    sport = request.GET.get("sport", "alpine")
    if sport not in _SPORT_PRICING:
        sport = "alpine"
    return render(
        request,
        "billing/paywall.html",
        {
            "stripe_publishable_key": settings.STRIPE_PUBLISHABLE_KEY,
            "show_dev_bypass": request.user.is_authenticated,
            "sport": sport,
            "tiers": _SPORT_PRICING[sport],
        },
    )


@login_required
def create_checkout_session(request):
    profile, _ = Profile.objects.get_or_create(user=request.user)
    if profile.has_active_subscription():
        return redirect("calculator")

    plan_tier = request.GET.get("plan") or Profile.PlanTier.BASIC
    interval = request.GET.get("interval") or "monthly"
    sport = request.GET.get("sport", "alpine")
    if plan_tier not in (Profile.PlanTier.BASIC, Profile.PlanTier.PRO, Profile.PlanTier.ALL):
        plan_tier = Profile.PlanTier.BASIC
    if interval not in ("monthly", "annual"):
        interval = "monthly"
    if sport not in _SPORT_PRICING:
        sport = "alpine"

    price_id = get_price_id(plan_tier, interval, sport=sport)
    if not price_id:
        messages.error(request, "Stripe is not configured for this plan.")
        return redirect(f"{reverse('paywall')}?sport={sport}")

    s = _stripe()
    base = settings.APP_BASE_URL.rstrip("/")
    success_url = f"{base}{reverse('account')}?checkout=success"
    cancel_url = f"{base}{reverse('paywall')}?checkout=cancel"

    customer = None
    if profile.stripe_customer_id:
        customer = profile.stripe_customer_id

    sport_access = "all" if plan_tier == Profile.PlanTier.ALL else sport
    session = s.checkout.Session.create(
        mode="subscription",
        customer=customer,
        customer_email=None if customer else request.user.email or None,
        line_items=[{"price": price_id, "quantity": 1}],
        subscription_data={
            "trial_period_days": 7,
            "metadata": {"sport_access": sport_access},
        },
        allow_promotion_codes=True,
        success_url=success_url,
        cancel_url=cancel_url,
    )
    return redirect(session.url)


@login_required
def customer_portal(request):
    profile, _ = Profile.objects.get_or_create(user=request.user)
    if not profile.stripe_customer_id:
        messages.error(request, "No billing profile found yet.")
        return redirect("account")

    s = _stripe()
    return_url = settings.STRIPE_BILLING_PORTAL_RETURN_URL or f"{settings.APP_BASE_URL.rstrip('/')}{reverse('account')}"
    portal = s.billing_portal.Session.create(customer=profile.stripe_customer_id, return_url=return_url)
    return redirect(portal.url)


@login_required
def billing_settings(request):
    profile, _ = Profile.objects.get_or_create(user=request.user)
    show_cancel = profile.has_active_subscription() or profile.admin_override_active
    return render(request, "billing/billing_settings.html", {
        "profile": profile,
        "show_cancel": show_cancel,
    })


@login_required
def cancel_subscription(request):
    if request.method != "POST":
        return redirect("account")

    profile, _ = Profile.objects.get_or_create(user=request.user)

    # Dev-bypass / admin-override cancellation
    if profile.admin_override_active:
        profile.admin_override_active = False
        profile.admin_override_plan = ""
        profile.subscription_status = Profile.SubscriptionStatus.CANCELED
        profile.save(update_fields=["admin_override_active", "admin_override_plan", "subscription_status", "updated_at"])
        messages.success(request, "Your plan has been cancelled.")
        return redirect("account")

    # Stripe subscription cancellation — cancel at period end via API
    if profile.stripe_subscription_id:
        try:
            s = _stripe()
            s.Subscription.modify(profile.stripe_subscription_id, cancel_at_period_end=True)
            profile.subscription_status = Profile.SubscriptionStatus.CANCELED
            profile.save(update_fields=["subscription_status", "updated_at"])
            messages.success(request, "Your subscription has been cancelled and will end at the current billing period.")
        except Exception as exc:
            messages.error(request, f"Could not cancel via API: {exc}. Please use Manage billing to cancel.")
        return redirect("account")

    # Stripe customer exists but no sub ID — send to portal
    if profile.stripe_customer_id:
        return redirect("customer_portal")

    messages.info(request, "No active subscription found.")
    return redirect("account")


@login_required
def dev_bypass_subscription(request):
    DEV_CODE = "33112577"
    if request.method != "POST" or request.POST.get("dev_code") != DEV_CODE:
        messages.error(request, "Invalid access code.")
        return redirect("paywall")
    profile, _ = Profile.objects.get_or_create(user=request.user)
    profile.admin_override_active = True
    profile.admin_override_plan = Profile.PlanTier.ALL
    profile.subscription_status = Profile.SubscriptionStatus.ACTIVE
    profile.plan_tier = Profile.PlanTier.ALL
    profile.sport_access = "all"
    profile.save(update_fields=["admin_override_active", "admin_override_plan", "subscription_status", "plan_tier", "sport_access", "updated_at"])
    messages.success(request, "Dev bypass enabled: subscription marked active for this account.")
    return redirect("calculator")


def _upsert_profile_from_subscription(profile: Profile, sub: dict) -> None:
    profile.stripe_subscription_id = sub.get("id", "") or profile.stripe_subscription_id
    status = (sub.get("status") or "none").lower()
    profile.subscription_status = status

    cpe = sub.get("current_period_end")
    cps = sub.get("current_period_start")
    if cpe:
        profile.current_period_end = datetime.fromtimestamp(int(cpe), tz=timezone.utc)
    if cps:
        period_start = datetime.fromtimestamp(int(cps), tz=timezone.utc)
        if not profile.pdf_period_start or (profile.current_period_end and period_start > profile.pdf_period_start):
            profile.pdf_period_start = period_start

    items = sub.get("items", {}).get("data", [])
    price_id = items[0].get("price", {}).get("id") if items else None
    if price_id:
        mapping = get_price_to_plan()
        if price_id in mapping:
            plan_tier, billing_interval = mapping[price_id]
            profile.plan_tier = plan_tier
            profile.billing_interval = billing_interval
            profile.stripe_price_id = price_id

    sport_access = (sub.get("metadata") or {}).get("sport_access", "")
    if sport_access in ("alpine", "nordic", "all"):
        profile.sport_access = sport_access
    elif profile.plan_tier == Profile.PlanTier.ALL:
        profile.sport_access = "all"

    profile.save(update_fields=[
        "stripe_subscription_id", "subscription_status", "current_period_end",
        "pdf_period_start", "plan_tier", "billing_interval", "stripe_price_id",
        "sport_access", "updated_at",
    ])


@csrf_exempt
def stripe_webhook(request: HttpRequest):
    payload = request.body
    sig_header = request.META.get("HTTP_STRIPE_SIGNATURE", "")

    try:
        event = stripe.Webhook.construct_event(payload, sig_header, settings.STRIPE_WEBHOOK_SECRET)
    except Exception as exc:
        return JsonResponse({"error": str(exc)}, status=400)

    event_type = event["type"]
    data = event["data"]["object"]

    if event_type == "checkout.session.completed":
        customer_id = data.get("customer")
        subscription_id = data.get("subscription")
        if customer_id and subscription_id:
            s = _stripe()
            sub = s.Subscription.retrieve(subscription_id)
            try:
                profile = Profile.objects.get(stripe_customer_id=customer_id)
            except Profile.DoesNotExist:
                email = (data.get("customer_details") or {}).get("email")
                if email:
                    profile = Profile.objects.filter(user__email=email).first()
                else:
                    profile = None
            if profile:
                profile.stripe_customer_id = customer_id
                _upsert_profile_from_subscription(profile, sub)

    if event_type in {
        "customer.subscription.created",
        "customer.subscription.updated",
        "customer.subscription.deleted",
    }:
        customer_id = data.get("customer")
        if customer_id:
            profile = Profile.objects.filter(stripe_customer_id=customer_id).first()
            if profile:
                _upsert_profile_from_subscription(profile, data)

    if event_type == "invoice.payment_failed":
        customer_id = data.get("customer")
        if customer_id:
            profile = Profile.objects.filter(stripe_customer_id=customer_id).first()
            if profile:
                profile.subscription_status = "past_due"
                profile.save(update_fields=["subscription_status", "updated_at"])

    return HttpResponse(status=200)
