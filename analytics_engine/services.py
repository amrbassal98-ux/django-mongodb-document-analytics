import json
import logging
import os

from groq import Groq

from .models import AnalysisMetadata, Document

logger = logging.getLogger(__name__)


class DocumentProcessingService:
    """
    Encapsulates the LLM-driven document analysis pipeline.

    Uses Groq's native JSON mode to produce structured output, then maps
    the result onto the Document model's ``analysis_metadata`` (embedded)
    and ``polymorphic_payload`` (JSON) fields.
    """

    DEFAULT_MODEL = "llama-3.1-8b-instant"

    def __init__(self, model: str | None = None):
        self.client = Groq(api_key=os.getenv("GROQ_API_KEY"))
        self.model = model or self.DEFAULT_MODEL

    @staticmethod
    def _build_prompt(raw_text: str) -> str:
        return (
            "Analyze the following document and return a JSON object with "
            "this exact structure:\n"
            "{\n"
            '  "analysis_metadata": {\n'
            '    "summary": "String description of the document",\n'
            '    "classification": "String (e.g., Invoice, Contract, Log, Report, Letter)",\n'
            '    "confidence_score": 0.95\n'
            "  },\n"
            '  "polymorphic_payload": {\n'
            '    "key_1": "val_1",\n'
            '    "key_2": "val_2"\n'
            "  }\n"
            "}\n\n"
            f"Document content:\n{raw_text}"
        )

    def analyze(self, document: Document) -> dict:
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "user", "content": self._build_prompt(document.raw_text)}
                ],
                response_format={"type": "json_object"},
                temperature=0.1,
            )
        except Exception as exc:
            logger.exception(
                "Groq API call failed for document %s", document.pk
            )
            return {"error": f"Groq API call failed: {exc}"}

        raw = response.choices[0].message.content
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as exc:
            logger.exception(
                "Failed to parse Groq response as JSON for document %s",
                document.pk,
            )
            return {"error": f"Failed to parse JSON response: {exc}"}

        metadata = parsed.get("analysis_metadata", {})
        payload = parsed.get("polymorphic_payload", {})

        document.analysis_metadata = AnalysisMetadata(
            summary=metadata.get("summary", ""),
            classification=metadata.get("classification", ""),
            confidence_score=metadata.get("confidence_score", 0.0),
        )
        document.polymorphic_payload = payload

        try:
            document.save()
        except Exception as exc:
            logger.exception(
                "Failed to save document %s after LLM update", document.pk
            )
            return {"error": f"Database save failed: {exc}"}

        return {
            "analysis_metadata": {
                "summary": document.analysis_metadata.summary,
                "classification": document.analysis_metadata.classification,
                "confidence_score": document.analysis_metadata.confidence_score,
            },
            "polymorphic_payload": document.polymorphic_payload,
        }


def analyze_document(document: Document) -> dict:
    """Top-level helper that views.py imports and calls directly."""
    service = DocumentProcessingService()
    return service.analyze(document)
