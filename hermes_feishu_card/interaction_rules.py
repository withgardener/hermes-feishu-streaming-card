"""Interaction eligibility and isolated display preflight decisions.

The HTTP boundary must first verify the original session/interaction, callback
token and chat under its owner lock, then expire the interaction. A positive
result only permits showing a new window; it does not grant or restore consent.
"""
from __future__ import annotations

from dataclasses import dataclass
from copy import deepcopy
import hashlib
import json
from typing import Any, TYPE_CHECKING, cast, Mapping, Literal, Callable

from .events import SidecarEvent
from .event_rules import policy_profile_id
from .session import CardSession

if TYPE_CHECKING:
    from .session import InteractionState


APPROVAL_RUNTIME_HEARTBEAT_SECONDS = 15.0


@dataclass(frozen=True)
class ApprovalWindowState:
    session_status: str
    interaction_status: str
    pause_on_timeout: bool
    has_runtime_admission: bool
    last_waiter_poll_at: float


def approval_window_can_reopen(state: ApprovalWindowState, *, now: float) -> bool:
    """Preserve the existing live-waiter and 15-second freshness contract."""
    if (
        state.session_status in {"completed", "failed"}
        or state.interaction_status != "paused"
        or not state.pause_on_timeout
        or state.has_runtime_admission
    ):
        return False
    return bool(
        state.last_waiter_poll_at
        and now - state.last_waiter_poll_at <= APPROVAL_RUNTIME_HEARTBEAT_SECONDS
    )


def runtime_admission_fingerprint(descriptor: dict[str, Any]) -> str:
    try:
        body = json.dumps(
            descriptor,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeEncodeError):
        return ""
    return hashlib.sha256(b"hfc-sidecar-runtime-admission-v1\0" + body).hexdigest()



@dataclass(frozen=True, repr=False)
class RuntimeCallbackSnapshot:
    """An in-flight request's original display owner, never an approval claim.

    Capture under the session lock. After network I/O, reacquire that same lock
    and compare against its current owner before applying the result. Referents
    deliberately retain object identity; field equality cannot revive an old
    window. Tokens/descriptors must never appear in automatic repr output.
    """

    session: CardSession
    interaction: InteractionState
    interaction_id: str
    callback_token: str
    chat_id: str
    fingerprint: str
    descriptor: dict[str, Any]
    choice: str
    turn_id: str

    def is_current(self, current_session: CardSession | None) -> bool:
        if current_session is None or current_session is not self.session:
            return False
        interaction = current_session.active_interaction
        return not (
            interaction is not self.interaction
            or interaction is None
            or interaction.interaction_id != self.interaction_id
            or interaction.callback_token != self.callback_token
            or current_session.chat_id != self.chat_id
            or interaction.status != "pending"
            or interaction.runtime_admission is None
            or runtime_admission_fingerprint(
                dict(cast(Mapping[str, Any], interaction.runtime_admission))
            ) != self.fingerprint
        )


def callback_rejection(
    expected_session: CardSession,
    current_session: CardSession | None,
    *,
    interaction_id: str,
    callback_token: str,
    chat_id: str,
    delivery_pending: bool,
) -> Literal["not_found", "delivery_pending"] | None:
    """Classify pre-expiry rejection from the current locked owner.

    Identity is checked before delivery state, so an unrelated callback cannot
    learn the current window's reservation. No expiry or claim is committed.
    """
    if current_session is not expected_session or current_session is None:
        return "not_found"
    interaction = current_session.active_interaction
    if (
        interaction is None
        or interaction.interaction_id != interaction_id
        or interaction.callback_token != callback_token
        or current_session.chat_id != chat_id
    ):
        return "not_found"
    return "delivery_pending" if delivery_pending else None


def runtime_admission_has_expired(interaction: InteractionState, *, now: float) -> bool:
    """Read both deadlines, preserving exact numeric type and short-circuiting.

    The caller owns the failed state, admission removal and receipt mutation.
    A non-pending or non-runtime window cannot be expired through this rule.
    """
    if interaction.status != "pending" or interaction.runtime_admission is None:
        return False
    descriptor = dict(cast(Mapping[str, Any], interaction.runtime_admission))
    expires_at = cast(float, descriptor.get("expires_at"))
    descriptor_expired = bool(type(expires_at) in (int, float) and now >= expires_at)
    return descriptor_expired or interaction.is_expired(now)


def native_text_fallback_requested(event: SidecarEvent) -> bool:
    if event.event != "interaction.requested":
        return False
    data = event.data if isinstance(event.data, dict) else {}
    return str(data.get("fallback_policy") or "").strip().lower() == "native_text"


def runtime_text_decline_requested(event: SidecarEvent) -> bool:
    return (
        event.event == "interaction.requested"
        and type(event.data) is dict
        and type(event.data.get("_hfc_runtime_admission")) is dict
    )


def interaction_preflight_rejection(
    event: SidecarEvent,
    session: CardSession | None,
    *,
    advance_sequence: bool,
    render_disposition: Callable[[CardSession], str],
) -> Literal["interaction_card_limit"] | None:
    """Preview eligibility without registering or mutating a display owner.

    The injected renderer receives only the disposable preview. The coordinator
    retains configuration lookup, rejection metrics and the real state commit.
    Duplicate events do not render; application/render exceptions propagate.
    """
    if event.event != "interaction.requested":
        return None
    preview = deepcopy(session) if session is not None else CardSession(
        conversation_id=event.conversation_id,
        message_id=event.message_id,
        chat_id=event.chat_id,
        route_profile_id=policy_profile_id(event) or "default",
    )
    if preview.apply(event, advance_sequence=advance_sequence):
        if render_disposition(preview) != "card":
            return "interaction_card_limit"
    return None
