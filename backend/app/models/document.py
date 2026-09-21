"""
models/document.py
------------------
SQLAlchemy ORM model for the `documents` table.

Stores document metadata and the raw extracted text.

Design note:
  extracted_text is stored here (not returned in the API response) so that
  Milestone 2 can retrieve it directly from Postgres for chunking/embedding
  without requiring re-extraction or a major schema change.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Document(Base):
    """Metadata and extracted text for a single uploaded document."""

    __tablename__ = "documents"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    filename: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="Client-supplied filename, path-sanitised before storage",
    )
    file_type: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
        comment="Lowercase extension without dot: 'pdf' or 'docx'",
    )
    file_size_bytes: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="Size of the uploaded file in bytes",
    )
    char_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="Character count of the extracted text",
    )
    extracted_text: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="Full extracted text — not returned in the API response; consumed by M2 chunking",
    )
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="extracted",
        comment="Ingestion status: extracted | chunking | indexed | error",
    )
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        comment="UTC timestamp set by the database on INSERT",
    )

    def __repr__(self) -> str:
        return (
            f"<Document id={self.id!s:.8} filename={self.filename!r} "
            f"status={self.status!r}>"
        )
