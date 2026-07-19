from django.conf import settings
from django.db import models


class CalculationHistory(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    inputs = models.JSONField()
    results = models.JSONField()
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return f"CalculationHistory(user={self.user_id}, created_at={self.created_at.isoformat()})"


class CalculationAuditLog(models.Model):
    """Audit trail: timestamp, user, plan tier. No raw inputs/formulas."""
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    plan_tier = models.CharField(max_length=32)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["user", "created_at"])]
