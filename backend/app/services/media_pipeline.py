from typing import Protocol

from sqlalchemy.orm import Session

from app.integrations.execution_lease import (
    ContentExecutionBusy,
    LeaseLost,
    NoopExecutionLeaseManager,
)
from app.models import AnalysisTask, TaskStatus, Video, VideoStatus
from app.services.task_state import ensure_transition


class PipelineHandlers(Protocol):
    def probe(self, video: Video) -> None: ...

    def extract(self, video: Video) -> None: ...

    def transcribe(self, video: Video) -> None: ...

    def index(self, video: Video) -> None: ...

    def summarize(self, video: Video) -> None: ...

    def resolve_ready_duplicate(self, video: Video) -> None: ...

    def cleanup(self, video: Video) -> None: ...


_STAGES = (
    (TaskStatus.PROBING, 10, "probe"),
    (TaskStatus.EXTRACTING, 25, "extract"),
    (TaskStatus.TRANSCRIBING, 45, "transcribe"),
    (TaskStatus.INDEXING, 70, "index"),
    (TaskStatus.SUMMARIZING, 90, "summarize"),
)


class MediaPipeline:
    def __init__(
        self,
        db: Session,
        handlers: PipelineHandlers,
        *,
        lease_manager: object | None = None,
    ) -> None:
        self.db = db
        self.handlers = handlers
        self.lease_manager = lease_manager or NoopExecutionLeaseManager()

    def run(self, task_id: str) -> AnalysisTask:
        task = self.db.get(AnalysisTask, task_id)
        if task is None:
            raise LookupError(f"analysis task {task_id} does not exist")
        if task.status in {TaskStatus.SUCCEEDED, TaskStatus.CANCELLED}:
            return task
        if task.status is TaskStatus.FAILED:
            self._restore_failed_stage(task)

        task.video.status = VideoStatus.PROCESSING
        self.db.commit()

        try:
            start_index = self._start_index(task.status)
            if start_index == 0:
                self._run_stage(task, _STAGES[0])
                start_index = 1

            content_key = task.video.sha256 or task.video.id
            with self.lease_manager.hold(content_key) as lease:  # type: ignore[attr-defined]
                resolver = getattr(self.handlers, "resolve_ready_duplicate", None)
                if resolver is not None:
                    resolver(task.video)
                for index in range(start_index, len(_STAGES)):
                    lease.assert_owned()
                    self._run_stage(task, _STAGES[index])
                lease.assert_owned()

            task.status = ensure_transition(task.status, TaskStatus.SUCCEEDED)
            task.current_stage = TaskStatus.SUCCEEDED.value
            task.progress = 100
            task.video.status = VideoStatus.READY
            task.error_code = None
            task.error_message = None
            self.db.commit()
            return task
        except (ContentExecutionBusy, LeaseLost) as exc:
            task.error_code = type(exc).__name__
            task.error_message = str(exc)
            self.db.commit()
            raise
        except Exception as exc:
            if task.status not in {
                TaskStatus.SUCCEEDED,
                TaskStatus.FAILED,
                TaskStatus.CANCELLED,
            }:
                task.status = ensure_transition(task.status, TaskStatus.FAILED)
            task.video.status = VideoStatus.FAILED
            task.error_code = type(exc).__name__
            task.error_message = str(exc)
            self.db.commit()
            raise
        finally:
            cleanup = getattr(self.handlers, "cleanup", None)
            if cleanup is not None:
                cleanup(task.video)

    def _run_stage(
        self,
        task: AnalysisTask,
        stage_definition: tuple[TaskStatus, int, str],
    ) -> None:
        stage, progress, handler_name = stage_definition
        if task.status is not stage:
            task.status = ensure_transition(task.status, stage)
        task.current_stage = stage.value
        task.progress = progress
        task.attempts += 1
        self.db.commit()

        handler = getattr(self.handlers, handler_name)
        handler(task.video)

    @staticmethod
    def _start_index(status: TaskStatus) -> int:
        if status is TaskStatus.PENDING:
            return 0
        for index, (stage, _, _) in enumerate(_STAGES):
            if stage is status:
                return index
        if status is TaskStatus.FAILED:
            raise ValueError("failed tasks require an explicit retry transition")
        return len(_STAGES)

    def _restore_failed_stage(self, task: AnalysisTask) -> None:
        try:
            failed_stage = TaskStatus(task.current_stage or "")
        except ValueError as exc:
            raise ValueError("failed task does not contain a resumable stage") from exc
        if failed_stage not in {stage for stage, _, _ in _STAGES}:
            raise ValueError("failed task does not contain a resumable stage")
        task.status = failed_stage
        task.error_code = None
        task.error_message = None
        self.db.commit()
