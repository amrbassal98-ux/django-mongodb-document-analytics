import json

from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt

from .models import Annotation, Document
from .utils import extract_text


def _trigger_llm_pipeline(document):
    from . import services
    return services.analyze_document(document)


@method_decorator(csrf_exempt, name="dispatch")
class DocumentUploadView(View):
    def post(self, request):
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
    def get(self, request, id):
        doc = get_object_or_404(Document, pk=id)
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
    def post(self, request, id):
        doc = get_object_or_404(Document, pk=id)
        result = _trigger_llm_pipeline(doc)
        return JsonResponse(
            {"id": str(doc.pk), "status": "processing_triggered", "result": result},
            status=202,
        )


@method_decorator(csrf_exempt, name="dispatch")
class DocumentAnnotateView(View):
    def post(self, request, id):
        doc = get_object_or_404(Document, pk=id)
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
    def get(self, request):
        docs = Document.objects.all().order_by("-uploaded_at")
        return render(request, "analytics/dashboard.html", {"documents": docs})


class DocumentDetailHTMLView(View):
    def get(self, request, id):
        doc = get_object_or_404(Document, pk=id)
        return render(request, "analytics/document_detail.html", {"document": doc})
