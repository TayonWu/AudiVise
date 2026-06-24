from pydantic import BaseModel, Field

from app.models.enums import UploadStatus


class UploadCreate(BaseModel):
    filename: str = Field(min_length=1, max_length=512)
    content_type: str = Field(pattern=r"^(audio|video)/")
    size_bytes: int = Field(gt=0)


class UploadCreated(BaseModel):
    id: str
    object_key: str
    status: UploadStatus


class UploadPartRequest(BaseModel):
    part_number: int = Field(ge=1, le=10_000)


class UploadPartResponse(BaseModel):
    part_number: int
    url: str


class UploadPartConfirmed(BaseModel):
    etag: str = Field(min_length=1, max_length=512)


class CompletedPart(BaseModel):
    part_number: int = Field(ge=1, le=10_000)
    etag: str = Field(min_length=1, max_length=512)


class UploadSessionResponse(BaseModel):
    id: str
    filename: str
    content_type: str
    size_bytes: int
    object_key: str
    status: UploadStatus
    completed_parts: list[CompletedPart]
    video_id: str | None


class UploadComplete(BaseModel):
    parts: list[CompletedPart] = Field(min_length=1)


class UploadCompleted(BaseModel):
    upload_id: str
    video_id: str
    status: UploadStatus
