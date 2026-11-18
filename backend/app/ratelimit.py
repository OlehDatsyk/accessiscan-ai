"""Small in-process sliding-window rate limiter (login / registration throttling).

Per-user scan and AI limits are enforced from database records instead (see scans and ai routers), so
they hold across multiple API instances. This in-memory limiter is per process; document-level note in
SECURITY.md.
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict, deque


class SlidingWindowLimiter:
    def __init__(self, limit: int, window_seconds: float) -> None:
        self.limit = limit
        self.window = window_seconds
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def hit(self, key: str) -> bool:
        """Record an attempt. Returns False when the key is over its limit."""
        now = time.monotonic()
        with self._lock:
            q = self._hits[key]
            while q and now - q[0] > self.window:
                q.popleft()
            if len(q) >= self.limit:
                return False
            q.append(now)
            if len(self._hits) > 50_000:  # bound memory under abuse
                for k in list(self._hits)[:10_000]:
                    if not self._hits[k] or now - self._hits[k][-1] > self.window:
                        del self._hits[k]
            return True

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()
