from __future__ import annotations

import pytest

from hermes_feishu_card.events import SidecarEvent
from hermes_feishu_card.lifecycle import (CleanupPolicy, CleanupState, cleanup_runtime_state,
    cleanup_closed_controller, cleanup_orphan_message_lock, session_cleanup_reason)
from hermes_feishu_card.metrics import SidecarMetrics
from hermes_feishu_card.event_rules import active_session_key
from dataclasses import FrozenInstanceError, fields, replace
from types import SimpleNamespace
from hermes_feishu_card import session as session_module
from hermes_feishu_card.session import CardSession, InteractionState, ToolState


def _state(_aliases=None, **overrides):
    values = dict(sessions={}, aliases={}, message_locks={}, lock_users={},
                  controllers={}, message_ids={}, bot_ids={}, card_configs={},
                  summary_owners={}, summaries={}, interaction_owners={},
                  interaction_results={}, metrics=SidecarMetrics(), diagnostics={})
    values.update(overrides)
    if _aliases is not None:
        values["aliases"] = _aliases
    return CleanupState(**values)


def _session(*, status: str = "thinking", updated_at: float = 100.0) -> CardSession:
    session = CardSession(conversation_id="oc_1", message_id="om_1", chat_id="oc_1")
    session.status = status
    session.updated_at = updated_at
    return session


def _reason(
    session: CardSession,
    *,
    now: float,
    has_card: bool = False,
    has_inflight_send: bool = False,
    controller_closed: bool = True,
) -> str | None:
    return session_cleanup_reason(
        session,
        now=now,
        has_card=has_card,
        has_inflight_send=has_inflight_send,
        controller_closed=controller_closed,
        policy=CleanupPolicy(),
    )


def _event(name: str, sequence: int) -> SidecarEvent:
    return SidecarEvent(
        schema_version="1",
        event=name,
        conversation_id="oc_1",
        message_id="om_1",
        chat_id="oc_1",
        platform="feishu",
        sequence=sequence,
        created_at=50.0,
        data={"text": "accepted"},
    )


def test_cleanup_policy_defaults_are_bounded():
    assert CleanupPolicy() == CleanupPolicy(
        session_retention_seconds=3600,
        zombie_grace_seconds=120,
        history_limit=50,
    )


def test_completed_session_is_collected_after_retention():
    session = _session(status="completed")

    assert _reason(session, now=3701.0, has_card=True) == "terminal_retention_expired"


@pytest.mark.parametrize("status", ["completed", "failed"])
def test_terminal_session_uses_inclusive_retention_boundary(status):
    session = _session(status=status)

    assert _reason(session, now=3699.999, has_card=True) is None
    assert _reason(session, now=3700.0, has_card=True) == "terminal_retention_expired"


def test_terminal_session_waits_for_controller_and_inflight_work():
    session = _session(status="completed")

    assert _reason(session, now=5000.0, has_card=True, controller_closed=False) is None
    assert _reason(session, now=5000.0, has_card=True, has_inflight_send=True) is None


def test_empty_session_waits_for_zombie_grace_and_never_collects_active_interaction():
    session = _session()

    assert _reason(session, now=219.999, controller_closed=False) is None
    session.active_interaction = InteractionState(
        interaction_id="interaction-1",
        kind="approval",
        prompt="允许吗？",
    )
    assert _reason(session, now=500.0, controller_closed=False) is None


def test_empty_thinking_session_is_collected_at_zombie_boundary():
    session = _session()

    assert _reason(session, now=220.0, controller_closed=False) == "zombie_grace_expired"


@pytest.mark.parametrize("field", ["answer_text", "thinking_text"])
def test_nonempty_text_prevents_zombie_collection(field):
    session = _session()
    setattr(session, field, "progress")

    assert _reason(session, now=500.0) is None


def test_tool_or_sequence_progress_prevents_zombie_collection():
    tool_session = _session()
    tool_session.tools["tool-1"] = ToolState("tool-1", "search", "completed")
    sequence_session = _session()
    sequence_session.last_sequence = 0

    assert _reason(tool_session, now=500.0) is None
    assert _reason(sequence_session, now=500.0) is None


def test_card_binding_prevents_zombie_collection():
    assert _reason(_session(), now=500.0, has_card=True) is None


