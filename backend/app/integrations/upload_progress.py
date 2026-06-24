import json
from collections.abc import Mapping, Sequence
from functools import lru_cache
from typing import Protocol

from redis import Redis

from app.core.config import get_settings


class UploadProgressCache(Protocol):
    def store_parts(
        self,
        upload_id: str,
        parts: Sequence[Mapping[str, object]],
    ) -> None: ...

    def delete(self, upload_id: str) -> None: ...


class NullUploadProgressCache:
    def store_parts(
        self,
        upload_id: str,
        parts: Sequence[Mapping[str, object]],
    ) -> None:
        return None

    def delete(self, upload_id: str) -> None:
        return None


class RedisUploadProgressCache:
    def __init__(self) -> None:
        self.client = Redis.from_url(get_settings().redis_url, decode_responses=True)

    def store_parts(
        self,
        upload_id: str,
        parts: Sequence[Mapping[str, object]],
    ) -> None:
        self.client.setex(
            f"upload:parts:{upload_id}",
            24 * 60 * 60,
            json.dumps(list(parts), ensure_ascii=False),
        )

    def delete(self, upload_id: str) -> None:
        self.client.delete(f"upload:parts:{upload_id}")


@lru_cache
def get_upload_progress_cache() -> UploadProgressCache:
    if get_settings().upload_progress_cache_enabled:
        return RedisUploadProgressCache()
    return NullUploadProgressCache()
