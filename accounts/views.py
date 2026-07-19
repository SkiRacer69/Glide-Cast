import json
import logging
from datetime import timedelta

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.core.mail import mail_admins, send_mail
from django.db.models import Count
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from .features import check_feature_access, get_upgrade_prompt, pdf_download_limit
from .forms import ConditionsLogEntryForm
from .models import ConditionsLogEntry, LoginIPHistory, Profile, ScreenshotCaptureSignal, TermsAcceptance

logger = logging.getLogger(__name__)


@login_required
def account(request):
    profile, _ = Profile.objects.get_or_create(user=request.user)
    login_history = LoginIPHistory.objects.filter(user=request.user)[:50]
    tos = TermsAcceptance.objects.filter(user=request.user).first()
    limit = pdf_download_limit(profile)
    from billing.models import PDFDownload
    from django.utils import timezone
    period_start = profile.pdf_period_start
    if limit is not None and limit > 0:
        period_start = profile.pdf_period_start or timezone.now().replace(year=2000, month=1, day=1)
        pdf_count = PDFDownload.objects.filter(user=request.user, created_at__gte=period_start).count()
        pdf_remaining = max(0, limit - pdf_count)
    else:
        pdf_remaining = None
    show_conditions = check_feature_access(request.user, "conditions_log")
    return render(
        request,
        "accounts/account.html",
        {
            "profile": profile,
            "login_history": login_history,
            "tos_acceptance": tos,
            "pdf_remaining": pdf_remaining,
            "pdf_limit": limit,
            "upgrade_prompt": get_upgrade_prompt(request.user) or {},
            "show_conditions_log": show_conditions,
            "conditions_summary": _conditions_log_summary(request.user) if show_conditions else None,
        },
    )


def _conditions_log_summary(user):
    """Returns dict: accuracy_rate, most_used_products (list of (name, count)), best_venues (list of (venue, count))."""
    from collections import Counter

    qs = ConditionsLogEntry.objects.filter(user=user)
    with_result = qs.exclude(result="")
    total = with_result.count()
    correct = with_result.filter(result=ConditionsLogEntry.ResultChoice.CORRECT).count()
    accuracy_rate = round(correct / total * 100, 1) if total else None
    products = []
    for e in qs.only("run1_wax", "run2_wax"):
        if e.run1_wax:
            products.append(e.run1_wax)
        if e.run2_wax:
            products.append(e.run2_wax)
    most_used = Counter(products).most_common(5) if products else []
    best_venues = list(qs.values("venue").annotate(c=Count("id")).order_by("-c")[:5])
    return {"accuracy_rate": accuracy_rate, "most_used_products": most_used, "best_venues": best_venues, "total_entries": qs.count()}


@login_required
def conditions_log_list(request):
    if not check_feature_access(request.user, "conditions_log"):
        return render(
            request,
            "accounts/upgrade_prompt.html",
            {"feature": "Conditions log", "upgrade_prompt": get_upgrade_prompt(request.user) or {}},
        )
    entries = ConditionsLogEntry.objects.filter(user=request.user)[:100]
    summary = _conditions_log_summary(request.user)
    return render(
        request,
        "accounts/conditions_log_list.html",
        {"entries": entries, "summary": summary},
    )


@login_required
def conditions_log_add(request):
    if not check_feature_access(request.user, "conditions_log"):
        return render(
            request,
            "accounts/upgrade_prompt.html",
            {"feature": "Conditions log", "upgrade_prompt": get_upgrade_prompt(request.user) or {}},
        )
    if request.method == "POST":
        form = ConditionsLogEntryForm(request.POST)
        if form.is_valid():
            entry = form.save(commit=False)
            entry.user = request.user
            entry.save()
            return redirect("conditions_log_list")
    else:
        form = ConditionsLogEntryForm()
    return render(request, "accounts/conditions_log_form.html", {"form": form, "title": "Add log entry"})


@login_required
def conditions_log_edit(request, pk):
    if not check_feature_access(request.user, "conditions_log"):
        return render(
            request,
            "accounts/upgrade_prompt.html",
            {"feature": "Conditions log", "upgrade_prompt": get_upgrade_prompt(request.user) or {}},
        )
    entry = get_object_or_404(ConditionsLogEntry, pk=pk, user=request.user)
    if request.method == "POST":
        form = ConditionsLogEntryForm(request.POST, instance=entry)
        if form.is_valid():
            form.save()
            return redirect("conditions_log_list")
    else:
        form = ConditionsLogEntryForm(instance=entry)
    return render(request, "accounts/conditions_log_form.html", {"form": form, "title": "Edit log entry", "entry": entry})


@login_required
def conditions_log_delete(request, pk):
    if not check_feature_access(request.user, "conditions_log"):
        return redirect("conditions_log_list")
    entry = get_object_or_404(ConditionsLogEntry, pk=pk, user=request.user)
    if request.method == "POST":
        entry.delete()
        return redirect("conditions_log_list")
    return render(request, "accounts/conditions_log_confirm_delete.html", {"entry": entry})


@require_POST
@login_required
def report_screenshot_attempt(request):
    """
    Records best-effort browser key events associated with screenshots (PrintScreen, some OS shortcuts).
    Many screenshot tools never fire JavaScript; this is a deterrent + audit trail only.
    """
    try:
        data = json.loads(request.body.decode() or "{}")
    except json.JSONDecodeError:
        data = {}
    page_path = str(data.get("page_path") or "")[:512]
    signal_type = str(data.get("signal_type") or "unknown")[:64]
    detail = str(data.get("detail") or "")[:256]
    ua = (request.META.get("HTTP_USER_AGENT") or "")[:512]
    ip = request.META.get("REMOTE_ADDR")
    if ip:
        try:
            ip = str(ip)[:45]
        except Exception:
            ip = None

    window_start = timezone.now() - timedelta(minutes=15)
    prior_in_window = ScreenshotCaptureSignal.objects.filter(
        user=request.user, created_at__gte=window_start
    ).count()

    ScreenshotCaptureSignal.objects.create(
        user=request.user,
        page_path=page_path,
        signal_type=signal_type,
        detail=detail,
        user_agent=ua,
        ip_address=ip,
    )
    logger.warning(
        "Screenshot-related key signal: user=%s path=%s detail=%s",
        request.user.get_username(),
        page_path,
        detail,
    )

    # At most one email per user per 15 minutes (count was before this insert).
    if prior_in_window == 0:
        subject = f"[GlideCast™] Screenshot key signal — {request.user.get_username()}"
        body = (
            f"User: {request.user.get_username()} ({getattr(request.user, 'email', '') or 'no email'})\n"
            f"Path: {page_path}\n"
            f"Signal: {signal_type}\n"
            f"Detail: {detail}\n"
            f"IP: {ip or '—'}\n"
            f"UA: {ua[:200] or '—'}\n"
            f"\nNote: Browsers cannot detect all screenshots; this is a best-effort key combo log.\n"
        )
        alert_to = getattr(settings, "SCREENSHOT_ALERT_EMAIL", "").strip()
        if alert_to:
            send_mail(
                subject,
                body,
                getattr(settings, "DEFAULT_FROM_EMAIL", "noreply@glidecast.com"),
                [alert_to],
                fail_silently=True,
            )
        elif settings.ADMINS:
            mail_admins(subject, body, fail_silently=True)

    return JsonResponse({"ok": True})


def terms_of_service(request):
    return render(request, "legal/terms_of_service.html", {})
