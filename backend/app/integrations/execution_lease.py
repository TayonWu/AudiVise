from __future__ import annotations

import threading
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any, Protocol
from uuid import uuid4

from redis import Redis

from app.core.config import get_settings

_RENEW_SCRIPT = """
if redis.call("get", KEYS[1]) == ARGV[1] then
  return redis.call("pexpire", KEYS[1], ARGV[2])
end
return 0
"""

_RELEASE_SCRIPT = """
if redis.call("get", KEYS[1]) == ARGV[1] then
  return redis.call("del", KEYS[1])
end
return 0
"""


class ContentExecutionBusy(RuntimeError):
    """Raised when another worker owns the content execution lease."""


class LeaseLost(RuntimeError):
    """Raised when a worker can no longer prove ownership of its lease."""


class RedisClient(Protocol):
    def set(
        self,
        name: str,
        value: str,
        *,
        nx: bool,
        px: int,
    ) -> Any: ...

    def eval(self, script: str, numkeys: int, *keys_and_args: Any) -> Any: ...


class ExecutionLease:
    def __init__(
        self,
        client: RedisClient,
        key: str,
        token: str,
        ttl_ms: int,
        renew_interval: float,
    ) -> None:
        self.client = client
        self.key = key
        self.token = token
        self.ttl_ms = ttl_ms
        self.renew_interval = renew_interval
        self._stop = threading.Event()
        self._lost = threading.Event()
        self._thread = threading.Thread(
            target=self._renew_loop,
            name=f"lease-renew-{token[:8]}",
            daemon=True,
        )

    def start(self) -> None:
        self._thread.start()

    def assert_owned(self) -> None:
        if self._lost.is_set():
            raise LeaseLost(f"execution lease lost for {self.key}")

    def close(self) -> None:
        self._stop.set()
        self._thread.join(timeout=max(self.renew_interval * 2, 0.1))
        self.client.eval(_RELEASE_SCRIPT, 1, self.key, self.token)

    def _renew_loop(self) -> None:
        while not self._stop.wait(self.renew_interval):
            try:
                renewed = self.client.eval(
                    _RENEW_SCRIPT,
                    1,
                    self.key,
                    self.token,
                    self.ttl_ms,
                )
            except Exception:
                self._lost.set()
                return
            if int(renewed or 0) != 1:
                self._lost.set()
                return


class RedisExecutionLeaseManager:
    def __init__(
        self,
        client: RedisClient,
        *,
        ttl_seconds: float,
        renew_interval: float,
        key_prefix: str = "audivise:media:execution",
    ) -> None:
        if ttl_seconds <= 0:
            raise ValueError("lease ttl must be positive")
        if renew_interval <= 0 or renew_interval >= ttl_seconds:
            raise ValueError("renew interval must be positive and shorter than ttl")
        self.client = client
        self.ttl_ms = max(1, round(ttl_seconds * 1000))
        self.renew_interval = renew_interval
        self.key_prefix = key_prefix

    @contextmanager
    def hold(self, content_hash: str) -> Iterator[ExecutionLease]:
        key = f"{self.key_prefix}:{content_hash}"
        token = str(uuid4())
        acquired = self.client.set(key, token, nx=True, px=self.ttl_ms)
        if not acquired:
            raise ContentExecutionBusy(f"content {content_hash} is already processing")
        lease = ExecutionLease(
            self.client,
            key,
            token,
            self.ttl_ms,
            self.renew_interval,
        )
        lease.start()
        try:
            yield lease
            lease.assert_owned()
        finally:
            lease.close()


class NoopExecutionLeaseManager:
    @contextmanager
    def hold(self, content_hash: str) -> Iterator[NoopExecutionLease]:
        del content_hash
        yield NoopExecutionLease()


class NoopExecutionLease:
    def assert_owned(self) -> None:
        return


def get_execution_lease_manager() -> RedisExecutionLeaseManager:
    settings = get_settings()
    client = Redis.from_url(settings.redis_url, decode_responses=True)
    return RedisExecutionLeaseManager(
        client,
        ttl_seconds=settings.execution_lease_ttl_seconds,
        renew_interval=settings.execution_lease_renew_interval_seconds,
    )
