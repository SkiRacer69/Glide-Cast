from django.conf import settings
from django.db import models


class PDFDownload(models.Model):
    """Tracks PDF downloads per user for rate limiting. Counted per billing period."""
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["user", "created_at"])]

    def __str__(self) -> str:
        return f"PDFDownload(user={self.user_id}, {self.created_at})"
