from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.integrations.object_storage import ObjectStorage, get_object_storage
from app.models import AnalysisTask, TaskStatus, TranscriptChunk, Video
from app.schemas.summary import SummaryResponse
from app.schemas.tasks import TaskResponse
from app.schemas.videos import PlaybackResponse, TranscriptChunkResponse, VideoResponse
from app.services.task_dispatch import TaskDispatcher, get_task_dispatcher

router = APIRouter(prefix="/videos", tags=["videos"])

ACTIVE_TASK_STATUSES = {
    TaskStatus.PENDING,
    TaskStatus.PROBING,
    TaskStatus.EXTRACTING,
    TaskStatus.TRANSCRIBING,
    TaskStatus.INDEXING,
    TaskStatus.SUMMARIZING,
}


@router.get("", response_model=list[VideoResponse])
def list_videos(db: Session = Depends(get_db)) -> list[Video]:
    return list(db.scalars(select(Video).order_by(Video.created_at.desc())))


@router.get("/{video_id}", response_model=VideoResponse)
def get_video(video_id: str, db: Session = Depends(get_db)) -> Video:
    video = db.get(Video, video_id)
    if video is None:
        raise HTTPException(status_code=404, detail="video not found")
    return video


@router.get("/{video_id}/playback", response_model=PlaybackResponse)
def get_playback_url(
    video_id: str,
    db: Session = Depends(get_db),
    storage: ObjectStorage = Depends(get_object_storage),
) -> PlaybackResponse:
    video = db.get(Video, video_id)
    if video is None:
        raise HTTPException(status_code=404, detail="video not found")
    return PlaybackResponse(url=storage.presign_get(video.object_key))


@router.get("/{video_id}/summary", response_model=SummaryResponse)
def get_summary(video_id: str, db: Session = Depends(get_db)) -> SummaryResponse:
    video = db.get(Video, video_id)
    if video is None:
        raise HTTPException(status_code=404, detail="video not found")
    return SummaryResponse(video_id=video.id, summary=video.summary)


@router.get(
    "/{video_id}/transcript",
    response_model=list[TranscriptChunkResponse],
)
def list_transcript(
    video_id: str,
    db: Session = Depends(get_db),
) -> list[TranscriptChunkResponse]:
    if db.get(Video, video_id) is None:
        raise HTTPException(status_code=404, detail="video not found")
    chunks = db.scalars(
        select(TranscriptChunk)
        .where(TranscriptChunk.video_id == video_id)
        .order_by(TranscriptChunk.chunk_index)
    )
    return [
        TranscriptChunkResponse(
            chunk_id=chunk.id,
            chunk_index=chunk.chunk_index,
            start_ms=chunk.start_ms,
            end_ms=chunk.end_ms,
            text=chunk.text,
        )
        for chunk in chunks
    ]


@router.post(
    "/{video_id}/analysis",
    response_model=TaskResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def create_analysis(
    video_id: str,
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=1, max_length=255),
    db: Session = Depends(get_db),
    dispatcher: TaskDispatcher = Depends(get_task_dispatcher),
) -> TaskResponse:
    if db.get(Video, video_id) is None:
        raise HTTPException(status_code=404, detail="video not found")

    existing = db.scalar(
        select(AnalysisTask).where(
            AnalysisTask.video_id == video_id,
            AnalysisTask.idempotency_key == idempotency_key,
        )
    )
    if existing is not None:
        return _task_response(existing)

    active = _find_active_task(db, video_id)
    if active is not None:
        return _task_response(active)

    task = AnalysisTask(video_id=video_id, idempotency_key=idempotency_key)
    db.add(task)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        active = _find_active_task(db, video_id)
        if active is None:
            raise
        return _task_response(active)
    db.refresh(task)
    dispatcher.dispatch(task.id)
    return _task_response(task)


def _find_active_task(db: Session, video_id: str) -> AnalysisTask | None:
    return db.scalar(
        select(AnalysisTask)
        .where(
            AnalysisTask.video_id == video_id,
            AnalysisTask.status.in_(ACTIVE_TASK_STATUSES),
        )
        .order_by(AnalysisTask.created_at)
        .limit(1)
    )


def _task_response(task: AnalysisTask) -> TaskResponse:
    return TaskResponse(
        task_id=task.id,
        video_id=task.video_id,
        status=task.status,
        progress=task.progress,
        current_stage=task.current_stage,
        attempts=task.attempts,
        error_code=task.error_code,
        error_message=task.error_message,
        created_at=task.created_at,
    )
