"""Canonical turn carrier shared by hook and plugin adapters.

This is the original single registry and thread/task ownership gate. The weak
agent reference is only borrowed for display metrics; it grants no execution.
"""
from __future__ import annotations

import asyncio
from contextvars import ContextVar
from dataclasses import dataclass
import threading
from typing import Any
import weakref


@dataclass(frozen=True, repr=False)
class _CanonicalTurnFrame:
    turn_id: str
    token: object


@dataclass(frozen=True, repr=False)
class _CanonicalTurnEntry:
    token: object
    owner: object
    turn_id: str
    metrics_agent_ref: Any = None


_HFC_CANONICAL_TURN_CARRIER: ContextVar[tuple[_CanonicalTurnFrame, ...]] = (
    ContextVar("hfc_canonical_turn_carrier", default=())
)
_CANONICAL_TURN_REGISTRY_LIMIT = 1024
_CANONICAL_TURN_REGISTRY_LOCK = threading.RLock()
_CANONICAL_TURN_REGISTRY: dict[object, _CanonicalTurnEntry] = {}


def _canonical_turn_owner() -> tuple[threading.Thread, asyncio.Task[Any] | None]:
    try:
        task = asyncio.current_task()
    except RuntimeError:
        task = None
    return threading.current_thread(), task


def _same_canonical_turn_owner(left: object, right: object) -> bool:
    return left is right or (
        type(left) is tuple
        and len(left) == 2
        and type(right) is tuple
        and len(right) == 2
        and left[0] is right[0]
        and left[1] is right[1]
    )


def _live_canonical_turn_frames_locked(
    frames: object,
    owner: object,
) -> tuple[_CanonicalTurnFrame, ...] | None:
    if type(frames) is not tuple:
        return None
    live_frames: list[_CanonicalTurnFrame] = []
    for frame in frames:
        if type(frame) is not _CanonicalTurnFrame:
            return None
        entry = _CANONICAL_TURN_REGISTRY.get(frame.token)
        if entry is None:
            continue
        if (
            entry.token is not frame.token
            or not _same_canonical_turn_owner(entry.owner, owner)
            or entry.turn_id != frame.turn_id
        ):
            return None
        live_frames.append(frame)
    return tuple(live_frames)


def publish_canonical_turn_id(turn_id: object, *, metrics_agent: object = None) -> object | None:
    """Push an exact turn id into this thread/task's scoped carrier."""
    if type(turn_id) is not str or not turn_id.strip():
        return None
    owner = _canonical_turn_owner()
    token = object()
    try:
        metrics_ref = weakref.ref(metrics_agent) if metrics_agent is not None else None
    except TypeError:
        metrics_ref = None
    entry = _CanonicalTurnEntry(
        token=token, owner=owner, turn_id=turn_id, metrics_agent_ref=metrics_ref
    )
    with _CANONICAL_TURN_REGISTRY_LOCK:
        if len(_CANONICAL_TURN_REGISTRY) >= _CANONICAL_TURN_REGISTRY_LIMIT:
            return None
        frames = _live_canonical_turn_frames_locked(
            _HFC_CANONICAL_TURN_CARRIER.get(), owner
        )
        if frames is None:
            return None
        _CANONICAL_TURN_REGISTRY[token] = entry
        _HFC_CANONICAL_TURN_CARRIER.set(
            (*frames, _CanonicalTurnFrame(turn_id=turn_id, token=token))
        )
    return token


def clear_canonical_turn_id(token: object) -> bool:
    """Pop only the exact innermost frame owned by the current thread/task."""
    if type(token) is not object:
        return False
    owner = _canonical_turn_owner()
    with _CANONICAL_TURN_REGISTRY_LOCK:
        frames = _live_canonical_turn_frames_locked(
            _HFC_CANONICAL_TURN_CARRIER.get(), owner
        )
        if frames is None:
            return False
        if not frames or frames[-1].token is not token:
            _HFC_CANONICAL_TURN_CARRIER.set(frames)
            return False
        frame = frames[-1]
        entry = _CANONICAL_TURN_REGISTRY.get(token)
        if (
            entry is None
            or entry.token is not token
            or not _same_canonical_turn_owner(entry.owner, owner)
            or entry.turn_id != frame.turn_id
        ):
            return False
        del _CANONICAL_TURN_REGISTRY[token]
        _HFC_CANONICAL_TURN_CARRIER.set(frames[:-1])
    return True


