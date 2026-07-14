from django.urls import path

from . import views

urlpatterns = [
    path("upload/", views.DocumentUploadView.as_view(), name="document-upload"),
    path("<str:id>/process/", views.DocumentProcessView.as_view(), name="document-process"),
    path("<str:id>/annotate/", views.DocumentAnnotateView.as_view(), name="document-annotate"),
    path("<str:id>/", views.DocumentDetailView.as_view(), name="document-detail"),
]
