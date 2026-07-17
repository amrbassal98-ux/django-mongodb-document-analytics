"""Tests for analytics_engine models, utils, services, and views."""

import base64
import json
from io import BytesIO
from unittest.mock import MagicMock, patch

from PIL import Image

from django.test import TestCase
from django.urls import reverse

from .models import AnalysisMetadata, Annotation, Document
from .services import DocumentProcessingService, analyze_document
from .utils import encode_for_vision, is_vision_file


# ── Model Tests ──────────────────────────────────────────────────────────────

class DocumentModelTests(TestCase):
    """Tests for Document model creation and field persistence."""

    def test_create_document_minimal(self):
        """A document can be created with only the required fields."""
        doc = Document.objects.create(
            title="test.txt", file_type="txt", raw_text="hello"
        )
        self.assertIsNotNone(doc.pk)
        self.assertEqual(doc.title, "test.txt")
        self.assertEqual(doc.file_type, "txt")
        self.assertEqual(doc.raw_text, "hello")
        self.assertIsNotNone(doc.uploaded_at)
        self.assertIsNone(doc.analysis_metadata)
        self.assertEqual(doc.polymorphic_payload, {})
        self.assertEqual(list(doc.annotations), [])

    def test_create_document_with_analysis_metadata(self):
        """Embedded analysis metadata is persisted and retrievable."""
        doc = Document.objects.create(
            title="report.pdf",
            file_type="pdf",
            raw_text="some content",
            analysis_metadata=AnalysisMetadata(
                summary="A test report",
                classification="Report",
                confidence_score=0.85,
            ),
            polymorphic_payload={"key": "value"},
        )
        self.assertEqual(doc.analysis_metadata.summary, "A test report")
        self.assertEqual(doc.analysis_metadata.classification, "Report")
        self.assertEqual(doc.analysis_metadata.confidence_score, 0.85)
        self.assertEqual(doc.polymorphic_payload, {"key": "value"})

    def test_document_str_method(self):
        """The string representation returns the document title."""
        doc = Document.objects.create(
            title="my_doc.pdf", file_type="pdf", raw_text="data"
        )
        self.assertEqual(str(doc), "my_doc.pdf")

    def test_document_with_annotations(self):
        """Annotations can be added and persisted to a document."""
        doc = Document.objects.create(
            title="notes.txt", file_type="txt", raw_text="important stuff"
        )
        doc.annotations.append(
            Annotation(
                user_id="user1", comment="Nice doc", highlighted_text="important"
            )
        )
        doc.annotations.append(
            Annotation(
                user_id="user2", comment="Agreed", highlighted_text="stuff"
            )
        )
        doc.save()

        doc.refresh_from_db()
        self.assertEqual(len(doc.annotations), 2)
        self.assertEqual(doc.annotations[0].user_id, "user1")
        self.assertEqual(doc.annotations[1].comment, "Agreed")

    def test_analysis_metadata_embedded_defaults(self):
        """Embedded polymorphic payload is persisted and retrievable."""
        doc = Document.objects.create(
            title="defaults.pdf",
            file_type="pdf",
            raw_text="test",
            polymorphic_payload={"a": 1},
        )
        doc.refresh_from_db()
        self.assertEqual(doc.polymorphic_payload, {"a": 1})

    def test_document_stores_raw_file(self):
        """A document with raw_file stores and returns binary data correctly."""
        doc = Document.objects.create(
            title="data.bin",
            file_type="bin",
            raw_text="",
            raw_file=b"\x00\x01\x02\xff\xfe",
        )
        doc.refresh_from_db()
        self.assertEqual(doc.raw_file, b"\x00\x01\x02\xff\xfe")


# ── Utility Tests ────────────────────────────────────────────────────────────

