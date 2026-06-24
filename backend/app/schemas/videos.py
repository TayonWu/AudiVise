from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.enums import VideoStatus


class VideoResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    filename: str
    content_type: str
    size_bytes: int
    object_key: str
    sha256: str | None
    duplicate_of_id: str | None
    status: VideoStatus
    duration_seconds: int | None
    summary: str | None
    created_at: datetime


class PlaybackResponse(BaseModel):
    url: str


class TranscriptChunkResponse(BaseModel):
    chunk_id: str
    chunk_index: int
    start_ms: int
    end_ms: int
    text: str