def consume_canonical_turn_id(explicit_turn_id: object = None) -> str | None:
    """Return an exact explicit/carried id; mismatches are a hard fence."""
    if explicit_turn_id is not None and (
        type(explicit_turn_id) is not str or not explicit_turn_id.strip()
    ):
        return None
    owner = _canonical_turn_owner()
    carried: str | None = None
    with _CANONICAL_TURN_REGISTRY_LOCK:
        original_frames = _HFC_CANONICAL_TURN_CARRIER.get()
        frames = _live_canonical_turn_frames_locked(original_frames, owner)
        if frames is None:
            # Hermes copies ContextVars into tool worker threads.  Such a
            # worker must not gain implicit access to the turn, and it must
            # never be allowed to clear the owning frame.  It may, however,
            # present the exact explicit turn id carried by the still-live
            # opaque frame.  This keeps clarify/approval callbacks correlated
            # without weakening reset/clear revocation or accepting a guessed
            # id from an unrelated context.
            if explicit_turn_id is None or type(original_frames) is not tuple:
                return None
            copied_live: list[_CanonicalTurnFrame] = []
            for frame in original_frames:
                if type(frame) is not _CanonicalTurnFrame:
                    return None
                entry = _CANONICAL_TURN_REGISTRY.get(frame.token)
                if entry is None:
                    continue
                if entry.token is not frame.token or entry.turn_id != frame.turn_id:
                    return None
                copied_live.append(frame)
            if not copied_live or copied_live[-1].turn_id != explicit_turn_id:
                return None
            return explicit_turn_id
        if frames != original_frames:
            _HFC_CANONICAL_TURN_CARRIER.set(frames)
        if frames:
            frame = frames[-1]
            entry = _CANONICAL_TURN_REGISTRY.get(frame.token)
            if (
                entry is None
                or entry.token is not frame.token
                or not _same_canonical_turn_owner(entry.owner, owner)
                or entry.turn_id != frame.turn_id
            ):
                return None
            carried = entry.turn_id
    if explicit_turn_id is None:
        return carried
    if carried is not None and carried != explicit_turn_id:
        return None
    return explicit_turn_id


def canonical_turn_context_limit(turn_id: object) -> int | None:
    """Read only the live owner's effective context limit; never retain agent state."""
    if type(turn_id) is not str or not turn_id.strip():
        return None
    owner = _canonical_turn_owner()
    with _CANONICAL_TURN_REGISTRY_LOCK:
        frames = _live_canonical_turn_frames_locked(_HFC_CANONICAL_TURN_CARRIER.get(), owner)
        if not frames or frames[-1].turn_id != turn_id:
            return None
        entry = _CANONICAL_TURN_REGISTRY.get(frames[-1].token)
        if entry is None or entry.metrics_agent_ref is None:
            return None
        agent = entry.metrics_agent_ref()
    try:
        if agent is None or getattr(agent, "_current_turn_id", None) != turn_id:
            return None
        value = getattr(getattr(agent, "context_compressor", None), "context_length", None)
        return value if type(value) is int and 0 < value <= 2**63 - 1 else None
    except Exception:
        return None


def _canonical_turn_registry_size() -> int:
    """Testing/diagnostic count only; never exposes turn identities."""
    with _CANONICAL_TURN_REGISTRY_LOCK:
        return len(_CANONICAL_TURN_REGISTRY)


def reset_canonical_turn_for_tests() -> None:
    with _CANONICAL_TURN_REGISTRY_LOCK:
        _CANONICAL_TURN_REGISTRY.clear()
        _HFC_CANONICAL_TURN_CARRIER.set(())
