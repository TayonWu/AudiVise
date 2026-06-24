from __future__ import annotations

import threading
import time
from typing import Any

import pytest

from app.integrations.execution_lease import (
    ContentExecutionBusy,
    LeaseLost,
    RedisExecutionLeaseManager,
)


class FakeRedis:
    def __init__(self) -> None:
        self.values: dict[str, tuple[str, float]] = {}
        self.lock = threading.Lock()

    def set(
        self,
        key: str,
        value: str,
        *,
        nx: bool,
        px: int,
    ) -> bool | None:
        with self.lock:
            self._expire(key)
            if nx and key in self.values:
                return None
            self.values[key] = (value, time.monotonic() + px / 1000)
            return True

    def eval(self, script: str, numkeys: int, key: str, token: str, *args: Any) -> int:
        del numkeys
        with self.lock:
            self._expire(key)
            current = self.values.get(key)
            if current is None or current[0] != token:
                return 0
            if args:
                self.values[key] = (token, time.monotonic() + int(args[0]) / 1000)
            else:
                del self.values[key]
            return 1

    def replace_token(self, key: str, token: str, ttl_seconds: float = 1) -> None:
        with self.lock:
            self.values[key] = (token, time.monotonic() + ttl_seconds)

    def _expire(self, key: str) -> None:
        current = self.values.get(key)
        if current is not None and current[1] <= time.monotonic():
            del self.values[key]


def test_lease_is_exclusive_and_release_is_token_safe() -> None:
    redis = FakeRedis()
    first = RedisExecutionLeaseManager(redis, ttl_seconds=0.2, renew_interval=0.05)
    second = RedisExecutionLeaseManager(redis, ttl_seconds=0.2, renew_interval=0.05)

    with first.hold("same-content"):
        with pytest.raises(ContentExecutionBusy):
            with second.hold("same-content"):
                pass

    with second.hold("same-content"):
        pass


def test_lease_renews_beyond_original_ttl() -> None:
    redis = FakeRedis()
    first = RedisExecutionLeaseManager(redis, ttl_seconds=0.08, renew_interval=0.02)
    second = RedisExecutionLeaseManager(redis, ttl_seconds=0.08, renew_interval=0.02)

    with first.hold("long-transcode") as lease:
        time.sleep(0.16)
        lease.assert_owned()
        with pytest.raises(ContentExecutionBusy):
            with second.hold("long-transcode"):
                pass


def test_lease_detects_token_replacement_and_does_not_delete_new_owner() -> None:
    redis = FakeRedis()
    manager = RedisExecutionLeaseManager(redis, ttl_seconds=0.2, renew_interval=0.05)

    with pytest.raises(LeaseLost):
        with manager.hold("crashed-worker") as lease:
            redis.replace_token(lease.key, "new-worker-token")
            time.sleep(0.07)
            lease.assert_owned()

    assert redis.values["audivise:media:execution:crashed-worker"][0] == "new-worker-token"
