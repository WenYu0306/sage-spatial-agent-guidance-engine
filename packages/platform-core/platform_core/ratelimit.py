"""极简内存滑动窗口限流（P2 安全批，审计 S-5/S-6/S-8）。

单进程 demo 口径：多副本部署需换 Redis 实现（接口不变，记 DECISIONS）。
键约定由调用方决定（IP / anonymous_id / 复合键）。
"""

from __future__ import annotations

import time
from collections import deque


class SlidingWindow:
    """allow(key) → bool：窗口内第 max_events+1 次起拒绝。线程安全依赖 GIL 原子性即可。"""

    def __init__(self, max_events: int, window_s: float):
        self.max_events = max_events
        self.window_s = window_s
        self._hits: dict[str, deque[float]] = {}

    def allow(self, key: str, now: float | None = None) -> bool:
        now = time.monotonic() if now is None else now
        q = self._hits.setdefault(key, deque())
        while q and now - q[0] > self.window_s:
            q.popleft()
        if len(q) >= self.max_events:
            return False
        q.append(now)
        return True