class UtilityTests(TestCase):
    """Tests for file-type detection and encoding utilities."""

    def test_is_vision_file_pdf(self):
        """is_vision_file returns True for .pdf files."""
        self.assertTrue(is_vision_file("doc.pdf"))

    def test_is_vision_file_image(self):
        """is_vision_file returns True for common image file extensions."""
        self.assertTrue(is_vision_file("photo.png"))
        self.assertTrue(is_vision_file("photo.jpg"))
        self.assertTrue(is_vision_file("photo.jpeg"))

    def test_is_vision_file_text(self):
        """is_vision_file returns False for non-vision file types."""
        self.assertFalse(is_vision_file("notes.txt"))
        self.assertFalse(is_vision_file("data.csv"))
        self.assertFalse(is_vision_file("README"))

    def test_encode_for_vision_image_bytes(self):
        """encode_for_vision returns a valid base64 string for image bytes."""
        img = Image.new("RGB", (2, 2), color="red")
        buf = BytesIO()
        img.save(buf, format="PNG")
        png_bytes = buf.getvalue()
        b64 = encode_for_vision("test.png", png_bytes)
        self.assertIsInstance(b64, str)
        self.assertGreater(len(b64), 0)
        base64.b64decode(b64)

    def test_encode_for_vision_pdf(self):
        """encode_for_vision returns a valid base64 string for PDF bytes."""
        pdf_bytes = (
            b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
            b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
            b"3 0 obj<</Type/Page/MediaBox[0 0 100 100]/Parent 2 0 R"
            b"/Contents 4 0 R>>endobj\n"
            b"4 0 obj<</Length 22>>stream\nBT /F1 12 Tf 10 50 Td"
            b"(A)Tj ET\nendstream\nendobj\nxref\n0 5\n"
            b"0000000000 65535 f \n0000000009 00000 n \n0000000058 00000 n \n"
            b"0000000115 00000 n \n0000000196 00000 n \n"
            b"trailer<</Size 5/Root 1 0 R>>\nstartxref\n303\n%%EOF"
        )
        b64 = encode_for_vision("doc.pdf", pdf_bytes)
        self.assertIsInstance(b64, str)
        self.assertGreater(len(b64), 100)
        base64.b64decode(b64)

    def test_encode_for_vision_invalid_image(self):
        """encode_for_vision raises ValueError for invalid image data."""
        with self.assertRaises(ValueError):
            encode_for_vision("bad.png", b"not an image")


# ── Service-Layer Tests ──────────────────────────────────────────────────────

