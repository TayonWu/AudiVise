# AudiVise Python Rewrite Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the Spring Boot/Vue prototype with a locally runnable Python/React video-understanding Agent platform featuring asynchronous processing, evidence-grounded answers, and traceable tool execution.

**Architecture:** Use a modular FastAPI application as the HTTP boundary and PostgreSQL as the durable source of truth. Celery workers execute idempotent media-processing stages, MinIO stores media artifacts, Redis provides broker/cache services, Qdrant stores transcript vectors, and LangGraph orchestrates evidence-grounded tools. A React TypeScript client consumes REST and SSE endpoints.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2, Alembic, Pydantic Settings, Celery, Redis, MinIO, FFmpeg, Qdrant, LangGraph, pytest, React, TypeScript, Vite, Docker Compose.

---

### Task 1: Python application foundation

**Files:**
- Create: `backend/pyproject.toml`
- Create: `backend/app/main.py`
- Create: `backend/app/core/config.py`
- Create: `backend/app/core/database.py`
- Create: `backend/tests/test_health.py`

- [ ] Write a failing FastAPI health-check test expecting `GET /api/health` to return service and dependency status.
- [ ] Run the test and verify it fails because the application package does not exist.
- [ ] Add the minimal application factory, typed settings, SQLAlchemy session factory, and health route.
- [ ] Run the test suite and verify the health test passes.

### Task 2: Durable domain model and task state machine

**Files:**
- Create: `backend/app/models/*.py`
- Create: `backend/app/schemas/*.py`
- Create: `backend/app/services/task_state.py`
- Create: `backend/tests/test_task_state.py`

- [ ] Write failing tests for valid parsing-stage transitions and rejection of invalid transitions.
- [ ] Implement users, videos, upload sessions, analysis tasks, transcript chunks, conversations, messages, and agent traces using SQLAlchemy.
- [ ] Implement enums and a deterministic task transition service.
- [ ] Add Alembic configuration and an initial migration matching the models.
- [ ] Verify state-machine and model tests pass using SQLite while retaining PostgreSQL-compatible types.

### Task 3: Video and upload APIs

**Files:**
- Create: `backend/app/api/uploads.py`
- Create: `backend/app/api/videos.py`
- Create: `backend/app/services/uploads.py`
- Create: `backend/app/integrations/object_storage.py`
- Create: `backend/tests/test_upload_api.py`

- [ ] Write failing API tests for creating an upload session, completing it idempotently, listing videos, and rejecting duplicate completion.
- [ ] Define a storage protocol and an in-memory implementation for tests.
- [ ] Implement MinIO multipart initialization, part URL generation, completion, and upload-session persistence.
- [ ] Add SHA-256 metadata fields without requiring a browser-side full-file hash before upload.
- [ ] Verify API tests pass.

### Task 4: Celery processing pipeline

**Files:**
- Create: `backend/app/worker/celery_app.py`
- Create: `backend/app/worker/tasks.py`
- Create: `backend/app/services/media_pipeline.py`
- Create: `backend/app/integrations/ffmpeg.py`
- Create: `backend/tests/test_media_pipeline.py`

- [ ] Write failing tests proving completed stages are skipped and retryable failures preserve durable task state.
- [ ] Implement the stages `PROBING`, `EXTRACTING`, `TRANSCRIBING`, `INDEXING`, and `SUMMARIZING`.
- [ ] Store deterministic artifact keys so every stage is reentrant.
- [ ] Configure Celery time limits, acknowledgement-after-completion, retry backoff, and retryable exception classes.
- [ ] Expose task status and SSE progress endpoints, retaining polling as a fallback.

### Task 5: Transcript indexing and evidence retrieval

**Files:**
- Create: `backend/app/integrations/vector_store.py`
- Create: `backend/app/services/transcripts.py`
- Create: `backend/app/services/retrieval.py`
- Create: `backend/tests/test_retrieval.py`

- [ ] Write failing tests for timestamp-preserving chunks, adjacent-chunk merging, and deterministic evidence ordering.
- [ ] Normalize ASR segments into stable chunk IDs with start/end seconds.
- [ ] Implement Qdrant vector upserts and retrieval behind a protocol with an in-memory test adapter.
- [ ] Combine vector results with PostgreSQL keyword matching and rerank merged evidence.
- [ ] Verify every evidence item exposes chunk ID, timestamps, text, and score.

### Task 6: LangGraph Agent and traceability

**Files:**
- Create: `backend/app/agent/graph.py`
- Create: `backend/app/agent/state.py`
- Create: `backend/app/agent/tools.py`
- Create: `backend/app/services/traces.py`
- Create: `backend/app/api/chat.py`
- Create: `backend/tests/test_agent.py`

- [ ] Write failing tests for tool argument validation, evidence-only citations, insufficient-evidence responses, and trace persistence.
- [ ] Implement the tools `search_transcript`, `get_video_metadata`, `get_video_summary`, and `get_task_status`.
- [ ] Build LangGraph nodes for question analysis, conditional tool execution, evidence aggregation, and structured answer generation.
- [ ] Validate that generated citations belong to the current evidence set.
- [ ] Stream `status`, `tool`, `evidence`, `token`, `final`, and `error` events over SSE.
- [ ] Persist node timing, tool summaries, evidence IDs, model metadata, token usage, and classified errors under one trace ID.

### Task 7: React TypeScript client

**Files:**
- Replace: `client/`
- Create: `client/src/features/uploads/*`
- Create: `client/src/features/videos/*`
- Create: `client/src/features/chat/*`
- Create: `client/src/features/traces/*`

- [ ] Configure Vite, TypeScript, Vitest, and React Testing Library.
- [ ] Implement resumable upload, task progress, video workspace, summary, and transcript views.
- [ ] Implement SSE chat rendering with tool status and timestamped evidence cards.
- [ ] Seek the HTML video player when a citation is selected.
- [ ] Add a trace drawer showing node timing, tool calls, and evidence without exposing secrets.
- [ ] Verify component tests and the production build.

### Task 8: Local deployment, documentation, and verification

**Files:**
- Replace: `docker-compose.yml`
- Create: `backend/Dockerfile`
- Create: `client/Dockerfile`
- Create: `.env.example`
- Replace: `README.md`

- [ ] Add PostgreSQL, Redis, MinIO, Qdrant, API, worker, and web services with health checks.
- [ ] Remove RocketMQ and all committed credentials; document rotation of previously exposed keys.
- [ ] Add Ruff, mypy, pytest, frontend test, and build commands to CI.
- [ ] Document architecture, task state machine, Agent flow, API endpoints, setup, demo script, and design trade-offs.
- [ ] Run backend tests, frontend tests/build, Compose validation, and a local end-to-end smoke test.
