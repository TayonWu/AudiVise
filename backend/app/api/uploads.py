import json
from datetime import UTC, datetime
from pathlib import PurePosixPath
from typing import TypedDict
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.integrations.object_storage import ObjectStorage, get_object_storage
from app.integrations.upload_progress import UploadProgressCache, get_upload_progress_cache
from app.models import UploadSession, UploadStatus, Video
from app.schemas.uploads import (
    UploadComplete,
    UploadCompleted,
    UploadCreate,
    UploadCreated,
    UploadPartConfirmed,
    UploadPartRequest,
    UploadPartResponse,
    UploadSessionResponse,
)

router = APIRouter(prefix="/uploads", tags=["uploads"])


class ConfirmedPartData(TypedDict):
    part_number: int
    etag: str


def _confirmed_parts(upload: UploadSession) -> list[ConfirmedPartData]:
    if not upload.completed_parts:
        return []
    value = json.loads(upload.completed_parts)
    if not isinstance(value, list):
        return []
    return [
        {
            "part_number": int(item["part_number"]),
            "etag": str(item["etag"]),
        }
        for item in value
        if isinstance(item, dict) and "part_number" in item and "etag" in item
    ]


@router.post("", response_model=UploadCreated, status_code=status.HTTP_201_CREATED)
def create_upload(
    payload: UploadCreate,
    db: Session = Depends(get_db),
    storage: ObjectStorage = Depends(get_object_storage),
) -> UploadCreated:
    upload_id = str(uuid4())
    safe_name = PurePosixPath(payload.filename).name
    date_prefix = datetime.now(UTC).strftime("%Y/%m/%d")
    object_key = f"videos/{date_prefix}/{upload_id}/{safe_name}"
    multipart_upload_id = storage.create_multipart_upload(object_key, payload.content_type)
    upload = UploadSession(
        id=upload_id,
        filename=safe_name,
        content_type=payload.content_type,
        size_bytes=payload.size_bytes,
        object_key=object_key,
        multipart_upload_id=multipart_upload_id,
    )
    db.add(upload)
    db.commit()
    return UploadCreated(id=upload.id, object_key=upload.object_key, status=upload.status)


@router.get("/{upload_id}", response_model=UploadSessionResponse)
def get_upload(upload_id: str, db: Session = Depends(get_db)) -> UploadSessionResponse:
    upload = db.get(UploadSession, upload_id)
    if upload is None:
        raise HTTPException(status_code=404, detail="upload session not found")
    return UploadSessionResponse(
        id=upload.id,
        filename=upload.filename,
        content_type=upload.content_type,
        size_bytes=upload.size_bytes,
        object_key=upload.object_key,
        status=upload.status,
        completed_parts=_confirmed_parts(upload),
        video_id=upload.video_id,
    )


@router.post("/{upload_id}/parts", response_model=UploadPartResponse)
def create_part_url(
    upload_id: str,
    payload: UploadPartRequest,
    db: Session = Depends(get_db),
    storage: ObjectStorage = Depends(get_object_storage),
) -> UploadPartResponse:
    upload = db.get(UploadSession, upload_id)
    if upload is None:
        raise HTTPException(status_code=404, detail="upload session not found")
    if upload.status is not UploadStatus.INITIATED or not upload.multipart_upload_id:
        raise HTTPException(status_code=409, detail="upload is not active")
    return UploadPartResponse(
        part_number=payload.part_number,
        url=storage.presign_part(
            upload.object_key,
            upload.multipart_upload_id,
            payload.part_number,
        ),
    )


@router.put("/{upload_id}/parts/{part_number}", response_model=UploadSessionResponse)
def confirm_uploaded_part(
    upload_id: str,
    part_number: int,
    payload: UploadPartConfirmed,
    db: Session = Depends(get_db),
    progress_cache: UploadProgressCache = Depends(get_upload_progress_cache),
) -> UploadSessionResponse:
    upload = db.get(UploadSession, upload_id)
    if upload is None:
        raise HTTPException(status_code=404, detail="upload session not found")
    if upload.status is not UploadStatus.INITIATED:
        raise HTTPException(status_code=409, detail="upload is not active")

    parts: dict[int, ConfirmedPartData] = {
        item["part_number"]: {
            "part_number": item["part_number"],
            "etag": str(item["etag"]),
        }
        for item in _confirmed_parts(upload)
    }
    parts[part_number] = {"part_number": part_number, "etag": payload.etag}
    upload.completed_parts = json.dumps(
        [parts[key] for key in sorted(parts)],
        ensure_ascii=False,
    )
    db.commit()
    progress_cache.store_parts(upload.id, _confirmed_parts(upload))
    return UploadSessionResponse(
        id=upload.id,
        filename=upload.filename,
        content_type=upload.content_type,
        size_bytes=upload.size_bytes,
        object_key=upload.object_key,
        status=upload.status,
        completed_parts=_confirmed_parts(upload),
        video_id=upload.video_id,
    )


@router.post("/{upload_id}/complete", response_model=UploadCompleted)
def complete_upload(
    upload_id: str,
    payload: UploadComplete,
    db: Session = Depends(get_db),
    storage: ObjectStorage = Depends(get_object_storage),
    progress_cache: UploadProgressCache = Depends(get_upload_progress_cache),
) -> UploadCompleted:
    upload = db.get(UploadSession, upload_id)
    if upload is None:
        raise HTTPException(status_code=404, detail="upload session not found")

    if upload.status is UploadStatus.COMPLETED and upload.video_id:
        return UploadCompleted(
            upload_id=upload.id,
            video_id=upload.video_id,
            status=upload.status,
        )

    storage.complete_multipart_upload(
        upload.object_key,
        upload.multipart_upload_id or "",
        [(part.part_number, part.etag) for part in payload.parts],
    )
    video = Video(
        filename=upload.filename,
        content_type=upload.content_type,
        size_bytes=upload.size_bytes,
        object_key=upload.object_key,
    )
    db.add(video)
    db.flush()
    upload.status = UploadStatus.COMPLETED
    upload.video_id = video.id
    upload.completed_parts = json.dumps(
        [part.model_dump() for part in payload.parts], ensure_ascii=False
    )
    db.commit()
    progress_cache.delete(upload.id)
    return UploadCompleted(
        upload_id=upload.id,
        video_id=video.id,
        status=upload.status,
    )