class DocumentProcessingServiceTests(TestCase):
    """Tests for DocumentProcessingService happy-path and error handling."""

    def _build_mock_groq_response(self, content: str):
        choice = MagicMock()
        choice.message.content = content
        response = MagicMock()
        response.choices = [choice]
        return response

    # -- Happy path -----------------------------------------------------------

    @patch("analytics_engine.services.Groq")
    def test_analyze_success(self, mock_groq_cls):
        """A successful analysis stores metadata and polymorphic payload."""
        raw_payload = {
            "analysis_metadata": {
                "summary": "An invoice document",
                "classification": "Invoice",
                "confidence_score": 0.98,
            },
            "polymorphic_payload": {
                "total": 100.0,
                "vendor": "Acme",
            },
        }
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = (
            self._build_mock_groq_response(json.dumps(raw_payload))
        )
        mock_groq_cls.return_value = mock_client

        doc = Document.objects.create(
            title="inv.txt", file_type="txt", raw_text="INVOICE $100"
        )
        result = DocumentProcessingService().analyze(doc)

        self.assertEqual(
            result["analysis_metadata"]["summary"], "An invoice document"
        )
        self.assertEqual(result["analysis_metadata"]["classification"], "Invoice")
        self.assertEqual(result["analysis_metadata"]["confidence_score"], 0.98)
        self.assertEqual(result["polymorphic_payload"]["total"], 100.0)

        doc.refresh_from_db()
        self.assertEqual(doc.analysis_metadata.summary, "An invoice document")
        self.assertEqual(doc.polymorphic_payload["vendor"], "Acme")

    @patch("analytics_engine.services.Groq")
    def test_analyze_success_top_level_function(self, mock_groq_cls):
        """The top-level analyze_document function produces valid results."""
        raw_payload = {
            "analysis_metadata": {
                "summary": "Simple memo",
                "classification": "Memo",
                "confidence_score": 0.90,
            },
            "polymorphic_payload": {"note": "hello"},
        }
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = (
            self._build_mock_groq_response(json.dumps(raw_payload))
        )
        mock_groq_cls.return_value = mock_client

        doc = Document.objects.create(
            title="memo.txt", file_type="txt", raw_text="hello world"
        )
        result = analyze_document(doc)
        self.assertEqual(result["analysis_metadata"]["classification"], "Memo")

    # -- Error handling: API failure ------------------------------------------

    @patch("analytics_engine.services.Groq")
    def test_analyze_api_failure(self, mock_groq_cls):
        """An API failure returns an error dict with a descriptive message."""
        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = Exception("Network error")
        mock_groq_cls.return_value = mock_client

        doc = Document.objects.create(
            title="fail.txt", file_type="txt", raw_text="oops"
        )
        result = DocumentProcessingService().analyze(doc)
        self.assertIn("error", result)
        self.assertIn("Groq API call failed", result["error"])
        self.assertIn("Network error", result["error"])

    # -- Error handling: malformed JSON ---------------------------------------

    @patch("analytics_engine.services.Groq")
    def test_analyze_json_decode_failure(self, mock_groq_cls):
        """Invalid JSON from the API returns a parse error."""
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = (
            self._build_mock_groq_response("not valid json")
        )
        mock_groq_cls.return_value = mock_client

        doc = Document.objects.create(
            title="bad.txt", file_type="txt", raw_text="garbage in"
        )
        result = DocumentProcessingService().analyze(doc)
        self.assertIn("error", result)
        self.assertIn("Failed to parse JSON", result["error"])

    # -- Edge case: missing fields in response --------------------------------

    @patch("analytics_engine.services.Groq")
    def test_analyze_missing_analysis_metadata_fields(self, mock_groq_cls):
        """Missing optional fields default to empty/zero values."""
        raw_payload = {
            "analysis_metadata": {
                "classification": "Log",
            },
            "polymorphic_payload": {"event": "startup"},
        }
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = (
            self._build_mock_groq_response(json.dumps(raw_payload))
        )
        mock_groq_cls.return_value = mock_client

        doc = Document.objects.create(
            title="log.txt", file_type="txt", raw_text="boot sequence"
        )
        result = DocumentProcessingService().analyze(doc)
        self.assertEqual(result["analysis_metadata"]["summary"], "")
        self.assertEqual(result["analysis_metadata"]["classification"], "Log")
        self.assertEqual(result["analysis_metadata"]["confidence_score"], 0.0)
        self.assertEqual(result["polymorphic_payload"]["event"], "startup")

    @patch("analytics_engine.services.Groq")
    def test_analyze_missing_polymorphic_payload(self, mock_groq_cls):
        """A missing polymorphic payload defaults to an empty dict."""
        raw_payload = {
            "analysis_metadata": {
                "summary": "No polymorphic payload",
                "classification": "Other",
                "confidence_score": 0.5,
            },
        }
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = (
            self._build_mock_groq_response(json.dumps(raw_payload))
        )
        mock_groq_cls.return_value = mock_client

        doc = Document.objects.create(
            title="partial.txt", file_type="txt", raw_text="partial"
        )
        result = DocumentProcessingService().analyze(doc)

        doc.refresh_from_db()
        self.assertEqual(doc.polymorphic_payload, {})
        self.assertEqual(result["polymorphic_payload"], {})

    # -- Error handling: DB save failure --------------------------------------

    @patch("analytics_engine.services.Groq")
    def test_analyze_db_save_failure(self, mock_groq_cls):
        """A database save error returns a descriptive error message."""
        raw_payload = {
            "analysis_metadata": {
                "summary": "Will not save",
                "classification": "Error",
                "confidence_score": 0.0,
            },
            "polymorphic_payload": {},
        }
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = (
            self._build_mock_groq_response(json.dumps(raw_payload))
        )
        mock_groq_cls.return_value = mock_client

        doc = Document.objects.create(
            title="dbfail.txt", file_type="txt", raw_text="data"
        )

        with patch.object(Document, "save", side_effect=Exception("DB connection lost")):
            result = DocumentProcessingService().analyze(doc)
        self.assertIn("error", result)
        self.assertIn("Database save failed", result["error"])

    # -- Custom model override ------------------------------------------------

    @patch("analytics_engine.services.Groq")
    def test_custom_model_override(self, mock_groq_cls):
        """The service uses the explicitly provided model name."""
        raw_payload = {
            "analysis_metadata": {
                "summary": "Custom model",
                "classification": "Test",
                "confidence_score": 1.0,
            },
            "polymorphic_payload": {},
        }
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = (
            self._build_mock_groq_response(json.dumps(raw_payload))
        )
        mock_groq_cls.return_value = mock_client

        doc = Document.objects.create(
            title="custom.txt", file_type="txt", raw_text="custom model test"
        )
        DocumentProcessingService(model="mixtral-8x7b-32768").analyze(doc)

        call_kwargs = mock_client.chat.completions.create.call_args[1]
        self.assertEqual(call_kwargs["model"], "mixtral-8x7b-32768")

    @patch("analytics_engine.services.Groq")
    def test_default_model(self, mock_groq_cls):
        """The service defaults to llama-3.1-8b-instant when no model is specified."""
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = (
            self._build_mock_groq_response(
                json.dumps({
                    "analysis_metadata": {
                        "summary": "x",
                        "classification": "x",
                        "confidence_score": 0.5,
                    },
                    "polymorphic_payload": {},
                })
            )
        )
        mock_groq_cls.return_value = mock_client

        doc = Document.objects.create(
            title="default_model.txt", file_type="txt", raw_text="test"
        )
        DocumentProcessingService().analyze(doc)

        call_kwargs = mock_client.chat.completions.create.call_args[1]
        self.assertEqual(call_kwargs["model"], "llama-3.1-8b-instant")

    @patch("analytics_engine.services.Groq")
    def test_json_mode_enforced(self, mock_groq_cls):
        """The API call enforces json_object response format."""
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = (
            self._build_mock_groq_response(
                json.dumps({
                    "analysis_metadata": {
                        "summary": "x",
                        "classification": "x",
                        "confidence_score": 0.5,
                    },
                    "polymorphic_payload": {},
                })
            )
        )
        mock_groq_cls.return_value = mock_client

        doc = Document.objects.create(
            title="jsonmode.txt", file_type="txt", raw_text="test"
        )
        DocumentProcessingService().analyze(doc)

        call_kwargs = mock_client.chat.completions.create.call_args[1]
        self.assertEqual(call_kwargs["response_format"], {"type": "json_object"})

    @patch("analytics_engine.services.Groq")
    def test_prompt_contains_raw_text(self, mock_groq_cls):
        """The raw document text is included in the prompt sent to the API."""
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = (
            self._build_mock_groq_response(
                json.dumps({
                    "analysis_metadata": {
                        "summary": "x",
                        "classification": "x",
                        "confidence_score": 0.5,
                    },
                    "polymorphic_payload": {},
                })
            )
        )
        mock_groq_cls.return_value = mock_client

        raw = "unique document content >>> 123"
        doc = Document.objects.create(
            title="content.txt", file_type="txt", raw_text=raw
        )
        DocumentProcessingService().analyze(doc)

        sent_content = mock_client.chat.completions.create.call_args[1][
            "messages"
        ][0]["content"]
        self.assertIn(raw, sent_content)

    # ── vision pipeline ───────────────────────────────────────────────────

    @patch("analytics_engine.services.encode_for_vision")
    @patch("analytics_engine.services.Groq")
    def test_vision_pipeline_dispatches_for_pdf(
        self, mock_groq_cls, mock_encode
    ):
        """PDF files are processed through the vision pipeline."""
        mock_encode.return_value = "fakebase64=="
        raw_payload = {
            "analysis_metadata": {
                "summary": "Vision-analyzed PDF",
                "classification": "Contract",
                "confidence_score": 0.92,
            },
            "polymorphic_payload": {"clauses": 3},
        }
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = (
            self._build_mock_groq_response(json.dumps(raw_payload))
        )
        mock_groq_cls.return_value = mock_client

        doc = Document.objects.create(
            title="scan.pdf",
            file_type="pdf",
            raw_text="",
            raw_file=b"dummy pdf bytes",
        )
        result = DocumentProcessingService().analyze(doc)

        self.assertEqual(
            result["analysis_metadata"]["classification"], "Contract"
        )
        # Verify vision model was used
        call_kwargs = mock_client.chat.completions.create.call_args[1]
        self.assertEqual(
            call_kwargs["model"], "meta-llama/llama-4-scout-17b-16e-instruct"
        )
        # Verify image_url content type was sent
        messages = call_kwargs["messages"]
        self.assertEqual(len(messages), 1)
        content = messages[0]["content"]
        self.assertIsInstance(content, list)
        self.assertEqual(content[1]["type"], "image_url")
        mock_encode.assert_called_once_with("scan.pdf", b"dummy pdf bytes")

    @patch("analytics_engine.services.encode_for_vision")
    @patch("analytics_engine.services.Groq")
    def test_vision_pipeline_dispatches_for_image(
        self, mock_groq_cls, mock_encode
    ):
        """Image files are processed through the vision pipeline."""
        mock_encode.return_value = "fakebase64=="
        raw_payload = {
            "analysis_metadata": {
                "summary": "Photo analysis",
                "classification": "Receipt",
                "confidence_score": 0.88,
            },
            "polymorphic_payload": {"total": 45.0},
        }
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = (
            self._build_mock_groq_response(json.dumps(raw_payload))
        )
        mock_groq_cls.return_value = mock_client

        doc = Document.objects.create(
            title="receipt.png",
            file_type="png",
            raw_text="",
            raw_file=b"dummy image bytes",
        )
        result = DocumentProcessingService().analyze(doc)

        self.assertEqual(result["analysis_metadata"]["classification"], "Receipt")
        call_kwargs = mock_client.chat.completions.create.call_args[1]
        self.assertEqual(
            call_kwargs["model"], "meta-llama/llama-4-scout-17b-16e-instruct"
        )
        mock_encode.assert_called_once_with("receipt.png", b"dummy image bytes")

    @patch("analytics_engine.services.Groq")
    def test_text_pipeline_for_txt_file(self, mock_groq_cls):
        """Text files use the text pipeline instead of vision."""
        raw_payload = {
            "analysis_metadata": {
                "summary": "Text analysis",
                "classification": "Note",
                "confidence_score": 0.75,
            },
            "polymorphic_payload": {"words": 42},
        }
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = (
            self._build_mock_groq_response(json.dumps(raw_payload))
        )
        mock_groq_cls.return_value = mock_client

        doc = Document.objects.create(
            title="notes.txt",
            file_type="txt",
            raw_text="some text content",
            raw_file=b"some text content",
        )
        result = DocumentProcessingService().analyze(doc)

        self.assertEqual(result["analysis_metadata"]["classification"], "Note")
        call_kwargs = mock_client.chat.completions.create.call_args[1]
        self.assertEqual(call_kwargs["model"], "llama-3.1-8b-instant")
        # Should NOT use image_url content
        content = call_kwargs["messages"][0]["content"]
        self.assertIsInstance(content, str)

    @patch("analytics_engine.services.encode_for_vision")
    @patch("analytics_engine.services.Groq")
    def test_vision_fails_without_raw_file(self, _mock_groq_cls, mock_encode):
        """Vision processing fails gracefully when raw_file is missing."""
        doc = Document.objects.create(
            title="scan.pdf", file_type="pdf", raw_text="", raw_file=None
        )
        result = DocumentProcessingService().analyze(doc)
        self.assertIn("error", result)
        self.assertIn("No raw file data", result["error"])
        mock_encode.assert_not_called()

    @patch("analytics_engine.services.Groq")
    def test_truncates_oversized_text(self, mock_groq_cls):
        """Text exceeding the character limit is truncated with a notice."""
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = (
            self._build_mock_groq_response(
                json.dumps({
                    "analysis_metadata": {
                        "summary": "x",
                        "classification": "x",
                        "confidence_score": 0.5,
                    },
                    "polymorphic_payload": {},
                })
            )
        )
        mock_groq_cls.return_value = mock_client

        large_text = "a" * 50_000
        doc = Document.objects.create(
            title="large.txt", file_type="txt", raw_text=large_text
        )
        DocumentProcessingService().analyze(doc)

        sent_content = mock_client.chat.completions.create.call_args[1][
            "messages"
        ][0]["content"]
        self.assertIn("[Document was truncated due to length.]", sent_content)
        self.assertLess(len(sent_content), 35_000)

    @patch("analytics_engine.services.Groq")
    def test_does_not_truncate_small_text(self, mock_groq_cls):
        """Small text is passed through without truncation."""
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = (
            self._build_mock_groq_response(
                json.dumps({
                    "analysis_metadata": {
                        "summary": "x",
                        "classification": "x",
                        "confidence_score": 0.5,
                    },
                    "polymorphic_payload": {},
                })
            )
        )
        mock_groq_cls.return_value = mock_client

        small_text = "small document"
        doc = Document.objects.create(
            title="small.txt", file_type="txt", raw_text=small_text
        )
        DocumentProcessingService().analyze(doc)

        sent_content = mock_client.chat.completions.create.call_args[1][
            "messages"
        ][0]["content"]
        self.assertIn(small_text, sent_content)
        self.assertNotIn("truncated", sent_content)


