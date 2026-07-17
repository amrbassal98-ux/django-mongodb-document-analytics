"""API and HTML views for document analysis."""

import json

from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt

from . import services
from .models import Annotation, Document
from .utils import extract_text


def _trigger_llm_pipeline(document):
    """Run the full LLM analysis pipeline and return structured results."""
    return services.analyze_document(document)


@method_decorator(csrf_exempt, name="dispatch")
class DocumentUploadView(View):
    """Handle file upload and create a new Document record."""

    def post(self, request):
        """Accept a file upload, persist a Document, and return its metadata."""
        uploaded = request.FILES.get("file")
        if not uploaded:
            return JsonResponse({"error": "No file provided"}, status=400)

        raw_bytes = uploaded.read()
        raw_text = extract_text(uploaded.name, raw_bytes)
        doc = Document.objects.create(
            title=uploaded.name,
            file_type=uploaded.name.split(".")[-1] if "." in uploaded.name else "",
            raw_text=raw_text,
            raw_file=raw_bytes,
        )
        return JsonResponse(
            {"id": str(doc.pk), "title": doc.title, "uploaded_at": doc.uploaded_at.isoformat()},
            status=201,
        )


class DocumentDetailView(View):
    """Return document metadata, analysis, and annotations as JSON."""

    def get(self, request, doc_id):
        """Return the document's full metadata as JSON."""
        doc = get_object_or_404(Document, pk=doc_id)
        meta = doc.analysis_metadata
        return JsonResponse(
            {
                "id": str(doc.pk),
                "title": doc.title,
                "file_type": doc.file_type,
                "raw_text": doc.raw_text,
                "uploaded_at": doc.uploaded_at.isoformat(),
                "analysis_metadata": {
                    "summary": meta.summary,
                    "classification": meta.classification,
                    "confidence_score": meta.confidence_score,
                }
                if meta
                else None,
                "polymorphic_payload": doc.polymorphic_payload,
                "annotations": list(doc.annotations),
            }
        )


@method_decorator(csrf_exempt, name="dispatch")
class DocumentProcessView(View):
    """Trigger LLM analysis for a document."""

    def post(self, request, doc_id):
        """Trigger the LLM analysis pipeline for the given document."""
        doc = get_object_or_404(Document, pk=doc_id)
        result = _trigger_llm_pipeline(doc)
        return JsonResponse(
            {"id": str(doc.pk), "status": "processing_triggered", "result": result},
            status=202,
        )


@method_decorator(csrf_exempt, name="dispatch")
class DocumentAnnotateView(View):
    """Add an annotation to an existing document."""

    def post(self, request, doc_id):
        """Parse and persist an annotation for the given document."""
        doc = get_object_or_404(Document, pk=doc_id)
        try:
            body = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({"error": "Invalid JSON"}, status=400)

        annotation = Annotation(
            user_id=body.get("user_id", ""),
            comment=body.get("comment", ""),
            highlighted_text=body.get("highlighted_text", ""),
        )
        doc.annotations.append(annotation)
        doc.save(update_fields=["annotations"])
        return JsonResponse(
            {
                "user_id": annotation.user_id,
                "comment": annotation.comment,
                "highlighted_text": annotation.highlighted_text,
            },
            status=201,
        )


class DashboardView(View):
    """Render the HTML dashboard listing all documents."""

    def get(self, request):
        """Return HTML with all documents ordered by newest first."""
        docs = Document.objects.all().order_by("-uploaded_at")
        return render(request, "analytics/dashboard.html", {"documents": docs})


class DocumentDetailHTMLView(View):
    """Render the HTML document detail page."""

    def get(self, request, doc_id):
        """Return the HTML detail view for a single document."""
        doc = get_object_or_404(Document, pk=doc_id)
        return render(request, "analytics/document_detail.html", {"document": doc})
