from django.urls import path

from . import views

urlpatterns = [
    path("", views.calculator, name="calculator"),
    path("export-pdf/", views.export_race_report_pdf, name="export_race_report_pdf"),
]

