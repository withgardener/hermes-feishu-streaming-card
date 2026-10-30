import pytest
import time

from hermes_feishu_card import events as events_module
from hermes_feishu_card.events import EventValidationError, SidecarEvent


def valid_payload(event="thinking.delta", sequence=2):
    return {
        "schema_version": "1",
        "event": event,
        "conversation_id": "chat-1",
        "message_id": "msg-1",
        "chat_id": "oc_abc",
        "platform": "feishu",
        "sequence": sequence,
        "created_at": 1777017600.0,
        "data": {"text": "我在分析。"},
    }


def test_parses_valid_event():
    event = SidecarEvent.from_dict(valid_payload())
    assert event.event == "thinking.delta"
    assert event.sequence == 2


def _runtime_admission():
    return {
        "protocol": "hfc-runtime-interaction-v1",
        "runtime_id": "a" * 64,
        "resolve_url": "http://127.0.0.1:43210/runtime/interactions/resolve",
        "interaction_key": "b" * 64,
        "token": "c" * 64,
        "expires_at": time.time() + 20.0,
    }


def test_runtime_interaction_admission_requires_exact_closed_fresh_descriptor():
    payload = valid_payload(event="interaction.requested", sequence=3)
    payload.update(
        turn_id="turn-1",
        event_id="patch:turn-1:interaction:approval-1:3",
        producer="patch",
        phase="started",
    )
    descriptor = _runtime_admission()
    payload["data"] = {
        "interaction_id": "approval-1",
        "kind": "approval",
        "prompt": "请选择",
        "options": [{"label": "允许", "value": "once"}],
        "_hfc_runtime_admission": descriptor,
    }

    event = SidecarEvent.from_dict(payload)

    assert event.data["_hfc_runtime_admission"] == descriptor


def test_runtime_interaction_admission_accepts_full_clarify_wait_window(monkeypatch):
    now = 100.0
    monkeypatch.setattr(events_module.time, "time", lambda: now)
    payload = valid_payload(event="interaction.requested", sequence=3)
    payload.update(
        turn_id="turn-1",
        event_id="patch:turn-1:interaction:clarify-1:3",
        producer="patch",
        phase="started",
    )
    descriptor = _runtime_admission()
    descriptor["expires_at"] = now + 3600.0
    payload["data"] = {
        "interaction_id": "clarify-1",
        "kind": "clarify",
        "prompt": "请选择",
        "options": [{"label": "继续", "value": "once"}],
        "_hfc_runtime_admission": descriptor,
    }

    assert SidecarEvent.from_dict(payload).data["_hfc_runtime_admission"] == descriptor

    descriptor["expires_at"] = now + 3600.001
    with pytest.raises(EventValidationError, match="runtime admission"):
        SidecarEvent.from_dict(payload)


@pytest.mark.parametrize(
    "mutate",
    (
        lambda value: value.update(extra=False),
        lambda value: value.update(protocol="future"),
        lambda value: value.update(runtime_id="A" * 64),
        lambda value: value.update(resolve_url="http://localhost:43210/runtime/interactions/resolve"),
        lambda value: value.update(resolve_url="http://127.0.0.1:43210/runtime/interactions/resolve?x=1"),
        lambda value: value.update(expires_at=time.time() - 1.0),
        lambda value: value.update(expires_at=True),
    ),
)
def test_runtime_interaction_admission_rejects_malformed_before_session_mutation(mutate):
    payload = valid_payload(event="interaction.requested", sequence=3)
    payload.update(
        turn_id="turn-1",
        event_id="patch:turn-1:interaction:approval-1:3",
        producer="patch",
        phase="started",
    )
    descriptor = _runtime_admission()
    mutate(descriptor)
    payload["data"] = {
        "interaction_id": "approval-1",
        "kind": "approval",
        "prompt": "请选择",
        "options": [{"label": "允许", "value": "once"}],
        "_hfc_runtime_admission": descriptor,
    }

    with pytest.raises(EventValidationError, match="runtime admission"):
        SidecarEvent.from_dict(payload)


