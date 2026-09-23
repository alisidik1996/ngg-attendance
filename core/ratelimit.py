import threading
import time
from collections import deque


class SlidingWindowRateLimiter:
    def __init__(self):
        self._hits = {}
        self._lock = threading.Lock()

    def allow(self, key: str, max_hits: int, window_seconds: int) -> bool:
        now = time.monotonic()
        with self._lock:
            hits = self._hits.setdefault(key, deque())
            while hits and now - hits[0] > window_seconds:
                hits.popleft()
            if len(hits) >= max_hits:
                return False
            hits.append(now)
            return True

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


login_rate_limiter = SlidingWindowRateLimiter()
