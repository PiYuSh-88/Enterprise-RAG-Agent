"""
tests/unit/test_chunker.py
--------------------------
Unit tests for document chunking logic.
"""

import uuid

from app.ingestion.chunker import chunk_document, generate_chunk_id


def test_chunk_id_is_deterministic():
    doc_id = uuid.uuid4()
    id1 = generate_chunk_id(doc_id, 0)
    id2 = generate_chunk_id(doc_id, 0)
    id3 = generate_chunk_id(doc_id, 1)

    assert id1 == id2
    assert id1 != id3


def test_chunk_empty_text():
    doc_id = uuid.uuid4()
    assert chunk_document("", doc_id, "doc.pdf", "pdf") == []
    assert chunk_document("   \n\t  ", doc_id, "doc.pdf", "pdf") == []


def test_chunk_short_text_single_chunk():
    doc_id = uuid.uuid4()
    text = "Short text under 1000 characters."
    chunks = chunk_document(text, doc_id, "test.pdf", "pdf", chunk_size=1000, chunk_overlap=150)

    assert len(chunks) == 1
    assert chunks[0].chunk_index == 0
    assert chunks[0].text == text
    assert chunks[0].document_id == doc_id
    assert chunks[0].filename == "test.pdf"
    assert chunks[0].file_type == "pdf"
    assert chunks[0].char_start == 0
    assert chunks[0].char_end == len(text)
    assert chunks[0].char_count == len(text)
    assert chunks[0].point_id == generate_chunk_id(doc_id, 0)


def test_chunk_long_text_overlap():
    doc_id = uuid.uuid4()
    # Create 2500 character text
    paragraphs = [
        f"Paragraph {i}: " + ("word " * 40)
        for i in range(10)
    ]
    text = "\n\n".join(paragraphs)

    chunks = chunk_document(text, doc_id, "report.docx", "docx", chunk_size=500, chunk_overlap=100)

    assert len(chunks) > 1
    # Check monotonic indices
    for i, chunk in enumerate(chunks):
        assert chunk.chunk_index == i
        assert chunk.document_id == doc_id
        assert chunk.filename == "report.docx"
        assert chunk.file_type == "docx"
        assert chunk.char_count == len(chunk.text)
        assert chunk.point_id == generate_chunk_id(doc_id, i)
        assert chunk.char_start >= 0
        assert chunk.char_end > chunk.char_start


def test_chunk_metadata_minimal_keys():
    doc_id = uuid.uuid4()
    text = "Sample chunk text."
    chunks = chunk_document(text, doc_id, "file.pdf", "pdf")
    chunk = chunks[0]

    # Model dump has exactly the approved minimal keys
    keys = set(chunk.model_dump().keys())
    expected_keys = {
        "point_id",
        "document_id",
        "chunk_index",
        "text",
        "char_start",
        "char_end",
        "char_count",
        "filename",
        "file_type",
    }
    assert keys == expected_keys