# ── View Tests ───────────────────────────────────────────────────────────────

class DocumentUploadViewTests(TestCase):
    """Tests for the document upload API endpoint."""

    def test_upload_success(self):
        """Uploading a file creates a Document and returns its ID."""
        file_data = BytesIO(b"hello world, this is a test file")
        file_data.name = "greeting.txt"
        resp = self.client.post(
            reverse("document-upload"), {"file": file_data}, format="multipart"
        )
        self.assertEqual(resp.status_code, 201)
        body = resp.json()
        self.assertIn("id", body)
        self.assertEqual(body["title"], "greeting.txt")

        doc = Document.objects.get(pk=body["id"])
        self.assertEqual(doc.raw_text, "hello world, this is a test file")
        self.assertEqual(doc.file_type, "txt")
        self.assertEqual(doc.raw_file, b"hello world, this is a test file")

    def test_upload_missing_file(self):
        """Uploading without a file returns a 400 error."""
        resp = self.client.post(reverse("document-upload"), {}, format="multipart")
        self.assertEqual(resp.status_code, 400)
        self.assertIn("error", resp.json())

    def test_upload_no_extension(self):
        """A file without an extension is accepted with an empty file_type."""
        file_data = BytesIO(b"content")
        file_data.name = "README"
        resp = self.client.post(
            reverse("document-upload"), {"file": file_data}, format="multipart"
        )
        self.assertEqual(resp.status_code, 201)
        body = resp.json()
        self.assertIn("id", body)
        self.assertEqual(body["title"], "README")
        doc = Document.objects.get(pk=body["id"])
        self.assertEqual(doc.file_type, "")


