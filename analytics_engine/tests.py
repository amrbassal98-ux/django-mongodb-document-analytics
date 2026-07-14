import json
from io import BytesIO
from unittest.mock import MagicMock, patch

from django.test import TestCase
from django.urls import reverse

from .models import AnalysisMetadata, Annotation, Document
from .services import DocumentProcessingService, analyze_document


# ── Model Tests ──────────────────────────────────────────────────────────────

class DocumentModelTests(TestCase):
    def test_create_document_minimal(self):
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
        doc = Document.objects.create(
            title="my_doc.pdf", file_type="pdf", raw_text="data"
        )
        self.assertEqual(str(doc), "my_doc.pdf")

    def test_document_with_annotations(self):
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
        doc = Document.objects.create(
            title="defaults.pdf",
            file_type="pdf",
            raw_text="test",
            polymorphic_payload={"a": 1},
        )
        doc.refresh_from_db()
        self.assertEqual(doc.polymorphic_payload, {"a": 1})


# ── Service-Layer Tests ──────────────────────────────────────────────────────

class DocumentProcessingServiceTests(TestCase):
    def _build_mock_groq_response(self, content: str):
        choice = MagicMock()
        choice.message.content = content
        response = MagicMock()
        response.choices = [choice]
        return response

    # -- Happy path -----------------------------------------------------------

    @patch("analytics_engine.services.Groq")
    def test_analyze_success(self, mock_groq_cls):
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
            title="inv.pdf", file_type="pdf", raw_text="INVOICE $100"
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
        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = Exception("Network error")
        mock_groq_cls.return_value = mock_client

        doc = Document.objects.create(
            title="fail.pdf", file_type="pdf", raw_text="oops"
        )
        result = DocumentProcessingService().analyze(doc)
        self.assertIn("error", result)
        self.assertIn("Groq API call failed", result["error"])
        self.assertIn("Network error", result["error"])

    # -- Error handling: malformed JSON ---------------------------------------

    @patch("analytics_engine.services.Groq")
    def test_analyze_json_decode_failure(self, mock_groq_cls):
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


# ── View Tests ───────────────────────────────────────────────────────────────

class DocumentUploadViewTests(TestCase):
    def test_upload_success(self):
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

    def test_upload_missing_file(self):
        resp = self.client.post(reverse("document-upload"), {}, format="multipart")
        self.assertEqual(resp.status_code, 400)
        self.assertIn("error", resp.json())

    def test_upload_no_extension(self):
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
    def test_detail_existing(self):
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
        resp = self.client.get(
            reverse("document-detail", args=["000000000000000000000000"])
        )
        self.assertEqual(resp.status_code, 404)


class DocumentProcessViewTests(TestCase):
    @patch("analytics_engine.views._trigger_llm_pipeline")
    def test_process_success(self, mock_pipeline):
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
        resp = self.client.post(
            reverse("document-process", args=["000000000000000000000000"])
        )
        self.assertEqual(resp.status_code, 404)


class DocumentAnnotateViewTests(TestCase):
    def test_annotate_success(self):
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
        resp = self.client.post(
            reverse("document-annotate", args=["000000000000000000000000"]),
            data=json.dumps({"user_id": "x", "comment": "y", "highlighted_text": "z"}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 404)


# ── Integration-Style View Test (mocked Groq through the full stack) ────────

class FullPipelineViewTest(TestCase):
    @patch("analytics_engine.services.Groq")
    def test_upload_then_process_then_detail(self, mock_groq_cls):
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
