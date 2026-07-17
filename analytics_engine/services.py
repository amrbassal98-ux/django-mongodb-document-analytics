"""LLM-driven document analysis pipeline using Groq."""

import json
import logging
import os

from groq import Groq

from .models import AnalysisMetadata, Document
from .utils import encode_for_vision, is_vision_file

logger = logging.getLogger(__name__)

MAX_TEXT_LENGTH = 30_000
TRUNCATION_WARNING = "\n\n[Document was truncated due to length.]"

VISION_TEXT_PROMPT = (
    "Analyze this document image and return a JSON object with "
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
    "}"
)


class DocumentProcessingService:  # pylint: disable=too-few-public-methods
    """
    Encapsulates the LLM-driven document analysis pipeline.

    Dispatches to either a **text** pipeline (plain-text files sent
    directly to a text model) or a **vision** pipeline (image / PDF
    files converted to base64 and sent to a multimodal model).
    """

    DEFAULT_MODEL = "llama-3.1-8b-instant"
    DEFAULT_VISION_MODEL = "meta-llama/llama-4-scout-17b-16e-instruct"

    def __init__(self, model: str | None = None):
        self.client = Groq(api_key=os.getenv("GROQ_API_KEY"))
        self.model = model or self.DEFAULT_MODEL

    # ── public API ───────────────────────────────────────────────────────

    def analyze(self, document: Document) -> dict:
        """Run the full analysis pipeline on *document*.

        Dispatches to the vision or text pipeline based on file type.
        Returns the parsed analysis_metadata and polymorphic_payload dict.
        """
        if is_vision_file(document.title):
            return self._analyze_vision(document)
        return self._analyze_text(document)

    # ── text pipeline ────────────────────────────────────────────────────

    @staticmethod
    def _truncate(text: str) -> str:
        if len(text) <= MAX_TEXT_LENGTH:
            return text
        logger.warning(
            "Truncating document text from %d to %d characters",
            len(text),
            MAX_TEXT_LENGTH,
        )
        return text[:MAX_TEXT_LENGTH] + TRUNCATION_WARNING

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

    def _analyze_text(self, document: Document) -> dict:
        text = self._truncate(document.raw_text)
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "user", "content": self._build_prompt(text)}
                ],
                response_format={"type": "json_object"},
                temperature=0.1,
            )
        except Exception as exc:  # pylint: disable=broad-exception-caught
            logger.exception(
                "Groq API call failed for document %s", document.pk
            )
            return {"error": f"Groq API call failed: {exc}"}

        return self._parse_and_persist(document, response)

    # ── vision pipeline ──────────────────────────────────────────────────

    def _analyze_vision(self, document: Document) -> dict:
        if not document.raw_file:
            return {"error": "No raw file data available for vision analysis"}

        try:
            b64 = encode_for_vision(document.title, document.raw_file)
        except (ValueError, ImportError) as exc:
            logger.exception(
                "Failed to encode document %s for vision", document.pk
            )
            return {"error": f"Failed to encode file for vision: {exc}"}

        try:
            response = self.client.chat.completions.create(
                model=self.DEFAULT_VISION_MODEL,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": VISION_TEXT_PROMPT},
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/jpeg;base64,{b64}"
                                },
                            },
                        ],
                    }
                ],
                response_format={"type": "json_object"},
                temperature=0.1,
            )
        except Exception as exc:  # pylint: disable=broad-exception-caught
            logger.exception(
                "Groq vision API call failed for document %s", document.pk
            )
            return {"error": f"Groq vision API call failed: {exc}"}

        return self._parse_and_persist(document, response)

    # ── shared persistence ───────────────────────────────────────────────

    @staticmethod
    def _parse_and_persist(document: Document, response) -> dict:
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
        except Exception as exc:  # pylint: disable=broad-exception-caught
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
