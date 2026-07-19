from django.urls import path

from . import views


urlpatterns = [
    path("paywall/", views.paywall, name="paywall"),
    path("checkout/", views.create_checkout_session, name="create_checkout_session"),
    path("portal/", views.customer_portal, name="customer_portal"),
    path("webhook/", views.stripe_webhook, name="stripe_webhook"),
    path("dev-bypass/", views.dev_bypass_subscription, name="dev_bypass_subscription"),
]

