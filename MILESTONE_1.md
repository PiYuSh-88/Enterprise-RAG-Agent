# Milestone 1 — Document Ingestion (Upload → Validate → Extract)

Assumes Milestone 0 is complete: project structure, config, docker-compose
(Postgres + Qdrant), DB/Qdrant connectivity, and /health all exist and work.

## Goal
Add the first slice of the document-ingestion pipeline on top of the M0
foundation.

## Scope
Upload → Validate → Extract text (PDF/DOCX only)

## Out of scope (do not implement yet)
- Chunking
- Embeddings
- Vector search / retrieval
- LLM calls
- Agents
- Authentication
- Deployment (Kubernetes/AWS/Terraform)
- Redis, Celery, monitoring, MLOps

This is the boundary. Do not cross it without explicit approval.

---

## Prompt to give Antigravity

Read roadmap.md and NOTES.md completely before making any changes. Milestone 0
(project foundation: config, docker-compose, DB/Qdrant connectivity, /health)
is already complete — inspect the current repository state before proposing
anything so you build on top of it rather than re-creating it.

roadmap.md is the long-term specification — do NOT attempt to implement it.
NOTES.md contains locked-in stack and architecture decisions — follow them
exactly, do not substitute different libraries, models, or patterns.

For this task, implement ONLY document ingestion through:

Upload → Validate → Extract

Requirements:
- Follow the existing service-layer and repository-pattern architecture —
  add a DocumentService and DocumentRepository consistent with what M0
  already established, not a parallel structure.
- Services depend on interfaces/protocols (see services/interfaces.py from
  M0), not concrete classes.
- Implement PDF/DOCX upload handling (pypdf, python-docx per NOTES.md).
- Validate file type and file size BEFORE extraction runs.
- Store document metadata (filename, upload date) via the repository layer,
  using the existing DB connectivity from M0 — even though we're not using
  this metadata for filtering yet.
- Add tests under tests/unit (mocked) for validation logic, and under
  tests/integration for the full upload → validate → extract flow against
  the real Postgres from docker-compose.

Do NOT implement chunking, embeddings, Qdrant vector inserts, LLM calls,
agents, authentication, or any infra beyond what M0 already set up.

Before coding:
1. Inspect the repository as it currently stands.
2. Briefly explain what you intend to add and where it fits into the
   existing M0 structure.
3. Identify any assumptions you're making.
4. Wait for my approval before implementing.

After implementation:
1. Run the tests (unit and integration).
2. Run the application and verify the upload → validate → extract flow
   manually (e.g. via /docs or curl) — confirm a real PDF and a real DOCX
   both work, and that an invalid file type or oversized file is rejected.
3. Report exactly what was changed and what was verified.

STOP after this milestone. Do not continue to chunking/embeddings unless
explicitly instructed.
