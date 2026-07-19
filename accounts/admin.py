from django.contrib import admin
from django.contrib.auth import get_user_model
from django.db.models import Count
from django.shortcuts import render
from django.urls import path
from django.utils import timezone
from .models import (
    ConditionsLogEntry,
    LoginIPHistory,
    Profile,
    ScreenshotCaptureSignal,
    TermsAcceptance,
    UserSession,
)

User = get_user_model()


@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "plan_tier",
        "billing_interval",
        "subscription_status",
        "admin_override_active",
        "flagged_for_review_at",
        "suspended_at",
        "terminated_at",
        "current_period_end",
    )
    list_filter = ("subscription_status", "admin_override_active", "plan_tier", "billing_interval")
    search_fields = ("user__username", "user__email", "stripe_customer_id", "stripe_subscription_id")
    actions = ["suspend_accounts", "terminate_accounts"]

    @admin.action(description="Suspend selected accounts")
    def suspend_accounts(self, request, queryset):
        from django.utils import timezone
        n = queryset.update(suspended_at=timezone.now())
        self.message_user(request, f"Suspend applied to {n} account(s).")

    @admin.action(description="Terminate selected accounts")
    def terminate_accounts(self, request, queryset):
        from django.utils import timezone
        from django.core.mail import send_mail
        from django.conf import settings
        for profile in queryset:
            profile.terminated_at = timezone.now()
            profile.terminated_reason = "Terminated by admin."
            profile.save(update_fields=["terminated_at", "terminated_reason", "updated_at"])
            try:
                send_mail(
                    "Account terminated — GlideCast™",
                    "Your GlideCast™ account has been terminated. Reason: Terminated by admin. If you believe this is an error, contact support.\n\nRaceWax Oracle℠ is a service of GlideCast™.",
                    getattr(settings, "DEFAULT_FROM_EMAIL", "noreply@glidecast.com"),
                    [profile.user.email],
                    fail_silently=True,
                )
            except Exception:
                pass
        self.message_user(request, f"Terminated {queryset.count()} account(s).")

    def get_urls(self):
        urls = super().get_urls()
        custom = [path("security-dashboard/", self.admin_site.admin_view(self.security_dashboard), name="accounts_security_dashboard")]
        return custom + urls

    def security_dashboard(self, request):
        from django.utils import timezone
        from datetime import timedelta
        from billing.models import PDFDownload

        now = timezone.now()
        day_ago = now - timedelta(hours=24)

        flagged = Profile.objects.filter(flagged_for_review_at__gte=day_ago).select_related("user").order_by("-flagged_for_review_at")

        high_pdf = (
            PDFDownload.objects.filter(created_at__gte=day_ago)
            .values("user")
            .annotate(c=Count("id"))
            .filter(c__gt=10, user__isnull=False)
            .order_by("-c")
        )
        high_pdf_users = []
        for row in high_pdf:
            try:
                high_pdf_users.append(User.objects.get(pk=row["user"]))
            except User.DoesNotExist:
                pass

        revenue_by_plan = list(
            Profile.objects.filter(plan_tier__isnull=False)
            .exclude(plan_tier="")
            .values("plan_tier")
            .annotate(c=Count("id"))
            .order_by("-c")
        )

        context = {
            "title": "Security dashboard",
            "flagged_accounts": flagged,
            "high_pdf_users": high_pdf_users,
            "revenue_by_plan": revenue_by_plan,
            "opts": self.model._meta,
        }
        return render(request, "admin/accounts/security_dashboard.html", context)


@admin.register(UserSession)
class UserSessionAdmin(admin.ModelAdmin):
    list_display = ("user", "session_key", "ip_address", "is_current", "created_at")
    list_filter = ("is_current",)
    search_fields = ("user__username", "session_key")


@admin.register(ScreenshotCaptureSignal)
class ScreenshotCaptureSignalAdmin(admin.ModelAdmin):
    list_display = ("user", "detail", "page_path", "ip_address", "created_at")
    list_filter = ("created_at",)
    search_fields = ("user__username", "user__email", "page_path", "detail", "ip_address")
    readonly_fields = ("user", "page_path", "signal_type", "detail", "user_agent", "ip_address", "created_at")
    ordering = ("-created_at",)

    def has_add_permission(self, request):
        return False


@admin.register(LoginIPHistory)
class LoginIPHistoryAdmin(admin.ModelAdmin):
    list_display = ("user", "ip_address", "location", "flagged", "created_at")
    list_filter = ("flagged", "created_at")
    search_fields = ("user__username", "ip_address")


@admin.register(TermsAcceptance)
class TermsAcceptanceAdmin(admin.ModelAdmin):
    list_display = ("user", "ip_address", "accepted_at")
    search_fields = ("user__username",)


@admin.register(ConditionsLogEntry)
class ConditionsLogEntryAdmin(admin.ModelAdmin):
    list_display = ("user", "date", "venue", "discipline", "result", "created_at")
    list_filter = ("result", "discipline")
    search_fields = ("user__username", "venue")
