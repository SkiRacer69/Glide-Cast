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


def get_price_id(plan_tier: str, interval: str) -> str | None:
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


@login_required
def paywall(request):
    profile, _ = Profile.objects.get_or_create(user=request.user)
    if profile.has_active_subscription():
        return redirect("calculator")
    return render(
        request,
        "billing/paywall.html",
        {
            "stripe_publishable_key": settings.STRIPE_PUBLISHABLE_KEY,
            "show_dev_bypass": True,
            "tiers": [
                {
                    "id": Profile.PlanTier.BASIC,
                    "name": "Basic",
                    "monthly": 5,
                },
                {
                    "id": Profile.PlanTier.PRO,
                    "name": "Pro",
                    "monthly": 15,
                },
            ],
        },
    )


@login_required
def create_checkout_session(request):
    profile, _ = Profile.objects.get_or_create(user=request.user)
    if profile.has_active_subscription():
        return redirect("calculator")

    plan_tier = request.GET.get("plan") or Profile.PlanTier.BASIC
    interval = request.GET.get("interval") or "monthly"
    if plan_tier not in (Profile.PlanTier.BASIC, Profile.PlanTier.PRO):
        plan_tier = Profile.PlanTier.BASIC
    if interval not in ("monthly", "annual"):
        interval = "monthly"

    price_id = get_price_id(plan_tier, interval)
    if not price_id:
        messages.error(request, "Stripe is not configured for this plan.")
        return redirect("paywall")

    s = _stripe()
    base = settings.APP_BASE_URL.rstrip("/")
    success_url = f"{base}{reverse('account')}?checkout=success"
    cancel_url = f"{base}{reverse('paywall')}?checkout=cancel"

    customer = None
    if profile.stripe_customer_id:
        customer = profile.stripe_customer_id

    session = s.checkout.Session.create(
        mode="subscription",
        customer=customer,
        customer_email=None if customer else request.user.email or None,
        line_items=[{"price": price_id, "quantity": 1}],
        subscription_data={"trial_period_days": 7},
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
def dev_bypass_subscription(request):
    """
    Development helper: one-click activate subscription for the current user.
    Only available to staff/superusers and should not be exposed in production.
    """
    profile, _ = Profile.objects.get_or_create(user=request.user)
    profile.admin_override_active = True
    profile.subscription_status = Profile.SubscriptionStatus.ACTIVE
    if not profile.plan_tier:
        profile.plan_tier = Profile.PlanTier.PRO
    profile.save(update_fields=["admin_override_active", "subscription_status", "plan_tier", "updated_at"])
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

    profile.save(update_fields=[
        "stripe_subscription_id", "subscription_status", "current_period_end",
        "pdf_period_start", "plan_tier", "billing_interval", "stripe_price_id", "updated_at",
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
