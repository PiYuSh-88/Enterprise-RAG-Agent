"""
ingestion/extractor.py
----------------------
Pure text-extraction functions for supported document types.

Design:
  - All functions are synchronous pure functions (bytes → str).
    They have no I/O side effects, making them trivially unit-testable.
  - The service layer calls these after validation passes.
  - ExtractionError wraps library-specific exceptions so callers
    only need to catch one exception type.

Supported types (NOTES.md):
  PDF  → pypdf
  DOCX → python-docx

Out of scope (NOTES.md): OCR for scanned PDFs is deferred to v2.
"""

import io
from pathlib import PurePosixPath

from docx import Document as DocxDocument
from pypdf import PdfReader
from pypdf.errors import PdfReadError

# ── Constants ─────────────────────────────────────────────────────────────────

ALLOWED_EXTENSIONS: frozenset[str] = frozenset({"pdf", "docx"})

# Maps lowercase extension → expected MIME type.
# Used for MIME validation when the client provides Content-Type.
MIME_BY_EXTENSION: dict[str, str] = {
    "pdf": "application/pdf",
    "docx": (
        "application/vnd.openxmlformats-officedocument"
        ".wordprocessingml.document"
    ),
}


# ── Exceptions ────────────────────────────────────────────────────────────────


class ExtractionError(Exception):
    """
    Raised when text extraction fails (e.g. corrupt, password-protected,
    or structurally invalid file).  Never raised for validation failures —
    those are handled upstream in DocumentService.
    """


# ── Helpers ───────────────────────────────────────────────────────────────────


def get_extension(filename: str) -> str:
    """
    Return the lowercased extension (without leading dot) from a filename.

    Uses PurePosixPath to strip any path components first so a client cannot
    pass '../../evil.pdf' and have the dot-split behave unexpectedly.

    Returns an empty string if there is no extension.
    """
    safe_name = PurePosixPath(filename).name
    suffix = PurePosixPath(safe_name).suffix          # e.g. ".PDF"
    return suffix.lstrip(".").lower()                  # e.g. "pdf"


def sanitise_filename(filename: str) -> str:
    """
    Strip path components from a client-supplied filename.

    Prevents directory traversal in the stored filename field.
    Example: '../../etc/passwd.pdf' → 'passwd.pdf'
    """
    return PurePosixPath(filename).name


# ── Extractors ────────────────────────────────────────────────────────────────


def extract_pdf(content: bytes) -> str:
    """
    Extract all text from a PDF file given as raw bytes.

    Uses pypdf.  Pages with no extractable text (e.g. scanned images)
    contribute an empty string — no OCR is attempted (NOTES.md).

    Raises ExtractionError if the bytes are not a valid or readable PDF.
    """
    try:
        reader = PdfReader(io.BytesIO(content))
        pages = [page.extract_text() or "" for page in reader.pages]
        return "\n".join(pages)
    except PdfReadError as exc:
        raise ExtractionError(f"PDF extraction failed: {exc}") from exc
    except Exception as exc:
        raise ExtractionError(f"PDF extraction failed: {exc}") from exc


def extract_docx(content: bytes) -> str:
    """
    Extract all paragraph text from a DOCX file given as raw bytes.

    Uses python-docx.  Paragraphs are joined with newlines.

    Raises ExtractionError if the bytes are not a valid DOCX file.
    """
    try:
        doc = DocxDocument(io.BytesIO(content))
        return "\n".join(p.text for p in doc.paragraphs)
    except Exception as exc:
        raise ExtractionError(f"DOCX extraction failed: {exc}") from exc


def extract(filename: str, content: bytes) -> str:
    """
    Dispatch to the correct extractor based on the file extension.

    Callers should validate the extension before calling this function.
    Raises ValueError for unsupported extensions (should not happen if
    validation is done upstream, but guards against incorrect direct calls).
    """
    ext = get_extension(filename)
    if ext == "pdf":
        return extract_pdf(content)
    if ext == "docx":
        return extract_docx(content)
    raise ValueError(f"No extractor for extension '{ext}'")
