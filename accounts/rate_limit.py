"""Rate limit: max N requests per hour per authenticated user."""
from __future__ import annotations

from django.conf import settings
from django.core.cache import cache
from django.http import HttpResponse


def check_rate_limit(request) -> HttpResponse | None:
    """
    If the authenticated user has exceeded the hourly limit, return a 429 response.
    Otherwise increment count and return None (caller should proceed).
    """
    if not getattr(request, "user", None) or not request.user.is_authenticated:
        return None
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    max_per_hour = getattr(settings, "API_RATE_LIMIT_PER_HOUR", 60)
    key = f"rate_limit:{request.user.id}:{now.strftime('%Y-%m-%d-%H')}"
    count = cache.get(key, 0)
    if count >= max_per_hour:
        return HttpResponse(
            "Rate limit exceeded. Maximum 60 requests per hour. Try again later.",
            status=429,
            content_type="text/plain",
        )
    cache.set(key, count + 1, timeout=3660)
    return None
