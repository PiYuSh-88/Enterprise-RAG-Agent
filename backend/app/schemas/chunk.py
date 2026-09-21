"""
schemas/chunk.py
----------------
Schemas for document chunks and the indexing response.

DocumentChunk:
    Internal representation of a chunk with deterministic point ID and metadata,
    ready for embedding and Qdrant upsert.

IndexDocumentResponse:
    Public response model returned by POST /documents/{doc_id}/index.
"""

import uuid

from pydantic import BaseModel, ConfigDict, Field


class DocumentChunk(BaseModel):
    """
    Internal representation of a document chunk.

    Contains the text slice, character offsets, and minimal metadata
    persisted into Qdrant vector payload.
    """

    point_id: uuid.UUID = Field(
        description="Deterministic UUIDv5 calculated from document_id and chunk_index"
    )
    document_id: uuid.UUID
    chunk_index: int = Field(ge=0)
    text: str
    char_start: int = Field(ge=0)
    char_end: int = Field(ge=0)
    char_count: int = Field(ge=0)
    filename: str
    file_type: str


class IndexDocumentResponse(BaseModel):
    """
    Public API response model for document indexing.

    Returned by:
        POST /documents/{doc_id}/index -> 200 OK
    """

    model_config = ConfigDict(from_attributes=True)

    document_id: uuid.UUID
    status: str
    chunks_indexed: int
