# AudiVise Media Dedup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebrand the application as AudiVise, support existing audio and video uploads, and prevent duplicate expensive processing through database task uniqueness and renewable Redis content leases.

**Architecture:** Keep the existing `Video` persistence and `/api/videos` compatibility surface while presenting media terminology in the UI. PostgreSQL arbitrates duplicate active tasks for one media row, while a token-owned renewable Redis lease keyed by SHA-256 arbitrates equal content across different rows. Pipeline stages remain durable and idempotent, and worker-local artifacts are removed in a guaranteed cleanup block.

**Tech Stack:** FastAPI, SQLAlchemy, Alembic, Celery, Redis, PostgreSQL, MinIO, FFmpeg, React, TypeScript, Vitest, pytest

---

### Task 1: Accept audio and video uploads

**Files:**
- Modify: `backend/app/schemas/uploads.py`
- Test: `backend/tests/test_upload_api.py`

- [ ] Add tests that POST `/api/uploads` with `audio/mpeg` succeeds and `text/plain` returns 422.
- [ ] Run `python -m pytest tests/test_upload_api.py -q` and confirm the audio test fails because the schema only accepts `video/*`.
- [ ] Change the Pydantic pattern to `^(audio|video)/`.
- [ ] Re-run the upload tests and confirm they pass.

### Task 2: Return one active task for concurrent submissions

**Files:**
- Modify: `backend/app/models/entities.py`
- Modify: `backend/app/api/videos.py`
- Create: `backend/alembic/versions/20260621_0003_active_task_uniqueness.py`
- Test: `backend/tests/test_task_api.py`

- [ ] Add an API test that submits two different idempotency keys for one media row and expects the same active `task_id`.
- [ ] Run the focused test and confirm it fails by creating two tasks.
- [ ] Add an active-status query before insertion and recover from `IntegrityError` by rolling back and returning the existing active task.
- [ ] Define the PostgreSQL partial unique index in SQLAlchemy metadata and Alembic for active task states.
- [ ] Run task API tests and confirm they pass.

### Task 3: Implement token-safe renewable Redis leases

**Files:**
- Create: `backend/app/integrations/execution_lease.py`
- Modify: `backend/app/core/config.py`
- Test: `backend/tests/test_execution_lease.py`

- [ ] Add tests for exclusive acquisition, token-safe release, renewal, lease loss, and repeated renewal beyond the original TTL using an in-memory Redis-compatible fake.
- [ ] Run the focused test and confirm imports fail because the lease module does not exist.
- [ ] Implement `RedisExecutionLease`, Lua compare-and-renew/release scripts, a renewal thread, `ContentExecutionBusy`, and `LeaseLost`.
- [ ] Add configurable lease TTL and renewal interval settings.
- [ ] Run the lease tests and confirm they pass.

### Task 4: Guard expensive pipeline stages by content hash

**Files:**
- Modify: `backend/app/services/media_pipeline.py`
- Modify: `backend/app/services/production_pipeline.py`
- Modify: `backend/app/worker/tasks.py`
- Test: `backend/tests/test_content_deduplication.py`
- Test: `backend/tests/test_media_pipeline.py`

- [ ] Add a concurrency-oriented pipeline test where two different media rows share SHA-256 and only the lease owner invokes `extract`.
- [ ] Add a race-closing test where a canonical READY row appears immediately after lease acquisition and the duplicate reuses its artifacts.
- [ ] Run focused tests and confirm both fail.
- [ ] Split PROBING from guarded expensive stages, acquire the lease after SHA-256 is known, recheck canonical content inside the lease, and raise `ContentExecutionBusy` when occupied.
- [ ] Include `ContentExecutionBusy` and `LeaseLost` in Celery autoretry.
- [ ] Re-run content deduplication and pipeline tests.

### Task 5: Guarantee temporary workspace cleanup and stage re-entry

**Files:**
- Modify: `backend/app/services/production_pipeline.py`
- Modify: `backend/app/services/media_pipeline.py`
- Test: `backend/tests/test_content_deduplication.py`
- Test: `backend/tests/test_media_pipeline.py`

- [ ] Add tests proving workspaces are deleted after success and after a handler exception.
- [ ] Run focused tests and confirm local directories remain.
- [ ] Add a handler cleanup protocol and invoke it from `MediaPipeline.run` in `finally`.
- [ ] Keep persistent-stage checks for transcript, vector upsert and summary so redelivery resumes safely.
- [ ] Re-run focused tests.

### Task 6: Rebuild the frontend as an audio/video workspace

**Files:**
- Modify: `client/src/App.tsx`
- Modify: `client/src/api.ts`
- Modify: `client/src/styles.css`
- Modify: `client/src/App.test.tsx`
- Modify: `client/index.html`

- [ ] Add UI tests for the AudiVise title, `audio/*,video/*` file input, audio player rendering, and video player rendering.
- [ ] Run `npm test -- --run` and confirm the tests fail against the video-only UI.
- [ ] Replace corrupted Chinese strings, switch user-facing terminology to media/audio-video, render `<audio>` or `<video>` from content type, and preserve timestamp seeking through a shared media ref.
- [ ] Rename frontend API helpers/types to media terminology where it does not break backend routes.
- [ ] Update responsive styles for the audio state.
- [ ] Run frontend tests and build.

### Task 7: Rebrand documentation and service metadata

**Files:**
- Modify: `README.md`
- Modify: `client/README.md`
- Modify: `backend/app/__init__.py`
- Modify: `backend/app/main.py`
- Modify: `backend/app/core/config.py`
- Modify: `backend/pyproject.toml`
- Modify: `backend/tests/test_health.py`

- [ ] Update the health test to expect `AudiVise API` and run it to confirm failure.
- [ ] Replace all previous public branding with AudiVise and rewrite corrupted README text as valid UTF-8.
- [ ] Document audio/video scope, ASR configuration, active-task index, renewable leases, crash redelivery and cleanup.
- [ ] Run health tests and search README/public metadata for stale branding.

### Task 8: Full verification

**Files:**
- Verify: `backend/`
- Verify: `client/`
- Verify: `docker-compose.yml`

- [ ] Run `python -m pytest -q`.
- [ ] Run `python -m ruff check app tests`.
- [ ] Run `python -m mypy app`.
- [ ] Run `npm test -- --run`.
- [ ] Run `npm run build`.
- [ ] Run Alembic upgrade against PostgreSQL through Docker Compose.
- [ ] Run the concurrent submission test repeatedly and verify only one expensive execution is counted.
- [ ] Inspect the final diff/search results against every requirement in the design.
