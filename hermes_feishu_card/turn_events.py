"""Turn-local observer sequencing and bounded delivery workers.

Producer ownership remains in PluginRuntime. This boundary sequences accepted
plugin/patch events, closes the terminal barrier and bounds best-effort observer
work; a producer allowlist does not prove exclusive ownership of a turn.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import queue
import threading
from threading import Lock
from time import monotonic


@dataclass(frozen=True)
class ObserverEvent:
    sequence: int
    producer: str
    payload: dict[str, object]


class TurnEventCoordinator:
    """Allocate one turn-local sequence and bound asynchronous observer work."""

    _PRODUCERS = frozenset({"plugin", "patch", "legacy-patch"})
    _WORKER_POLL_SECONDS = 0.05
    _CLOSE_JOIN_SECONDS = 0.1

    def __init__(
        self,
        turn_id: str,
        *,
        max_pending: int = 64,
        deliver: Callable[[ObserverEvent], None] | None = None,
        start_worker: bool = True,
    ) -> None:
        if not self._is_nonblank(turn_id):
            raise ValueError("turn_id must be nonblank")
        if not isinstance(max_pending, int) or isinstance(max_pending, bool) or max_pending <= 0:
            raise ValueError("max_pending must be a positive integer")
        self.turn_id = turn_id
        self._next = 0
        self._barrier: int | None = None
        self._terminal_sequence: int | None = None
        self._closed = False
        self._lock = Lock()
        self._queue: queue.Queue[ObserverEvent] = queue.Queue(maxsize=max_pending)
        self._deliver = deliver or (lambda event: None)
        self._worker: threading.Thread | None = None
        if start_worker:
            self._worker = threading.Thread(
                target=self._deliver_observer_events,
                name="hfc-turn-observer",
                daemon=True,
            )
            self._worker.start()

    def next_sequence(self, producer: str) -> int:
        self._validate_producer(producer)
        with self._lock:
            value, self._next = self._next, self._next + 1
            return value

    def close_terminal_barrier(self) -> int:
        with self._lock:
            if self._barrier is None:
                self._barrier = self._next - 1
            return self._barrier

    def next_terminal_sequence(self) -> int:
        with self._lock:
            if self._barrier is None:
                raise ValueError("terminal barrier is not closed")
            if self._terminal_sequence is not None:
                return self._terminal_sequence
            value, self._next = self._next, self._next + 1
            self._terminal_sequence = value
            self._closed = True
            return value

    def event_id(self, kind: str, *, item_id: str = "", phase: str = "") -> str:
        if kind in {"started", "completed", "failed"}:
            return f"turn:{self.turn_id}:{kind}"
        if kind not in {"tool", "approval", "subagent"} or not self._is_nonblank(item_id):
            raise ValueError("invalid event identity")
        if phase not in {"started", "terminal"}:
            raise ValueError("invalid event phase")
        return f"{kind}:{self.turn_id}:{item_id}:{phase}"

    def submit_observer(
        self,
        payload: dict[str, object],
        *,
        producer: str,
        event_id_for_sequence: Callable[[int], str] | None = None,
    ) -> bool:
        self._validate_producer(producer)
        with self._lock:
            if self._closed or self._barrier is not None:
                return False
            sequence, self._next = self._next, self._next + 1
            event = ObserverEvent(sequence, producer, dict(payload, sequence=sequence))
            if event_id_for_sequence is not None:
                event.payload["event_id"] = event_id_for_sequence(sequence)
            try:
                self._queue.put_nowait(event)
            except queue.Full:
                return False
            return True

    def drain_before_terminal(self, timeout_seconds: float) -> None:
        deadline = monotonic() + max(0.0, timeout_seconds)
        with self._lock:
            self._closed = True
        while self._queue.unfinished_tasks and monotonic() < deadline:
            threading.Event().wait(0.001)

    def close(self) -> None:
        with self._lock:
            self._closed = True
            worker = self._worker
        if worker is not None and worker is not threading.current_thread():
            worker.join(timeout=self._CLOSE_JOIN_SECONDS)

    def _deliver_observer_events(self) -> None:
        while True:
            try:
                event = self._queue.get(timeout=self._WORKER_POLL_SECONDS)
            except queue.Empty:
                with self._lock:
                    if self._closed:
                        return
                continue
            try:
                self._deliver(event)
            except Exception:
                pass
            finally:
                self._queue.task_done()

    @staticmethod
    def _is_nonblank(value: object) -> bool:
        return isinstance(value, str) and bool(value.strip())

    @classmethod
    def _validate_producer(cls, producer: object) -> None:
        if producer not in cls._PRODUCERS:
            raise ValueError("unknown producer")


