"""
URL configuration for skiwax project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from pathlib import Path

from django.contrib import admin
from django.urls import include, path, re_path
from django.views.static import serve

BASE_DIR = Path(__file__).resolve().parent.parent

admin.site.site_header = "glideCast administration"
admin.site.site_title = "glideCast admin"
admin.site.index_title = "Site administration"

urlpatterns = [
    re_path(
        r"^images/(?P<path>.*)$",
        serve,
        {"document_root": BASE_DIR / "public" / "images"},
    ),
    path("admin/", admin.site.urls),
    path("accounts/", include("accounts.urls")),
    path("accounts/", include("django.contrib.auth.urls")),
    path("billing/", include("billing.urls")),
    path("", include("calculator.urls")),
]
