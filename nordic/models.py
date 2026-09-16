from django.conf import settings
from django.db import models


class NordicCalculationHistory(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    venue = models.CharField(max_length=128)
    discipline = models.CharField(max_length=32)
    inputs = models.JSONField()
    results = models.JSONField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"NordicHistory({self.user_id}, {self.venue}, {self.created_at.date()})"
