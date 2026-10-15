from django.urls import path

from . import views

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("run/", views.run_all, name="run_all"),
    path("results.csv", views.download_csv, name="download_csv"),
    path("natural/", views.natural, name="natural"),
    path("search/", views.search, name="search"),
    path("barcode/", views.barcode, name="barcode"),
    path("voice/", views.voice, name="voice"),
]
