from __future__ import annotations

import io
import importlib
import re
from pathlib import Path
from typing import Iterable

SUPPORTED_UPLOAD_TYPES = ["txt", "md", "pdf", "docx"]
MAX_GROUNDING_DOCUMENTS = 5

# FIX (Warning #6): Global context budget enforced in build_grounding_brief.
# Prevents context window overflow when multiple large documents are uploaded.
MAX_CONTEXT_CHARS = 6_000

# Characters per document = budget divided equally across documents, capped here
# so a single document never consumes the whole budget.
MAX_CHARS_PER_DOC = MAX_CONTEXT_CHARS // MAX_GROUNDING_DOCUMENTS

TEXT_EXTENSIONS = {".txt", ".md", ".rst", ".csv", ".json", ".yaml", ".yml"}

# FIX (Warning #7): Single source of truth for word-count thresholds.
# These are imported and referenced by dspy_module.py to keep both files in sync.
MIN_SYSTEM_WORDS = 90
MAX_SYSTEM_WORDS = 150
MIN_USER_WORDS = 60
MAX_USER_WORDS = 120


def normalize_text(text: str) -> str:
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


def _is_likely_binary(text: str, null_byte_threshold: float = 0.01) -> bool:
    """Return True if the decoded text looks like a binary file.

    FIX (Warning #4): After decoding, check null-byte density. If more than
    1% of characters are null bytes, the source was almost certainly binary
    and the decoded text is garbage — return an error instead of corrupted
    grounding context.
    """
    if not text:
        return False
    null_count = text.count("\x00")
    return (null_count / len(text)) > null_byte_threshold


def chunk_text(text: str, max_chars: int = 1_800, overlap: int = 180) -> list[str]:
    """Split text into overlapping chunks, breaking at sentence boundaries.

    FIX (Warning #3): After computing the raw character boundary, walk
    backwards to the nearest sentence end (. ! ?) so chunks never begin or
    end mid-sentence. Falls back to the character boundary only when no
    sentence end is found in the final 20 % of the window.
    """
    text = normalize_text(text)
    if not text:
        return []
    if len(text) <= max_chars:
        return [text]

    # Pattern matches end of a sentence followed by whitespace or end-of-string.
    _SENTENCE_END = re.compile(r"[.!?][\s]")
    fallback_margin = max(1, int(max_chars * 0.20))

    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = min(len(text), start + max_chars)

        if end < len(text):
            # Search backwards from `end` for the nearest sentence boundary
            # within the last `fallback_margin` characters.
            search_window = text[max(start, end - fallback_margin) : end]
            matches = list(_SENTENCE_END.finditer(search_window))
            if matches:
                # +1 to include the punctuation character itself in this chunk.
                boundary_offset = matches[-1].start() + 1
                end = max(start, end - fallback_margin) + boundary_offset

        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)

        if end >= len(text):
            break
        start = max(0, end - overlap)

    return chunks


def summarize_chunks(
    chunks: list[str],
    max_chunks: int = 3,
    sentences_per_chunk: int = 2,
) -> str:
    """Return a short human-readable summary used for UI previews only.

    NOTE: This output is intentionally NOT passed as LM grounding context.
    Full chunk text (up to MAX_CHARS_PER_DOC) is used for grounding instead.
    See build_grounding_brief.
    """
    if not chunks:
        return ""

    summaries: list[str] = []
    for idx, chunk in enumerate(chunks[:max_chunks], start=1):
        sentences = re.split(r"(?<=[.!?])\s+", chunk)
        picked = " ".join(sentences[:sentences_per_chunk]).strip()
        picked = picked or chunk[:320].strip()
        summaries.append(f"Chunk {idx}: {picked[:420]}")
    return "\n".join(summaries)


def summarize_text(
    text: str,
    max_chunks: int = 3,
    sentences_per_chunk: int = 2,
) -> str:
    chunks = chunk_text(text)
    return summarize_chunks(chunks, max_chunks=max_chunks, sentences_per_chunk=sentences_per_chunk)


