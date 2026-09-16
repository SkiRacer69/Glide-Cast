from django.urls import path

from . import views

urlpatterns = [
    path("", views.nordic_calculator, name="nordic_calculator"),
]
