"""按聊天流计的发卡片冷却（命令与工具 send_card 共用）。"""

from __future__ import annotations

import math
import time
from collections.abc import Callable


class Cooldown:
    def __init__(self, seconds: int, clock: Callable[[], float] = time.monotonic) -> None:
        self._seconds = max(0, int(seconds))
        self._clock = clock
        self._last: dict[str, float] = {}

    def set_seconds(self, seconds: int) -> None:
        self._seconds = max(0, int(seconds))

    def hit(self, key: str) -> int:
        """冷却中返回剩余秒数（向上取整，至少 1）；否则记录本次并返回 0。"""

        if self._seconds <= 0:
            return 0
        now = self._clock()
        last = self._last.get(key)
        if last is not None and now - last < self._seconds:
            return max(1, math.ceil(self._seconds - (now - last)))
        self._last[key] = now
        return 0
