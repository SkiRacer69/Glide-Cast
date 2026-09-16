from django.conf import settings
from django.db import models


class Profile(models.Model):
    class SubscriptionStatus(models.TextChoices):
        NONE = "none", "None"
        TRIALING = "trialing", "Trialing"
        ACTIVE = "active", "Active"
        PAST_DUE = "past_due", "Past due"
        CANCELED = "canceled", "Canceled"
        UNPAID = "unpaid", "Unpaid"

    class PlanTier(models.TextChoices):
        BASIC = "basic", "Basic"
        PRO = "pro", "Pro"
        ALL = "all", "All Access"

    class BillingInterval(models.TextChoices):
        MONTHLY = "monthly", "Monthly"
        ANNUAL = "annual", "Annual"

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    stripe_customer_id = models.CharField(max_length=255, blank=True, default="")
    stripe_subscription_id = models.CharField(max_length=255, blank=True, default="")
    stripe_price_id = models.CharField(max_length=255, blank=True, default="")  # which price (plan + interval)
    subscription_status = models.CharField(
        max_length=32, choices=SubscriptionStatus.choices, default=SubscriptionStatus.NONE
    )
    plan_tier = models.CharField(
        max_length=32, choices=PlanTier.choices, default=PlanTier.BASIC
    )
    billing_interval = models.CharField(
        max_length=16, choices=BillingInterval.choices, default=BillingInterval.MONTHLY
    )
    current_period_end = models.DateTimeField(null=True, blank=True)
    pdf_period_start = models.DateTimeField(null=True, blank=True)  # start of current billing period for PDF count
    sport_access = models.CharField(max_length=16, default="alpine")  # "alpine" | "nordic" | "all"
    admin_override_active = models.BooleanField(default=False)
    admin_override_plan = models.CharField(max_length=32, blank=True, default="")  # if set, use this plan
    suspended_at = models.DateTimeField(null=True, blank=True)
    terminated_at = models.DateTimeField(null=True, blank=True)
    terminated_reason = models.TextField(blank=True, default="")
    flagged_for_review_at = models.DateTimeField(null=True, blank=True)  # e.g. >3 IPs in 24h

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def has_active_subscription(self) -> bool:
        if self.terminated_at:
            return False
        if self.suspended_at:
            return False
        if self.admin_override_active:
            return True
        return self.subscription_status in {
            self.SubscriptionStatus.TRIALING,
            self.SubscriptionStatus.ACTIVE,
        }

    def effective_plan_tier(self) -> str:
        t = (self.admin_override_plan or self.plan_tier or "").strip()
        legacy = {
            "club_junior": self.PlanTier.BASIC,
            "individual_masters": self.PlanTier.PRO,
            "coach_team": self.PlanTier.PRO,
            "race_department": self.PlanTier.PRO,
        }
        if t in legacy:
            return legacy[t]
        if t in (self.PlanTier.BASIC, self.PlanTier.PRO, self.PlanTier.ALL):
            return t
        return self.PlanTier.BASIC

    def has_access_to_sport(self, sport: str) -> bool:
        """Return True if this profile's subscription covers the requested sport."""
        if not self.has_active_subscription():
            return False
        tier = self.effective_plan_tier()
        if tier == self.PlanTier.ALL:
            return True
        access = self.admin_override_plan and "all" in self.admin_override_plan or self.sport_access
        return access == sport or access == "all"

    def __str__(self) -> str:
        return f"Profile({self.user.username})"


class UserSession(models.Model):
    """Single active session per user: one row per user with is_current=True."""
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    session_key = models.CharField(max_length=40, db_index=True)
    device_info = models.CharField(max_length=255, blank=True, default="")
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    is_current = models.BooleanField(default=True)

    class Meta:
        indexes = [models.Index(fields=["user", "is_current"])]

    def __str__(self) -> str:
        return f"Session({self.user_id}, {self.session_key[:8]}...)"


class LoginIPHistory(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    ip_address = models.GenericIPAddressField()
    location = models.CharField(max_length=255, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    flagged = models.BooleanField(default=False)  # admin review

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["user", "created_at"])]

    def __str__(self) -> str:
        return f"Login({self.user_id}, {self.ip_address}, {self.created_at})"


class TermsAcceptance(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    accepted_at = models.DateTimeField(auto_now_add=True)
    user_agent = models.CharField(max_length=512, blank=True, default="")

    def __str__(self) -> str:
        return f"ToS({self.user_id}, {self.accepted_at})"


class ConditionsLogEntry(models.Model):
    """Personal race log: date, venue, discipline, wax used, result, notes. Retained 90 days after cancel."""
    class ResultChoice(models.TextChoices):
        FASTER = "faster", "Faster than expected"
        CORRECT = "correct", "Correct"
        SLOWER = "slower", "Slower than expected"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    date = models.DateField()
    venue = models.CharField(max_length=128)
    discipline = models.CharField(max_length=32)
    run1_wax = models.CharField(max_length=128, blank=True, default="")
    run2_wax = models.CharField(max_length=128, blank=True, default="")
    result = models.CharField(max_length=32, choices=ResultChoice.choices, blank=True, default="")
    snow_notes = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-date", "-created_at"]
        indexes = [models.Index(fields=["user"])]

    def __str__(self) -> str:
        return f"Log({self.user_id}, {self.date}, {self.venue})"


class ScreenshotCaptureSignal(models.Model):
    """Best-effort log when the browser reports a screenshot-related key combo (not 100% reliable)."""

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    page_path = models.CharField(max_length=512, blank=True, default="")
    signal_type = models.CharField(max_length=64, blank=True, default="")
    detail = models.CharField(max_length=256, blank=True, default="")
    user_agent = models.CharField(max_length=512, blank=True, default="")
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["user", "created_at"])]

    def __str__(self) -> str:
        return f"ScreenshotSignal({self.user_id}, {self.detail}, {self.created_at})"
