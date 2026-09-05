# Stack Decisions (v1)

Fixed before implementation starts. Do not change without updating this file.

## Core stack
- Language: Python 3.12
- Backend framework: FastAPI
- Database: PostgreSQL (SQLAlchemy async + asyncpg, Alembic for migrations)
- Vector DB: Qdrant (local via docker-compose for dev)
- Frontend: React / Next.js (not started until backend v1 is stable)
- Containerization: Docker / docker-compose

## LLM + Embeddings
- LLM (answer generation): OpenAI `gpt-4o-mini`
- Embeddings: OpenAI `text-embedding-3-small` — **1536 dimensions**
  - Qdrant collection vector size MUST be set to 1536 to match. Any mismatch will
    cause every insert to fail — verify this explicitly when the collection is created.

## Document processing
- PDF extraction: `pypdf`
- DOCX extraction: `python-docx`
- OCR (scanned PDFs): not implemented in v1 — deferred until explicitly scoped
- Chunking: `langchain-text-splitters` → `RecursiveCharacterTextSplitter`
  - chunk_size = 1000 (characters)
  - chunk_overlap = 150 (characters)

## Testing
- Framework: pytest + pytest-asyncio
- HTTP testing: httpx
- Split tests into `tests/unit` (mocked, fast) and `tests/integration` (real
  Postgres/Qdrant via docker-compose, slower)

## Config
- All settings (chunk_size, top_k, model names, DB URLs, API keys) live in
  `pydantic-settings`, reading from `.env`
- Never hardcode API keys or connection strings
- `.env` is gitignored; only `.env.example` (blank values) is committed

## Architecture (non-negotiable)
FastAPI (routers) → Service Layer → Repository Layer → PostgreSQL / Qdrant

- Dependency injection via FastAPI's `Depends`, wired against interfaces/protocols
  defined in `services/interfaces.py` — not concrete classes directly — so services
  are mockable in tests without hitting real APIs.
- Vector DB access is wrapped in a `repositories/vector_repository.py`, never called
  directly from `RetrieverService`.

## Explicitly NOT in v1 (do not implement without approval)
Kubernetes, Terraform, AWS, Redis, Celery, Prometheus, Grafana, multi-tenancy,
authentication, agents/tool-calling, reranking, semantic caching, MLOps/eval
dashboards.

These are real parts of the long-term roadmap (see roadmap.md) — just not this phase.
