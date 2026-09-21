"""
schemas/document.py
-------------------
Pydantic request/response models for the document ingestion API.

DocumentCreate  — internal schema: passed from service → repository.
                  Includes extracted_text so the repository can persist it.
                  Never serialised to an HTTP response.

DocumentResponse — external API schema: returned by POST /documents/upload
                   and GET /documents/{id}.
                   Does NOT include extracted_text (could be multi-megabyte).
"""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class DocumentCreate(BaseModel):
    """
    Internal schema for inserting a document record.

    Used by DocumentService → DocumentRepository.
    Not exposed in any API response.
    """

    filename: str
    file_type: str            # "pdf" | "docx"
    file_size_bytes: int
    char_count: int
    extracted_text: str       # full extracted text — stored in DB, not in response
    status: str = "extracted"


class DocumentResponse(BaseModel):
    """
    Public API response for a document resource.

    Returned by:
      POST /documents/upload  → 201 Created
      GET  /documents/{id}    → 200 OK

    extracted_text is intentionally excluded:
      - It may be megabytes in size.
      - Consumers that need it (Milestone 2 chunking) read it directly from DB.
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    filename: str
    file_type: str
    file_size_bytes: int
    char_count: int
    status: str
    uploaded_at: datetime
