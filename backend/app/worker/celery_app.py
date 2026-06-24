from celery import Celery

from app.core.config import get_settings

settings = get_settings()
celery_app = Celery(
    "dovideo",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["app.worker.tasks"],
)
celery_app.conf.update(
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    task_track_started=True,
    worker_prefetch_multiplier=1,
    task_soft_time_limit=3_500,
    task_time_limit=3_600,
)
