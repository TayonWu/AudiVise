from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field

import pytest
from sqlalchemy.orm import Session

from app.integrations.execution_lease import ContentExecutionBusy, NoopExecutionLease
from app.models import AnalysisTask, TaskStatus, Video
from app.services.media_pipeline import MediaPipeline, PipelineHandlers


@dataclass
class RecordingHandlers(PipelineHandlers):
    calls: list[str] = field(default_factory=list)
    cleaned: list[str] = field(default_factory=list)

    def probe(self, video: Video) -> None:
        self.calls.append("probe")
        video.sha256 = video.sha256 or "a" * 64

    def extract(self, video: Video) -> None:
        self.calls.append("extract")

    def transcribe(self, video: Video) -> None:
        self.calls.append("transcribe")

    def index(self, video: Video) -> None:
        self.calls.append("index")

    def summarize(self, video: Video) -> None:
        self.calls.append("summarize")

    def cleanup(self, video: Video) -> None:
        self.cleaned.append(video.id)

    def resolve_ready_duplicate(self, video: Video) -> None:
        return


class BusyLeaseManager:
    @contextmanager
    def hold(self, content_hash: str) -> Iterator[NoopExecutionLease]:
        raise ContentExecutionBusy(content_hash)
        yield NoopExecutionLease()


def test_pipeline_runs_stages_and_persists_success(db_session: Session) -> None:
    video = Video(
        filename="pipeline.mp4",
        content_type="video/mp4",
        size_bytes=10,
        object_key="videos/pipeline.mp4",
    )
    task = AnalysisTask(video=video, idempotency_key="pipeline-1")
    db_session.add_all([video, task])
    db_session.commit()
    handlers = RecordingHandlers()

    MediaPipeline(db_session, handlers).run(task.id)

    db_session.refresh(task)
    assert handlers.calls == ["probe", "extract", "transcribe", "index", "summarize"]
    assert task.status is TaskStatus.SUCCEEDED
    assert task.progress == 100
    assert handlers.cleaned == [video.id]


def test_pipeline_resumes_from_current_stage(db_session: Session) -> None:
    video = Video(
        filename="resume.mp4",
        content_type="video/mp4",
        size_bytes=10,
        object_key="videos/resume.mp4",
    )
    task = AnalysisTask(
        video=video,
        idempotency_key="pipeline-2",
        status=TaskStatus.TRANSCRIBING,
        progress=40,
    )
    db_session.add_all([video, task])
    db_session.commit()
    handlers = RecordingHandlers()

    MediaPipeline(db_session, handlers).run(task.id)

    assert handlers.calls == ["transcribe", "index", "summarize"]


@dataclass
class FailTranscriptionOnce(RecordingHandlers):
    failed: bool = False

    def transcribe(self, video: Video) -> None:
        self.calls.append("transcribe")
        if not self.failed:
            self.failed = True
            raise TimeoutError("temporary ASR timeout")


def test_failed_task_retries_from_the_failed_stage(db_session: Session) -> None:
    video = Video(
        filename="retry.mp4",
        content_type="video/mp4",
        size_bytes=10,
        object_key="videos/retry.mp4",
    )
    task = AnalysisTask(video=video, idempotency_key="pipeline-retry")
    db_session.add_all([video, task])
    db_session.commit()
    handlers = FailTranscriptionOnce()
    pipeline = MediaPipeline(db_session, handlers)

    with pytest.raises(TimeoutError):
        pipeline.run(task.id)

    db_session.refresh(task)
    assert task.status is TaskStatus.FAILED
    assert task.current_stage == TaskStatus.TRANSCRIBING.value

    pipeline.run(task.id)

    db_session.refresh(task)
    assert handlers.calls == [
        "probe",
        "extract",
        "transcribe",
        "transcribe",
        "index",
        "summarize",
    ]
    assert task.status is TaskStatus.SUCCEEDED
    assert handlers.cleaned == [video.id, video.id]


def test_busy_content_lease_blocks_expensive_stages_without_failing_task(
    db_session: Session,
) -> None:
    video = Video(
        filename="same-content.mp4",
        content_type="video/mp4",
        size_bytes=10,
        object_key="videos/same-content.mp4",
    )
    task = AnalysisTask(video=video, idempotency_key="content-lock")
    db_session.add_all([video, task])
    db_session.commit()
    handlers = RecordingHandlers()

    with pytest.raises(ContentExecutionBusy):
        MediaPipeline(db_session, handlers, lease_manager=BusyLeaseManager()).run(task.id)

    db_session.refresh(task)
    assert handlers.calls == ["probe"]
    assert handlers.cleaned == [video.id]
    assert task.status is TaskStatus.PROBING
    assert task.error_code == "ContentExecutionBusy"


def test_cleanup_runs_when_pipeline_handler_fails(db_session: Session) -> None:
    video = Video(
        filename="cleanup.mp4",
        content_type="video/mp4",
        size_bytes=10,
        object_key="videos/cleanup.mp4",
    )
    task = AnalysisTask(video=video, idempotency_key="cleanup")
    db_session.add_all([video, task])
    db_session.commit()
    handlers = FailTranscriptionOnce()

    with pytest.raises(TimeoutError):
        MediaPipeline(db_session, handlers).run(task.id)

    assert handlers.cleaned == [video.id]
