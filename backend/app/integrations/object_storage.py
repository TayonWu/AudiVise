from __future__ import annotations

from datetime import timedelta
from functools import lru_cache
from typing import Any, Protocol
from urllib.parse import urlencode

from minio import Minio
from minio.datatypes import Part
from minio.error import S3Error

from app.core.config import get_settings


class ObjectStorage(Protocol):
    def ensure_bucket(self) -> None: ...

    def create_multipart_upload(self, object_key: str, content_type: str) -> str: ...

    def presign_part(self, object_key: str, upload_id: str, part_number: int) -> str: ...

    def complete_multipart_upload(
        self, object_key: str, upload_id: str, parts: list[tuple[int, str]]
    ) -> None: ...

    def presign_get(self, object_key: str) -> str: ...

    def download_file(self, object_key: str, destination: str) -> None: ...

    def upload_file(self, object_key: str, source: str, content_type: str) -> None: ...

    def object_exists(self, object_key: str) -> bool: ...


class MemoryObjectStorage:
    def ensure_bucket(self) -> None:
        return None

    def create_multipart_upload(self, object_key: str, content_type: str) -> str:
        return f"memory-upload:{object_key}"

    def presign_part(self, object_key: str, upload_id: str, part_number: int) -> str:
        query = urlencode({"uploadId": upload_id, "partNumber": part_number})
        return f"memory://{object_key}?{query}"

    def complete_multipart_upload(
        self, object_key: str, upload_id: str, parts: list[tuple[int, str]]
    ) -> None:
        return None

    def presign_get(self, object_key: str) -> str:
        return f"memory://{object_key}"

    def download_file(self, object_key: str, destination: str) -> None:
        raise FileNotFoundError(f"memory object {object_key} has no file payload")

    def upload_file(self, object_key: str, source: str, content_type: str) -> None:
        return None

    def object_exists(self, object_key: str) -> bool:
        return False


class MinioObjectStorage:
    def __init__(
        self,
        *,
        internal_client: Any | None = None,
        public_client: Any | None = None,
        bucket: str | None = None,
    ) -> None:
        settings = get_settings()
        self.bucket = bucket or settings.minio_bucket
        self.internal_client = internal_client or Minio(
            settings.minio_endpoint,
            access_key=settings.minio_access_key,
            secret_key=settings.minio_secret_key,
            secure=settings.minio_secure,
            region=settings.minio_region,
        )
        self.public_client = public_client or Minio(
            settings.minio_public_endpoint or settings.minio_endpoint,
            access_key=settings.minio_access_key,
            secret_key=settings.minio_secret_key,
            secure=(
                settings.minio_public_secure
                if settings.minio_public_endpoint
                else settings.minio_secure
            ),
            region=settings.minio_region,
        )

    def ensure_bucket(self) -> None:
        if not self.internal_client.bucket_exists(self.bucket):
            self.internal_client.make_bucket(self.bucket)

    def create_multipart_upload(self, object_key: str, content_type: str) -> str:
        self.ensure_bucket()
        return self.internal_client._create_multipart_upload(  # noqa: SLF001
            self.bucket,
            object_key,
            headers={"Content-Type": content_type},
        )

    def presign_part(self, object_key: str, upload_id: str, part_number: int) -> str:
        return self.public_client.get_presigned_url(
            "PUT",
            self.bucket,
            object_key,
            expires=timedelta(hours=1),
            extra_query_params={
                "uploadId": upload_id,
                "partNumber": str(part_number),
            },
        )

    def complete_multipart_upload(
        self, object_key: str, upload_id: str, parts: list[tuple[int, str]]
    ) -> None:
        self.internal_client._complete_multipart_upload(  # noqa: SLF001
            self.bucket,
            object_key,
            upload_id,
            [Part(part_number, etag) for part_number, etag in parts],
        )

    def presign_get(self, object_key: str) -> str:
        return self.public_client.presigned_get_object(
            self.bucket,
            object_key,
            expires=timedelta(hours=1),
        )

    def download_file(self, object_key: str, destination: str) -> None:
        self.internal_client.fget_object(self.bucket, object_key, destination)

    def upload_file(self, object_key: str, source: str, content_type: str) -> None:
        self.ensure_bucket()
        self.internal_client.fput_object(
            self.bucket,
            object_key,
            source,
            content_type=content_type,
        )

    def object_exists(self, object_key: str) -> bool:
        try:
            self.internal_client.stat_object(self.bucket, object_key)
        except S3Error as exc:
            if exc.code in {"NoSuchKey", "NoSuchObject", "NotFound"}:
                return False
            raise
        return True


@lru_cache
def get_object_storage() -> ObjectStorage:
    if get_settings().storage_backend.lower() == "minio":
        return MinioObjectStorage()
    return MemoryObjectStorage()