class DocumentDetailViewTests(TestCase):
    """Tests for the document detail JSON API endpoint."""

    def test_detail_existing(self):
        """An existing document returns its full details as JSON."""
        doc = Document.objects.create(
            title="detail.txt",
            file_type="txt",
            raw_text="detail content",
            analysis_metadata=AnalysisMetadata(
                summary="test", classification="Log", confidence_score=0.5
            ),
            polymorphic_payload={"key": "val"},
        )
        resp = self.client.get(reverse("document-detail", args=[str(doc.pk)]))
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["title"], "detail.txt")
        self.assertEqual(body["analysis_metadata"]["summary"], "test")
        self.assertEqual(body["polymorphic_payload"]["key"], "val")
        self.assertEqual(body["annotations"], [])

    def test_detail_not_found(self):
        """A non-existent document ID returns a 404 error."""
        resp = self.client.get(
            reverse("document-detail", args=["000000000000000000000000"])
        )
        self.assertEqual(resp.status_code, 404)


class DocumentProcessViewTests(TestCase):
    """Tests for the document process/analysis API endpoint."""

    @patch("analytics_engine.views._trigger_llm_pipeline")
    def test_process_success(self, mock_pipeline):
        """Processing a document triggers the LLM pipeline and returns results."""
        mock_pipeline.return_value = {
            "analysis_metadata": {
                "summary": "Processed doc",
                "classification": "Report",
                "confidence_score": 0.95,
            },
            "polymorphic_payload": {"extracted": "data"},
        }

        doc = Document.objects.create(
            title="process.txt", file_type="txt", raw_text="process me"
        )
        resp = self.client.post(
            reverse("document-process", args=[str(doc.pk)])
        )
        self.assertEqual(resp.status_code, 202)
        body = resp.json()
        self.assertEqual(body["id"], str(doc.pk))
        self.assertEqual(body["status"], "processing_triggered")
        self.assertEqual(body["result"]["analysis_metadata"]["classification"], "Report")
        self.assertEqual(body["result"]["polymorphic_payload"]["extracted"], "data")
        mock_pipeline.assert_called_once_with(doc)

    def test_process_not_found(self):
        """Processing a non-existent document returns a 404 error."""
        resp = self.client.post(
            reverse("document-process", args=["000000000000000000000000"])
        )
        self.assertEqual(resp.status_code, 404)