def test_parses_optional_turn_id_and_exposes_canonical_turn_id():
    payload = valid_payload(event="answer.delta", sequence=1)
    payload["data"] = {"text": "x"}
    payload["message_id"] = "om_anchor"
    payload["turn_id"] = "  om_turn  "

    event = SidecarEvent.from_dict(payload)

    assert event.turn_id == "om_turn"
    assert event.canonical_turn_id == "om_turn"


def test_parses_strict_plugin_identity_and_subagent_event():
    payload = valid_payload(event="subagent.updated", sequence=4)
    payload.update(
        {
            "turn_id": " turn-1 ",
            "event_id": " subagent:turn-1:child-1:started ",
            "producer": " plugin ",
            "phase": " started ",
        }
    )
    payload["data"] = {
        "child_id": "child-1",
        "role": "research",
        "status": "running",
    }

    event = SidecarEvent.from_dict(payload)

    assert event.event_id == "subagent:turn-1:child-1:started"
    assert event.producer == "plugin"
    assert event.phase == "started"
    assert event.turn_id == "turn-1"


class _StringSubclass(str):
    pass


@pytest.mark.parametrize("field", ["event_id", "producer", "phase"])
@pytest.mark.parametrize("value", [None, 1, [], {}, _StringSubclass("plugin")])
def test_rejects_non_exact_optional_identity_strings(field, value):
    payload = valid_payload()
    payload[field] = value

    with pytest.raises(EventValidationError, match=field):
        SidecarEvent.from_dict(payload)


@pytest.mark.parametrize("field", ["event_id", "producer", "phase"])
def test_rejects_overlength_optional_identity_strings(field):
    payload = valid_payload()
    payload[field] = "x" * 257

    with pytest.raises(EventValidationError, match=field):
        SidecarEvent.from_dict(payload)


def test_optional_identity_length_is_checked_after_stripping():
    payload = valid_payload()
    payload.update(
        {
            "turn_id": "turn-1",
            "event_id": f" {'x' * 256} ",
            "producer": " plugin ",
            "phase": " update ",
        }
    )

    event = SidecarEvent.from_dict(payload)

    assert event.event_id == "x" * 256


@pytest.mark.parametrize(
    ("field", "value"),
    [("producer", "other"), ("phase", "finished")],
)
def test_rejects_unknown_optional_identity_values(field, value):
    payload = valid_payload()
    payload[field] = value

    with pytest.raises(EventValidationError, match=field):
        SidecarEvent.from_dict(payload)


@pytest.mark.parametrize(
    "identity",
    [
        {"event_id": "turn:turn-1:started"},
        {"event_id": "turn:turn-1:started", "turn_id": "turn-1"},
        {
            "event_id": "turn:turn-1:started",
            "turn_id": "turn-1",
            "producer": "plugin",
        },
        {"producer": "plugin"},
        {"phase": "started"},
    ],
)
def test_rejects_partial_plugin_identity(identity):
    payload = valid_payload()
    payload.update(identity)

    with pytest.raises(EventValidationError, match="identity"):
        SidecarEvent.from_dict(payload)


def test_legacy_event_identity_defaults_remain_empty():
    event = SidecarEvent.from_dict(valid_payload())

    assert (event.event_id, event.producer, event.phase) == ("", "", "")


def test_missing_turn_id_falls_back_to_message_id():
    event = SidecarEvent.from_dict(valid_payload(event="answer.delta", sequence=1))

    assert event.turn_id == ""
    assert event.canonical_turn_id == event.message_id


@pytest.mark.parametrize("value", [None, 123, [], {}])
def test_rejects_non_string_turn_id(value):
    payload = valid_payload()
    payload["turn_id"] = value

    with pytest.raises(EventValidationError, match="turn_id"):
        SidecarEvent.from_dict(payload)


def test_event_exposes_optional_exact_display_status():
    payload = valid_payload(event="message.completed")
    payload["data"] = {"answer": "稍后继续", "display_status": "in_progress"}

    event = SidecarEvent.from_dict(payload)

    assert event.display_status == "in_progress"


@pytest.mark.parametrize("value", [None, "", "running", "COMPLETED", " completed "])
def test_event_ignores_invalid_optional_display_status(value):
    payload = valid_payload(event="message.completed")
    payload["data"] = {"answer": "最终答案", "display_status": value}

    event = SidecarEvent.from_dict(payload)

    assert event.display_status == ""


