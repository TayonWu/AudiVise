from typing import Any

from app.core.database import SessionLocal
from app.integrations.ai_provider import RetryableExternalError
from app.integrations.execution_lease import (
    ContentExecutionBusy,
    LeaseLost,
    get_execution_lease_manager,
)
from app.integrations.object_storage import get_object_storage
from app.services.media_pipeline import MediaPipeline
from app.services.production_pipeline import ProductionPipelineHandlers
from app.worker.celery_app import celery_app


@celery_app.task(  # type: ignore[untyped-decorator]
    bind=True,
    autoretry_for=(
        ConnectionError,
        TimeoutError,
        RetryableExternalError,
        LeaseLost,
    ),
    retry_backoff=True,
    retry_backoff_max=300,
    retry_jitter=True,
    max_retries=5,
    name="dovideo.process_video",
)
def process_video(self: Any, task_id: str) -> str:
    try:
        with SessionLocal() as db:
            handlers = ProductionPipelineHandlers(db, get_object_storage())
            MediaPipeline(
                db,
                handlers,
                lease_manager=get_execution_lease_manager(),
            ).run(task_id)
    except ContentExecutionBusy as exc:
        retry_number = int(getattr(self.request, "retries", 0))
        countdown = min(2 ** min(retry_number, 8), 300)
        raise self.retry(exc=exc, countdown=countdown, max_retries=1_000) from exc
    return task_id