class DocumentAnnotateViewTests(TestCase):
    """Tests for the annotation API endpoint."""

    def test_annotate_success(self):
        """Annotating a document creates and persists the annotation."""
        doc = Document.objects.create(
            title="annotate.txt", file_type="txt", raw_text="annotate me"
        )
        payload = {
            "user_id": "alice",
            "comment": "Needs review",
            "highlighted_text": "annotate me",
        }
        resp = self.client.post(
            reverse("document-annotate", args=[str(doc.pk)]),
            data=json.dumps(payload),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 201)
        body = resp.json()
        self.assertEqual(body["user_id"], "alice")
        self.assertEqual(body["comment"], "Needs review")

        doc.refresh_from_db()
        self.assertEqual(len(doc.annotations), 1)
        self.assertEqual(doc.annotations[0].user_id, "alice")

    def test_annotate_defaults_for_missing_fields(self):
        """Missing annotation fields default to empty strings."""
        doc = Document.objects.create(
            title="partial.txt", file_type="txt", raw_text="partial annotate"
        )
        resp = self.client.post(
            reverse("document-annotate", args=[str(doc.pk)]),
            data=json.dumps({}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 201)
        body = resp.json()
        self.assertEqual(body["user_id"], "")
        self.assertEqual(body["comment"], "")
        self.assertEqual(body["highlighted_text"], "")

    def test_annotate_invalid_json(self):
        """Invalid JSON in the request body returns a 400 error."""
        doc = Document.objects.create(
            title="badjson.txt", file_type="txt", raw_text="bad"
        )
        resp = self.client.post(
            reverse("document-annotate", args=[str(doc.pk)]),
            data=b"not json",
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 400)
        self.assertIn("error", resp.json())

    def test_annotate_not_found(self):
        """Annotating a non-existent document returns a 404 error."""
        resp = self.client.post(
            reverse("document-annotate", args=["000000000000000000000000"]),
            data=json.dumps({"user_id": "x", "comment": "y", "highlighted_text": "z"}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 404)


# ── Integration-Style View Test (mocked Groq through the full stack) ────────

class FullPipelineViewTest(TestCase):
    """End-to-end integration tests spanning upload, process, and annotate."""

    @patch("analytics_engine.services.Groq")
    def test_upload_then_process_then_detail(self, mock_groq_cls):
        """A full upload-process-detail cycle persists analysis data correctly."""
        raw_payload = {
            "analysis_metadata": {
                "summary": "Integration test invoice",
                "classification": "Invoice",
                "confidence_score": 0.99,
            },
            "polymorphic_payload": {"total": 250.0, "vendor": "IntegrationCo"},
        }
        choice = MagicMock()
        choice.message.content = json.dumps(raw_payload)
        response = MagicMock()
        response.choices = [choice]
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = response
        mock_groq_cls.return_value = mock_client

        # Upload
        file_data = BytesIO(b"Integration test content")
        file_data.name = "integration_invoice.txt"
        upload_resp = self.client.post(
            reverse("document-upload"), {"file": file_data}, format="multipart"
        )
        self.assertEqual(upload_resp.status_code, 201)
        doc_id = upload_resp.json()["id"]

        # Process
        process_resp = self.client.post(
            reverse("document-process", args=[doc_id])
        )
        self.assertEqual(process_resp.status_code, 202)
        result = process_resp.json()["result"]
        self.assertEqual(result["analysis_metadata"]["classification"], "Invoice")
        self.assertEqual(result["polymorphic_payload"]["total"], 250.0)

        # Detail (verify persistence)
        detail_resp = self.client.get(
            reverse("document-detail", args=[doc_id])
        )
        self.assertEqual(detail_resp.status_code, 200)
        body = detail_resp.json()
        self.assertEqual(body["analysis_metadata"]["summary"], "Integration test invoice")
        self.assertEqual(body["polymorphic_payload"]["vendor"], "IntegrationCo")
