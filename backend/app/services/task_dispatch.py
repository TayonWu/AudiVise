from typing import Protocol

from app.core.config import get_settings


class TaskDispatcher(Protocol):
    def dispatch(self, task_id: str) -> None: ...


class NullTaskDispatcher:
    def dispatch(self, task_id: str) -> None:
        return None


class CeleryTaskDispatcher:
    def dispatch(self, task_id: str) -> None:
        from app.worker.tasks import process_video

        process_video.delay(task_id)


def get_task_dispatcher() -> TaskDispatcher:
    if get_settings().dispatch_tasks:
        return CeleryTaskDispatcher()
    return NullTaskDispatcher()