@pytest.mark.parametrize(
    "event_name",
    ["interaction.requested", "interaction.completed", "interaction.failed"],
)
def test_parses_interaction_events(event_name):
    payload = valid_payload(event=event_name)
    payload["data"] = {
        "interaction_id": "approval-1",
        "kind": "approval",
        "prompt": "允许执行命令吗？",
    }

    event = SidecarEvent.from_dict(payload)

    assert event.event == event_name
    assert event.data["interaction_id"] == "approval-1"


def test_parses_system_notice_event():
    payload = valid_payload(event="system.notice")
    payload["data"] = {
        "title": "上下文窗口提示",
        "content": "Codex gpt-5.5 caps context at 272K.",
        "level": "info",
        "notice_id": "context-cap",
    }

    event = SidecarEvent.from_dict(payload)

    assert event.event == "system.notice"
    assert event.data["notice_id"] == "context-cap"


def test_rejects_unknown_event_name():
    with pytest.raises(EventValidationError, match="unknown event"):
        SidecarEvent.from_dict(valid_payload(event="bad.event"))


@pytest.mark.parametrize("event", [[], "", {}, "   "])
def test_rejects_invalid_event_name_type(event):
    with pytest.raises(EventValidationError, match="event"):
        SidecarEvent.from_dict(valid_payload(event=event))


def test_rejects_missing_chat_id():
    payload = valid_payload()
    del payload["chat_id"]
    with pytest.raises(EventValidationError, match="chat_id"):
        SidecarEvent.from_dict(payload)


def test_rejects_non_feishu_platform():
    payload = valid_payload()
    payload["platform"] = "slack"
    with pytest.raises(EventValidationError, match="platform"):
        SidecarEvent.from_dict(payload)


@pytest.mark.parametrize("sequence", [True, -1, "2"])
def test_rejects_invalid_sequence(sequence):
    payload = valid_payload(sequence=sequence)
    with pytest.raises(EventValidationError, match="sequence"):
        SidecarEvent.from_dict(payload)


def test_rejects_invalid_created_at():
    payload = valid_payload()
    payload["created_at"] = "abc"
    with pytest.raises(EventValidationError, match="created_at"):
        SidecarEvent.from_dict(payload)


@pytest.mark.parametrize("created_at", [float("nan"), float("inf"), float("-inf")])
def test_rejects_non_finite_created_at(created_at):
    payload = valid_payload()
    payload["created_at"] = created_at
    with pytest.raises(EventValidationError, match="created_at"):
        SidecarEvent.from_dict(payload)


def test_rejects_non_object_data():
    payload = valid_payload()
    payload["data"] = "not-an-object"
    with pytest.raises(EventValidationError, match="data"):
        SidecarEvent.from_dict(payload)


def test_rejects_non_object_payload():
    with pytest.raises(EventValidationError, match="payload must be an object"):
        SidecarEvent.from_dict("not-an-object")


@pytest.mark.parametrize("field", ["conversation_id", "message_id", "chat_id"])
@pytest.mark.parametrize("value", [None, "", "   ", 123])
def test_rejects_invalid_id_fields(field, value):
    payload = valid_payload()
    payload[field] = value
    with pytest.raises(EventValidationError, match=field):
        SidecarEvent.from_dict(payload)


def test_allows_extra_fields():
    payload = valid_payload()
    payload["extra"] = "ignored"
    event = SidecarEvent.from_dict(payload)
    assert event.event == "thinking.delta"


def test_parses_optional_thread_id():
    payload = valid_payload()
    payload["thread_id"] = "omt_thread"

    event = SidecarEvent.from_dict(payload)

    assert event.thread_id == "omt_thread"


def test_event_accepts_optional_group_routing_context():
    payload = valid_payload()
    payload["data"] = {
        "chat_type": "group",
        "tenant_key": "tenant_a",
        "agent_id": "reserved-agent",
        "profile_id": "reserved-profile",
    }

    event = SidecarEvent.from_dict(payload)

    assert event.data["chat_type"] == "group"
    assert event.data["tenant_key"] == "tenant_a"
