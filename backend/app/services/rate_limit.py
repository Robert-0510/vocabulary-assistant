"""进程内滑动窗口限流。

适用于本机单进程部署：不引入 Redis 等额外依赖。多进程/多实例部署时应换成
共享存储（Redis）实现，否则每个进程各算各的额度。
"""

import threading
import time
from collections import deque

from fastapi import HTTPException, Request

from app.config import config


class SlidingWindowLimiter:
    def __init__(self) -> None:
        self._events: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    def check(self, key: str, limit: int, window_seconds: float) -> float | None:
        """记录一次请求；超限时返回需要等待的秒数，否则返回 None。"""
        now = time.monotonic()
        with self._lock:
            events = self._events.setdefault(key, deque())
            cutoff = now - window_seconds
            while events and events[0] <= cutoff:
                events.popleft()
            if len(events) >= limit:
                return max(0.001, window_seconds - (now - events[0]))
            events.append(now)
            return None

    def reset(self) -> None:
        with self._lock:
            self._events.clear()


limiter = SlidingWindowLimiter()


def client_ip(request: Request) -> str:
    """仅使用直连地址；不信任可伪造的 X-Forwarded-For。"""
    return request.client.host if request.client else "unknown"


def enforce(key: str, limit: int, window_seconds: float) -> None:
    if not config.RATE_LIMIT_ENABLED:
        return
    retry_after = limiter.check(key, limit, window_seconds)
    if retry_after is not None:
        raise HTTPException(
            429,
            "操作过于频繁，请稍后再试",
            headers={"Retry-After": str(max(1, int(retry_after + 0.999)))},
        )
