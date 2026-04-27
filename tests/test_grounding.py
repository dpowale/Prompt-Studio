import io
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.grounding import MAX_GROUNDING_DOCUMENTS, extract_document_text, extract_grounding_documents


class FakeUpload:
    def __init__(self, name: str, data: bytes):
        self.name = name
        self._data = data

    def getvalue(self):
        return self._data


class GroundingDocumentTests(unittest.TestCase):
    def test_extract_grounding_documents_supports_txt_and_md(self):
        uploads = [
            FakeUpload("style.txt", b"Short style guide. Use plain language."),
            FakeUpload("notes.md", b"# Facts\nUse only approved release dates."),
        ]

        docs = extract_grounding_documents(uploads, "style")

        self.assertEqual(len(docs), 2)
        self.assertEqual(docs[0]["source_id"], "SOURCE_STYLE_1")
        self.assertIn("Short style guide", docs[0]["text"])
        self.assertEqual(docs[0]["error"], None)
        self.assertIn("approved release dates", docs[1]["text"])

    def test_extract_grounding_documents_enforces_limit_of_five(self):
        uploads = [FakeUpload(f"doc_{index}.txt", f"Document {index}".encode("utf-8")) for index in range(1, 8)]

        docs = extract_grounding_documents(uploads, "factual")

        self.assertEqual(len(docs), MAX_GROUNDING_DOCUMENTS)
        self.assertEqual(docs[-1]["source_id"], "SOURCE_FACTUAL_5")

    def test_extract_document_text_reads_docx_bytes(self):
        class FakeParagraph:
            def __init__(self, text: str):
                self.text = text

        class FakeDocument:
            def __init__(self, _stream):
                self.paragraphs = [
                    FakeParagraph("Approved positioning statement"),
                    FakeParagraph("Second paragraph for summary"),
                ]

        fake_module = types.SimpleNamespace(Document=FakeDocument)
        with patch("core.grounding.importlib.import_module", return_value=fake_module):
            text, error = extract_document_text("reference.docx", b"fake docx bytes")

        self.assertIsNone(error)
        self.assertIn("Approved positioning statement", text)
        self.assertIn("Second paragraph", text)

    def test_extract_document_text_reads_pdf_via_pdf_reader(self):
        class FakePage:
            def extract_text(self):
                return "PDF sourced content"

        class FakePdfReader:
            def __init__(self, _stream):
                self.pages = [FakePage()]

        fake_module = types.SimpleNamespace(PdfReader=FakePdfReader)
        with patch("core.grounding.importlib.import_module", return_value=fake_module):
            text, error = extract_document_text("reference.pdf", b"%PDF-1.4 fake bytes")

        self.assertIsNone(error)
        self.assertEqual(text, "PDF sourced content")


if __name__ == "__main__":
    unittest.main()