def test_completed_interaction_does_not_block_terminal_retention():
    session = _session(status="completed")
    session.active_interaction = InteractionState(
        interaction_id="interaction-1",
        kind="approval",
        prompt="允许吗？",
        status="completed",
    )

    assert _reason(session, now=3700.0, has_card=True) == "terminal_retention_expired"


def test_expired_pending_interaction_does_not_block_terminal_retention():
    session = _session(status="completed")
    session.active_interaction = InteractionState(
        interaction_id="interaction-expired",
        kind="approval",
        prompt="允许吗？",
        timeout_seconds=5.0,
        requested_at=100.0,
    )

    assert _reason(session, now=3700.0, has_card=True) == "terminal_retention_expired"


def test_unexpired_pending_interaction_still_blocks_terminal_retention():
    session = _session(status="completed")
    session.active_interaction = InteractionState(
        interaction_id="interaction-pending",
        kind="approval",
        prompt="允许吗？",
        timeout_seconds=5000.0,
        requested_at=100.0,
    )

    assert _reason(session, now=3700.0, has_card=True) is None


def test_card_session_timestamps_only_advance_for_accepted_events(monkeypatch):
    times = iter((10.0, 11.0, 20.0))
    monkeypatch.setattr(session_module.time, "time", lambda: next(times))
    session = CardSession(conversation_id="oc_1", message_id="om_1", chat_id="oc_1")

    assert session.created_at == 10.0
    assert session.updated_at == 11.0
    assert session.apply(_event("thinking.delta", 1))
    assert session.updated_at == 20.0
    assert not session.apply(_event("thinking.delta", 1))
    assert session.updated_at == 20.0


def test_cleanup_preserves_alias_reassigned_to_new_active_session():
    app = _state()
    old_key = "om_old"
    new_key = "om_new"
    old = _session(status="completed")
    old.updated_at = 100.0
    new = _session()
    new.updated_at = 3700.0
    new.answer_text = "active"
    app.sessions[old_key] = old
    app.sessions[new_key] = new
    class ReassignedAliases(dict):
        def __init__(self):
            super().__init__({"om_reply": new_key})
            self._first_items_call = True

        def items(self):
            if self._first_items_call:
                self._first_items_call = False
                return (("om_reply", old_key),)
            return super().items()

    app = replace(app, aliases=ReassignedAliases())
    assert app.aliases["om_reply"] == new_key

    cleanup_runtime_state(app, now=3700.0)

    assert old_key not in app.sessions
    assert app.aliases["om_reply"] == new_key


def test_cleanup_keeps_old_canonical_key_when_it_has_been_reassigned_as_alias():
    app = _state()
    old_key = "om_old"
    new_key = "om_new"
    old = _session(status="completed")
    old.updated_at = 100.0
    new = _session()
    new.answer_text = "active"
    app.sessions[old_key] = old
    app.sessions[new_key] = new
    app.aliases[old_key] = new_key

    cleanup_runtime_state(app, now=3700.0)

    assert old_key not in app.sessions
    assert app.aliases[old_key] == new_key
    assert active_session_key(app.sessions, app.aliases, old_key) == new_key


def test_cleanup_view_borrows_references_and_freezes_only_the_binding():
    state = _state()
    other = _state(**{field.name: getattr(state, field.name) for field in fields(state)})
    for field in fields(state):
        assert getattr(other, field.name) is getattr(state, field.name)
    state.sessions["key"] = _session()
    assert other.sessions["key"] is state.sessions["key"]
    with pytest.raises(FrozenInstanceError):
        state.sessions = {}


def test_cleanup_session_replaced_during_observation_is_preserved():
    state = _state()
    old, replacement = _session(status="completed"), _session()
    state.sessions["key"] = old

    def snapshot():
        state.sessions["key"] = replacement
        return {"closed": True, "task_active": False}

    state.controllers["key"] = SimpleNamespace(snapshot=snapshot, close=lambda: None)
    result = cleanup_runtime_state(state, 3700)
    assert result.session_keys == ()
    assert state.sessions["key"] is replacement
    assert state.metrics.sessions_collected == 0


def test_cleanup_runtime_preserves_controller_replaced_during_observation():
    state = _state()
    state.sessions["key"] = _session(status="completed")
    replacement = SimpleNamespace(snapshot=lambda: {"closed": False, "task_active": False})
    closed = []

    def snapshot():
        state.controllers["key"] = replacement
        return {"closed": True, "task_active": False}

    old = SimpleNamespace(snapshot=snapshot, close=lambda: closed.append("old"))
    state.controllers["key"] = old
    result = cleanup_runtime_state(state, 3700)
    assert result.session_keys == ("key",)
    assert result.controllers_collected == 0
    assert state.controllers["key"] is replacement
    assert closed == []


