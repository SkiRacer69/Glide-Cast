"""
Custom login/signup with single-session enforcement, IP logging, and ToS.
"""
from __future__ import annotations

from datetime import timedelta

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import authenticate, login
from django.contrib.auth.views import LogoutView
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.http import require_http_methods

from .models import LoginIPHistory, Profile, TermsAcceptance, UserSession


def get_client_ip(request: HttpRequest) -> str:
    xff = request.META.get("HTTP_X_FORWARDED_FOR")
    if xff:
        return xff.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR", "")


def get_user_agent(request: HttpRequest) -> str:
    return (request.META.get("HTTP_USER_AGENT") or "")[:512]


@require_http_methods(["GET", "POST"])
@csrf_protect
def login_view(request: HttpRequest) -> HttpResponse:
    from django.contrib.auth.forms import AuthenticationForm

    if request.method == "POST":
        form = AuthenticationForm(request, data=request.POST)
        if form.is_valid():
            user = form.get_user()
            # Invalidate all other sessions for this user (single-session enforcement)
            UserSession.objects.filter(user=user).update(is_current=False)
            # Log in so we have session_key
            login(request, user)
            session_key = request.session.session_key
            if not session_key:
                request.session.create()
                session_key = request.session.session_key
            ip = get_client_ip(request)
            ua = get_user_agent(request)
            UserSession.objects.create(
                user=user,
                session_key=session_key,
                device_info=ua[:255],
                ip_address=ip if ip else None,
                is_current=True,
            )
            # "New location" email: send if this IP never seen before for this user (check before adding)
            ip_val = ip or "0.0.0.0"
            is_new_ip = ip and not LoginIPHistory.objects.filter(user=user, ip_address=ip).exists()
            # IP history and flagging
            LoginIPHistory.objects.create(
                user=user,
                ip_address=ip_val,
                location="",  # optional: geo lookup
            )
            now = timezone.now()
            day_ago = now - timedelta(hours=24)
            distinct_ips = (
                LoginIPHistory.objects.filter(user=user, created_at__gte=day_ago)
                .values("ip_address")
                .distinct()
                .count()
            )
            if distinct_ips > getattr(settings, "MAX_IP_LOGINS_PER_DAY_FLAG", 3):
                profile, _ = Profile.objects.get_or_create(user=user)
                if not profile.flagged_for_review_at:
                    profile.flagged_for_review_at = now
                    profile.save(update_fields=["flagged_for_review_at", "updated_at"])
            if is_new_ip and getattr(settings, "EMAIL_BACKEND", None) and "console" not in (settings.EMAIL_BACKEND or ""):
                try:
                    from django.core.mail import send_mail
                    send_mail(
                        "New login to glideCast",
                        f"New login detected from {ip} at {now.isoformat()} — if this wasn't you contact us immediately.",
                        getattr(settings, "DEFAULT_FROM_EMAIL", None) or "noreply@glidecast.com",
                        [user.email],
                        fail_silently=True,
                    )
                except Exception:
                    pass
            return redirect(request.GET.get("next") or settings.LOGIN_REDIRECT_URL)
        messages.error(request, "Invalid username or password.")
    else:
        form = AuthenticationForm(request)
    return render(request, "registration/login.html", {"form": form})


class LogoutViewWithMessage(LogoutView):
    def get_next_page(self):
        next_page = super().get_next_page()
        return next_page


def signup_with_tos(request: HttpRequest) -> HttpResponse:
    """Signup with mandatory ToS checkbox; store acceptance and enforce single session on first login."""
    from django.contrib.auth.forms import UserCreationForm
    from .forms import SignupFormWithToS

    if request.method == "POST":
        form = SignupFormWithToS(request.POST)
        if form.is_valid():
            user = form.save()
            Profile.objects.get_or_create(user=user)
            ip = get_client_ip(request)
            TermsAcceptance.objects.create(
                user=user,
                ip_address=ip or None,
                user_agent=get_user_agent(request),
            )
            UserSession.objects.filter(user=user).update(is_current=False)
            login(request, user, backend="django.contrib.auth.backends.ModelBackend")
            request.session.create()
            session_key = request.session.session_key
            UserSession.objects.create(
                user=user,
                session_key=session_key,
                device_info=get_user_agent(request)[:255],
                ip_address=ip or None,
                is_current=True,
            )
            LoginIPHistory.objects.create(user=user, ip_address=ip or "0.0.0.0", location="")
            return redirect(settings.LOGIN_REDIRECT_URL)
        messages.error(request, "Please correct the errors below.")
    else:
        form = SignupFormWithToS()
    return render(request, "accounts/signup.html", {"form": form})
