from django.urls import path

from . import views

urlpatterns = [
    path("", views.DashboardView.as_view(), name="dashboard"),
    path("documents/<str:id>/", views.DocumentDetailHTMLView.as_view(), name="document-html-detail"),
]
