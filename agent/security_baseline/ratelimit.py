"""L1 接口/工具调用限流：进程内线程安全令牌桶。

对应风险：大模型接口未鉴权限流被刷量、Agent 工具链被循环调用放大破坏面。
分布式部署时应替换为 Redis 实现，接口契约保持 acquire() 不变。
"""

from __future__ import annotations

import threading
import time


class TokenBucket:
    """标准令牌桶：capacity 容量上限，按 refill_per_second 持续回填。"""

    def __init__(self, capacity: int, refill_per_second: float, *, clock=None) -> None:
        self.capacity = float(capacity)
        self.refill = float(refill_per_second)
        self._tokens = float(capacity)
        self._clock = clock or time.monotonic
        self._updated = self._clock()
        self._lock = threading.Lock()

    def acquire(self, tokens: float = 1.0) -> bool:
        with self._lock:
            now = self._clock()
            self._tokens = min(
                self.capacity,
                self._tokens + (now - self._updated) * self.refill,
            )
            self._updated = now
            if self._tokens >= tokens:
                self._tokens -= tokens
                return True
            return False


class RateLimitManager:
    """按 identity + scope 维度管理令牌桶。"""

    def __init__(self, config, *, clock=None) -> None:
        self._config = config
        self._clock = clock or time.monotonic
        self._buckets: dict[tuple[str, str], TokenBucket] = {}
        self._lock = threading.Lock()

    def acquire(self, identity: str, scope: str) -> bool:
        key = (identity, scope)
        with self._lock:
            bucket = self._buckets.get(key)
            if bucket is None:
                capacity, refill = self._config.quota(scope)
                bucket = TokenBucket(capacity, refill, clock=self._clock)
                self._buckets[key] = bucket
        return bucket.acquire()
