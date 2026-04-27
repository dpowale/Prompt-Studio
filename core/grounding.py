from __future__ import annotations

import io
import importlib
import re
from pathlib import Path
from typing import Iterable

SUPPORTED_UPLOAD_TYPES = ["txt", "md", "pdf", "docx"]
MAX_GROUNDING_DOCUMENTS = 5
TEXT_EXTENSIONS = {".txt", ".md", ".rst", ".csv", ".json", ".yaml", ".yml"}


def normalize_text(text: str) -> str:
    text = text.replace("\x00", " ")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    return text.strip()


def decode_text_bytes(data: bytes) -> str:
    for encoding in ("utf-8", "utf-8-sig", "cp1252", "latin-1"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def chunk_text(text: str, max_chars: int = 1800, overlap: int = 180) -> list[str]:
    text = normalize_text(text)
    if not text:
        return []

    if len(text) <= max_chars:
        return [text]

    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = min(len(text), start + max_chars)
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= len(text):
            break
        start = max(0, end - overlap)
    return chunks


def summarize_text(text: str, max_chunks: int = 3, sentences_per_chunk: int = 2) -> str:
    chunks = chunk_text(text)
    if not chunks:
        return ""

    summaries: list[str] = []
    for idx, chunk in enumerate(chunks[:max_chunks], start=1):
        sentences = re.split(r"(?<=[.!?])\s+", chunk)
        picked = " ".join(sentences[:sentences_per_chunk]).strip()
        picked = picked or chunk[:320].strip()
        summaries.append(f"Chunk {idx}: {picked[:420]}")
    return "\n".join(summaries)


def extract_document_text(name: str, data: bytes) -> tuple[str, str | None]:
    suffix = Path(name).suffix.lower()
    try:
        if suffix in TEXT_EXTENSIONS or not suffix:
            return normalize_text(decode_text_bytes(data)), None

        if suffix == ".pdf":
            try:
                PdfReader = importlib.import_module("pypdf").PdfReader
            except ImportError:
                return "", "Install pypdf to extract PDF grounding documents."
            reader = PdfReader(io.BytesIO(data))
            text = "\n\n".join((page.extract_text() or "") for page in reader.pages)
            return normalize_text(text), None

        if suffix == ".docx":
            try:
                Document = importlib.import_module("docx").Document
            except ImportError:
                return "", "Install python-docx to extract DOCX grounding documents."
            document = Document(io.BytesIO(data))
            text = "\n".join(paragraph.text for paragraph in document.paragraphs)
            return normalize_text(text), None
    except Exception as exc:
        return "", f"Could not read {name}: {exc}"

    return "", f"Unsupported grounding file type: {suffix or 'unknown'}"


def extract_grounding_documents(uploaded_files: Iterable, kind: str) -> list[dict]:
    documents: list[dict] = []
    for index, uploaded_file in enumerate(list(uploaded_files or [])[:MAX_GROUNDING_DOCUMENTS], start=1):
        name = getattr(uploaded_file, "name", f"document_{index}")
        raw_bytes = uploaded_file.getvalue()
        text, error = extract_document_text(name, raw_bytes)
        source_id = f"SOURCE_{kind.upper()}_{index}"
        summary = summarize_text(text)
        documents.append(
            {
                "source_id": source_id,
                "name": name,
                "kind": kind,
                "summary": summary,
                "text": text,
                "char_count": len(text),
                "chunk_count": len(chunk_text(text)) if text else 0,
                "error": error,
            }
        )
    return documents


def build_grounding_brief(manual_text: str, documents: list[dict], purpose: str) -> str:
    parts: list[str] = []
    manual_text = normalize_text(manual_text or "")
    if manual_text:
        parts.append(f"Manual {purpose} guidance:\n{manual_text}")

    for document in documents or []:
        if document.get("error"):
            continue
        source_id = document.get("source_id", "SOURCE_UNKNOWN")
        name = document.get("name", "unnamed")
        summary = document.get("summary", "") or document.get("text", "")[:500]
        parts.append(f"{source_id} ({name}) summary:\n{summary}")

    return "\n\n".join(part for part in parts if part).strip()