def test_orphan_lock_replaced_during_locked_check_is_preserved():
    state = _state()
    replacement = SimpleNamespace(locked=lambda: False)

    def locked():
        state.message_locks["key"] = replacement
        return False

    old = SimpleNamespace(locked=locked)
    state.message_locks["key"] = old
    assert not cleanup_orphan_message_lock(state, "key", old)
    assert state.message_locks["key"] is replacement


@pytest.mark.parametrize("blocker", ["canonical_lock", "alias_lock", "canonical_user", "alias_user", "controller_active"])
def test_cleanup_retains_terminal_owner_for_each_inflight_view(blocker):
    state = _state()
    state.sessions["key"] = _session(status="completed")
    state.aliases["alias"] = "key"
    if blocker.endswith("lock"):
        key = "alias" if blocker.startswith("alias") else "key"
        state.message_locks[key] = SimpleNamespace(locked=lambda: True)
    elif blocker.endswith("user"):
        state.lock_users["alias" if blocker.startswith("alias") else "key"] = 1
    else:
        state.controllers["key"] = SimpleNamespace(snapshot=lambda: {"closed": True, "task_active": True})
    assert cleanup_runtime_state(state, 3700).session_keys == ()
    assert "key" in state.sessions
    assert state.aliases["alias"] == "key"
    assert state.metrics.sessions_collected == 0


def test_cleanup_order_and_history_preserve_unrelated_owners():
    trace = []

    class Traced(dict):
        def __init__(self, label, values):
            super().__init__(values)
            self.label = label

        def pop(self, key, default=None):
            trace.append((self.label, key))
            return super().pop(key, default)

    state = _state(
        sessions=Traced("sessions", {"key": _session(status="completed")}),
        aliases=Traced("aliases", {"alias": "key"}),
        message_locks=Traced("locks", {"key": SimpleNamespace(locked=lambda: False)}),
        lock_users=Traced("users", {}),
        summaries=Traced("summaries", {"card": "old", "newcard": "new"}),
        summary_owners=Traced("summary_owners", {"card": "key", "newcard": "other"}),
        interaction_results=Traced("receipts", {"approval": "old", "newapproval": "new"}),
        interaction_owners=Traced("receipt_owners", {"approval": "key", "newapproval": "other"}),
        message_ids=Traced("message_ids", {"key": "card"}),
        bot_ids=Traced("bot_ids", {"key": "bot"}),
        card_configs=Traced("configs", {"key": {}}),
    )
    def close():
        trace.append(("close", "key"))
        assert state.sessions == {}
        assert state.summaries == {"newcard": "new"}
        assert state.interaction_results == {"newapproval": "new"}
        assert state.message_ids == state.bot_ids == state.card_configs == {}
        assert state.metrics.sessions_collected == 0

    state.controllers["key"] = SimpleNamespace(
        snapshot=lambda: {"closed": True, "task_active": False}, close=close)
    result = cleanup_runtime_state(state, 3700)
    assert result.controllers_collected == 1
    assert trace.index(("sessions", "key")) < trace.index(("aliases", "alias"))
    assert trace.index(("summaries", "card")) < trace.index(("summary_owners", "card"))
    assert trace.index(("receipts", "approval")) < trace.index(("receipt_owners", "approval"))
    assert trace.index(("summary_owners", "card")) < trace.index(("receipt_owners", "approval")) < trace.index(("close", "key"))
    assert state.metrics.sessions_collected == state.metrics.flush_controllers_collected == 1
    for index in range(60):
        state.sessions[f"private-{index}"] = _session(status="failed")
    cleanup_runtime_state(state, 3700)
    history = state.diagnostics["cleanup_history"]
    assert len(history) == 50
    assert all(set(row) == {"session_key_hash", "reason", "recorded_at"} for row in history)
    assert "private-" not in str(history)


def test_closed_controller_changed_before_cleanup_is_not_collected():
    state = _state()
    old = SimpleNamespace(snapshot=lambda: {"closed": True, "task_active": False})
    replacement = SimpleNamespace(snapshot=lambda: {"closed": False, "task_active": False})
    state.controllers["key"] = replacement
    assert not cleanup_closed_controller(state, "key", old, now=100)
    assert state.controllers["key"] is replacement