def _truncate_at_sentence(text: str, max_chars: int) -> str:
    """Truncate *text* to at most *max_chars*, ending at a sentence boundary.

    Used by build_grounding_brief to stay within per-document budget while
    avoiding mid-sentence cuts.
    """
    if len(text) <= max_chars:
        return text
    window = text[:max_chars]
    # Walk backwards for the last sentence end.
    match = re.search(r"[.!?][\s]", window[::-1])
    if match:
        cut = max_chars - match.start()
        return text[:cut].strip()
    # No sentence boundary found — fall back to character limit.
    return window.strip()


def extract_document_text(name: str, data: bytes) -> tuple[str, str | None]:
    suffix = Path(name).suffix.lower()
    try:
        if suffix in TEXT_EXTENSIONS or not suffix:
            raw = decode_text_bytes(data)
            # FIX (Warning #4): Reject likely-binary files after decoding.
            if _is_likely_binary(raw):
                return "", f"File '{name}' appears to be binary — cannot extract text."
            return normalize_text(raw), None

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
        return "", f"Could not read '{name}': {exc}"

    return "", f"Unsupported grounding file type: {suffix or 'unknown'}"


def extract_grounding_documents(uploaded_files: Iterable, kind: str) -> list[dict]:
    """Extract and chunk each uploaded file, returning structured document dicts.

    Each dict contains:
        source_id   — citation-friendly identifier, e.g. SOURCE_SYSTEM_1
        name        — original filename
        kind        — caller-supplied kind tag (e.g. "system", "user")
        summary     — short human-readable preview (for UI only, NOT for LM context)
        text        — full extracted and normalised text
        char_count  — length of full text
        chunk_count — number of chunks produced
        error       — error string if extraction failed, else None
    """
    documents: list[dict] = []
    for index, uploaded_file in enumerate(list(uploaded_files or [])[:MAX_GROUNDING_DOCUMENTS], start=1):
        name = getattr(uploaded_file, "name", f"document_{index}")
        raw_bytes = uploaded_file.getvalue()
        text, error = extract_document_text(name, raw_bytes)
        source_id = f"SOURCE_{kind.upper()}_{index}"
        chunks = chunk_text(text) if text else []
        # Summary is for UI previews only — see build_grounding_brief for LM context.
        summary = summarize_chunks(chunks)
        documents.append(
            {
                "source_id": source_id,
                "name": name,
                "kind": kind,
                "summary": summary,
                "text": text,
                "char_count": len(text),
                "chunk_count": len(chunks),
                "error": error,
            }
        )
    return documents


def build_grounding_brief(
    manual_text: str,
    documents: list[dict],
    purpose: str,
    max_context_chars: int = MAX_CONTEXT_CHARS,
) -> str:
    """Build the grounding context string passed to the LM's *context* input field.

    FIX (Critical #3): Passes full chunk text (up to per-document budget) instead
    of truncated summaries. Summaries are only for UI display — the LM needs actual
    source passages to produce traceable citations.

    FIX (Warning #6): Enforces MAX_CONTEXT_CHARS total, distributed equally across
    documents, with sentence-boundary truncation to avoid mid-sentence cuts.

    Args:
        manual_text:       Free-text grounding notes entered by the user.
        documents:         List of dicts from extract_grounding_documents.
        purpose:           Label for the manual_text section (e.g. "system", "user").
        max_context_chars: Total character budget for all grounding text sent to LM.
    """
    parts: list[str] = []
    manual_text = normalize_text(manual_text or "")
    if manual_text:
        parts.append(f"Manual {purpose} guidance:\n{manual_text}")

    valid_docs = [d for d in (documents or []) if not d.get("error") and d.get("text")]
    if not valid_docs:
        return "\n\n".join(part for part in parts if part).strip()

    # Distribute the budget equally across documents.
    per_doc_budget = max(200, max_context_chars // max(len(valid_docs), 1))

    for document in valid_docs:
        source_id = document.get("source_id", "SOURCE_UNKNOWN")
        name = document.get("name", "unnamed")
        full_text = document.get("text", "")

        # FIX (Critical #3): Use full text up to per-doc budget, not summaries.
        grounding_text = _truncate_at_sentence(full_text, per_doc_budget)
        parts.append(f"{source_id} ({name}):\n{grounding_text}")

    return "\n\n".join(part for part in parts if part).strip()
