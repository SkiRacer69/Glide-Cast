from django.urls import path

from . import views

urlpatterns = [
    path("", views.calculator, name="calculator"),
    path("map/", views.venue_map, name="venue_map"),
    path("api/globe-wax/", views.globe_wax_data, name="globe_wax_data"),
    path("export-pdf/", views.export_race_report_pdf, name="export_race_report_pdf"),
]

