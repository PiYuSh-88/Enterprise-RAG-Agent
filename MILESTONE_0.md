# Milestone 0 — Project Foundation

## Goal
Get the skeleton running end-to-end: config, containers, DB connectivity,
Qdrant connectivity, one health endpoint, basic tests. No RAG logic yet.

## In scope
- Repository structure under backend/ (services/, repositories/, routers/,
  schemas/, models/, core/, ingestion/) — propose it, don't assume it
- Configuration management via pydantic-settings reading from .env
- docker-compose.yml for Postgres + Qdrant (dev only)
- Database connectivity (SQLAlchemy async engine/session, Alembic initialized
  with zero migrations yet)
- Qdrant connectivity (client wrapped in repositories/vector_repository.py)
- A single GET /health endpoint that checks Postgres and Qdrant are reachable
  and returns their status
- Basic tests under tests/unit confirming config loads and health check logic
  works (mocked, no real containers required for unit tests)

## Out of scope (do not implement yet)
- Document upload, validation, or extraction
- Chunking, embeddings, vector search
- LLM calls
- Agents
- Authentication
- Kubernetes, AWS, Terraform
- Redis, Celery, Prometheus, Grafana

This is the boundary. Do not cross it without explicit approval.

---

## First prompt to give Antigravity

Read roadmap.md and NOTES.md completely before making any changes.

This repository is for an Enterprise RAG + Agent System. roadmap.md is the
long-term specification — do NOT attempt to implement it. NOTES.md contains
locked-in stack and architecture decisions — follow them exactly, do not
substitute different libraries, models, or patterns.

Do not modify anything yet. First:
1. Inspect the repository.
2. Explain the architecture you understand from roadmap.md and NOTES.md.
3. Propose the internal folder/file structure for backend/app/ (services,
   repositories, routers, schemas, models, core, ingestion) consistent with
   the service-layer + repository-pattern requirement.
4. State any assumptions you're making.
5. Wait for my approval before writing any code.

Once approved, implement ONLY Milestone 0 (see MILESTONE_0.md scope):
- Project structure per the approved plan
- pydantic-settings config reading from .env
- docker-compose.yml for Postgres + Qdrant (dev only — no Redis, no monitoring)
- Async SQLAlchemy DB connectivity + Alembic initialized (no migrations yet)
- Qdrant connectivity wrapped in a repository, matching the 1536-dim
  embedding size from NOTES.md
- A single GET /health endpoint reporting Postgres and Qdrant reachability
- Unit tests for config loading and health check logic

Do NOT implement document upload, extraction, chunking, embeddings, retrieval,
LLM calls, agents, authentication, or any deployment/infra beyond the dev
docker-compose file.

After implementation:
1. Run `docker compose up -d` and confirm Postgres and Qdrant are reachable.
2. Run the tests.
3. Start the app and hit /health — confirm it reports both services as up.
4. Report exactly what was changed and what was verified.

STOP after this milestone. Do not continue to Milestone 1 unless explicitly
instructed.
