"""
Single-session enforcement: only one active session per user.
Validate session on every request; if current session is not the active one, logout and show message.
"""
from django.contrib.auth import logout
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.deprecation import MiddlewareMixin

from .models import UserSession


class SingleSessionMiddleware(MiddlewareMixin):
    """
    Run after AuthenticationMiddleware. If user is authenticated, check that
    this request's session_key is the one stored as is_current for that user.
    If not, logout and redirect with message.
    """
    def process_request(self, request):
        if not getattr(request, "user", None) or not request.user.is_authenticated:
            return None
        session_key = request.session.session_key
        if not session_key:
            return None
        try:
            current = UserSession.objects.get(user=request.user, is_current=True)
        except UserSession.DoesNotExist:
            # First time after migration or stale — allow and let login view set it
            return None
        if current.session_key != session_key:
            logout(request)
            request.session.flush()
            # Store message for next page
            from django.contrib import messages
            messages.warning(
                request,
                "Your session was ended because your account was accessed from another device."
            )
            return redirect(reverse("login") + "?session_ended=1")
        return None
