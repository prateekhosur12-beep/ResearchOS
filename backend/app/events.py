"""In-process event bus powering the live workflow stream (SSE).

Events are buffered per run so a browser that connects late still receives the
history of what actually happened, and never sees invented progress.
"""

from __future__ import annotations

import asyncio
import time
from collections import defaultdict
from typing import Any


class EventBus:
    def __init__(self, buffer_size: int = 400) -> None:
        self._subscribers: dict[str, list[asyncio.Queue]] = defaultdict(list)
        self._buffer: dict[str, list[dict[str, Any]]] = defaultdict(list)
        self._finished: dict[str, bool] = defaultdict(bool)
        self._buffer_size = buffer_size
        self._lock = asyncio.Lock()
        self._seq: dict[str, int] = defaultdict(int)

    def subscribe(self, run_id: str) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue(maxsize=1000)
        self._subscribers[run_id].append(queue)
        return queue

    def unsubscribe(self, run_id: str, queue: asyncio.Queue) -> None:
        if queue in self._subscribers.get(run_id, []):
            self._subscribers[run_id].remove(queue)

    async def publish(self, run_id: str, event: dict[str, Any]) -> None:
        self._seq[run_id] += 1
        payload = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "seq": self._seq[run_id],
            **event,
        }
        async with self._lock:
            buf = self._buffer[run_id]
            buf.append(payload)
            if len(buf) > self._buffer_size:
                del buf[: len(buf) - self._buffer_size]
            if payload.get("type") in ("run_finished", "run_failed", "run_cancelled"):
                self._finished[run_id] = True
            queues = list(self._subscribers.get(run_id, []))
        for q in queues:
            try:
                q.put_nowait(payload)
            except asyncio.QueueFull:  # slow consumer: drop rather than block the run
                pass

    def history(self, run_id: str) -> list[dict[str, Any]]:
        return list(self._buffer.get(run_id, []))

    def is_finished(self, run_id: str) -> bool:
        return self._finished.get(run_id, False)

    def clear(self, run_id: str) -> None:
        self._buffer.pop(run_id, None)
        self._subscribers.pop(run_id, None)
        self._finished.pop(run_id, None)


bus = EventBus()
