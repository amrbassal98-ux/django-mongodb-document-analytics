"""Frontend (HTML) URL patterns for dashboard and detail views."""

from django.urls import path

from . import views

urlpatterns = [
    path("", views.DashboardView.as_view(), name="dashboard"),
    path("documents/<str:doc_id>/", views.DocumentDetailHTMLView.as_view(), name="document-html-detail"),
]
