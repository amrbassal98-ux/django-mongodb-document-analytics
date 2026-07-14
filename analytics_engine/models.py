from django.db import models
from django_mongodb_backend.fields import (
    EmbeddedModelField,
    EmbeddedModelArrayField,
)
from django_mongodb_backend.models import EmbeddedModel


class AnalysisMetadata(EmbeddedModel):
    summary = models.TextField()
    classification = models.CharField(max_length=255)
    confidence_score = models.FloatField()

    class Meta:
        pass


class Annotation(EmbeddedModel):
    user_id = models.CharField(max_length=255)
    comment = models.TextField()
    highlighted_text = models.TextField()

    class Meta:
        pass


class Document(models.Model):
    title = models.CharField(max_length=500)
    file_type = models.CharField(max_length=100)
    raw_text = models.TextField()
    uploaded_at = models.DateTimeField(auto_now_add=True)

    analysis_metadata = EmbeddedModelField(
        embedded_model=AnalysisMetadata,
        null=True,
        blank=True,
    )

    polymorphic_payload = models.JSONField(
        default=dict,
        blank=True,
    )

    annotations = EmbeddedModelArrayField(
        embedded_model=Annotation,
        default=list,
        blank=True,
    )

    class Meta:
        db_table = "documents"

    def __str__(self):
        return self.title
