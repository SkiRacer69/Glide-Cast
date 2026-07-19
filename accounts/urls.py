from django.urls import path

from . import auth_views
from . import views

urlpatterns = [
    path("terms/", views.terms_of_service, name="terms_of_service"),
    path("login/", auth_views.login_view, name="login"),
    path("signup/", auth_views.signup_with_tos, name="signup"),
    path("account/", views.account, name="account"),
    path("conditions/", views.conditions_log_list, name="conditions_log_list"),
    path("conditions/add/", views.conditions_log_add, name="conditions_log_add"),
    path("conditions/<int:pk>/edit/", views.conditions_log_edit, name="conditions_log_edit"),
    path("conditions/<int:pk>/delete/", views.conditions_log_delete, name="conditions_log_delete"),
    path("security/screenshot-signal/", views.report_screenshot_attempt, name="report_screenshot_attempt"),
]

