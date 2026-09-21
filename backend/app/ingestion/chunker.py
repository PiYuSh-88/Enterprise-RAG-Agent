"""
ingestion/chunker.py
--------------------
Pure functions for document text chunking using RecursiveCharacterTextSplitter.

Architecture note (NOTES.md):
  Chunking uses langchain-text-splitters -> RecursiveCharacterTextSplitter
  - chunk_size = 1000 (characters)
  - chunk_overlap = 150 (characters)
  - boundaries: strictly per-document, overlap only within the same document
  - chunk IDs: deterministic UUIDv5 using uuid.uuid5(NAMESPACE_DNS, f"{doc_id}:{chunk_index}")
"""

import uuid

from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.schemas.chunk import DocumentChunk


def generate_chunk_id(document_id: uuid.UUID, chunk_index: int) -> uuid.UUID:
    """
    Generate a deterministic UUIDv5 for a document chunk.

    Guarantees reproducibility and idempotency: re-chunking the same document
    always yields the same point ID for each chunk index.
    """
    return uuid.uuid5(uuid.NAMESPACE_DNS, f"{document_id}:{chunk_index}")


def chunk_document(
    text: str,
    document_id: uuid.UUID,
    filename: str,
    file_type: str,
    chunk_size: int = 1000,
    chunk_overlap: int = 150,
) -> list[DocumentChunk]:
    """
    Split document text into overlapping character chunks with minimal metadata.

    Args:
        text: The full extracted document text.
        document_id: The UUID of the parent document.
        filename: Sanitised filename of the document.
        file_type: Extension ('pdf' or 'docx').
        chunk_size: Target character count per chunk (default 1000).
        chunk_overlap: Overlap in characters between adjacent chunks (default 150).

    Returns:
        A list of DocumentChunk instances, each with deterministic ID and metadata.
    """
    if not text or not text.strip():
        return []

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        separators=["\n\n", "\n", " ", ""],
        length_function=len,
    )

    raw_chunks = splitter.split_text(text)
    chunks: list[DocumentChunk] = []

    search_pos = 0
    for idx, chunk_str in enumerate(raw_chunks):
        point_id = generate_chunk_id(document_id, idx)

        # Calculate character offsets in the original text
        start_idx = text.find(chunk_str, search_pos)
        if start_idx == -1:
            # Fallback: search from beginning if not found from search_pos
            start_idx = text.find(chunk_str)
            if start_idx == -1:
                start_idx = search_pos

        end_idx = start_idx + len(chunk_str)
        # Advance search position allowing for overlap
        search_pos = max(start_idx + 1, end_idx - chunk_overlap)

        chunks.append(
            DocumentChunk(
                point_id=point_id,
                document_id=document_id,
                chunk_index=idx,
                text=chunk_str,
                char_start=start_idx,
                char_end=end_idx,
                char_count=len(chunk_str),
                filename=filename,
                file_type=file_type,
            )
        )

    return chunks
