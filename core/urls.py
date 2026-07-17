"""Root URL configuration — API, admin, and frontend routes."""

from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/v1/documents/", include("analytics_engine.urls")),
    path("", include("analytics_engine.frontend_urls")),
]
