# Milestone 2 — Document Chunking, Embedding & Vector Persistence

Assumes Milestone 0 (foundation, config, docker-compose, health check) and
Milestone 1 (document upload, validation, text extraction, PostgreSQL persistence)
are complete, tested, and verified.

## Goal
Implement the second slice of the document-ingestion pipeline:
take an existing extracted document from PostgreSQL, split its text into
chunks, generate vector embeddings, and persist the vectors and minimal chunk
metadata in Qdrant.

## Scope
Existing Stored Document
→ Read extracted text
→ Chunk (RecursiveCharacterTextSplitter: chunk_size=1000, chunk_overlap=150)
→ Generate embeddings (1536 dimensions, text-embedding-3-small)
→ Store vectors + minimal chunk metadata in Qdrant (`rag_documents` collection)
→ Update document status in PostgreSQL (`indexing` → `indexed` / `error`)

## Out of Scope (Do Not Implement)
- Retrieval / vector search queries (`GET /documents/search`, etc.)
- BM25 / hybrid search
- Reranking
- LLM answer generation
- Conversational memory / chat history
- Agents / tool calling
- Asynchronous task queues (Celery / Redis)
- Authentication / authorization / document-level access control
- Cloud deployment (Kubernetes / AWS / Terraform)

---

## Technical Specifications & Decisions

### 1. Chunking
- Library: `langchain-text-splitters` -> `RecursiveCharacterTextSplitter`
- Chunk size: `1000` characters (`chunk_size` from settings)
- Chunk overlap: `150` characters (`chunk_overlap` from settings)
- Separators: `["\n\n", "\n", " ", ""]`
- Boundaries: Chunking is strictly per-document.
- Point IDs: Deterministic UUIDv5 strings using `uuid.uuid5(uuid.NAMESPACE_DNS, f"{doc_id}:{chunk_index}")`.

### 2. Embeddings
- Model: OpenAI `text-embedding-3-small`
- Vector dimension: `1536`
- Batch size: 100 chunks per embedding API request
- Interface: `IEmbeddingService` Protocol
- Testing: Mocked in unit tests; deterministic synthetic local 1536-dim vector generator in integration tests. Never require a live OpenAI API key for automated test suites.

### 3. Vector Storage (Qdrant)
- Collection: `rag_documents` (`qdrant_collection_name` from settings)
- Vector size: `1536`
- Distance: `Cosine`
- Collection initialization: Handled lazily and idempotently inside `ensure_collection()` during the indexing flow, not during FastAPI startup/lifespan.
- Minimal Payload:
  - `document_id`: string (UUID)
  - `chunk_index`: int
  - `text`: string
  - `char_start`: int
  - `char_end`: int
  - `char_count`: int
  - `filename`: string
  - `file_type`: string
- Safe re-indexing:
  1. Chunk text.
  2. Generate all embeddings.
  3. Upsert new points (overwriting points with matching deterministic IDs).
  4. Query existing points for `document_id` and delete any stale points with `chunk_index >= new_chunk_count`.
  5. Update status to `indexed`.
  If embedding or upsert fails, existing points are preserved and status becomes `error`.

### 4. Relational Persistence (PostgreSQL)
- Table: `documents`
- Track status transitions: `extracted` -> `indexing` -> `indexed` (or `error`).
