from __future__ import annotations

import asyncio
import copy
import json
from pathlib import Path
from urllib.request import ProxyHandler, Request, build_opener

import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

from hermes_feishu_card import hermes_plugin_runtime as runtime_module
from hermes_feishu_card.event_rules import session_key
from hermes_feishu_card.events import SidecarEvent
from hermes_feishu_card.server import create_app, SESSIONS_KEY


def _runtime(post, profile):
    runtime = runtime_module.PluginRuntime(post=post)
    source = "fallback_default" if profile == "default" else "env"
    assert runtime.bind_ingress_from_values(
        profile, source, "session-test", "gateway-test", "generation-test",
        "synthetic-chat", "synthetic-input", "synthetic-input", "",
    )
    return runtime, source


@pytest.mark.parametrize("profile", ["default", "named-test"])
@pytest.mark.parametrize("path", ["started", "delta", "notice", "admission", "terminal", "observer"])
def test_plugin_all_event_paths_keep_bound_profile_owner(profile, path):
    posted = []

    def post(payload, timeout):
        posted.append(copy.deepcopy(payload))
        if "_hfc_runtime_admission" in payload["data"]:
            return {"ok": True, "applied": True, "delivery": {"outcome": "delivered"}, "runtime_admission": True}
        return {"ok": True, "applied": True}

    runtime, source = _runtime(post, profile)
    try:
        runtime.handle_pre_llm_call(session_id="session-test", turn_id="synthetic-turn", platform="feishu")
        if path == "started":
            payload = posted[0]
        elif path == "observer":
            payload = runtime._observer_payload(
                "synthetic-turn", event="tool.updated", event_id="synthetic-tool",
                phase="started", data={"name": "synthetic-tool"},
            )
        elif path == "terminal":
            runtime.handle_post_llm_call(turn_id="synthetic-turn", assistant_response="FINAL_PROFILE_END")
            runtime.handle_on_session_end(turn_id="synthetic-turn", completed=True, failed=False, interrupted=False)
            payload = posted[-1]
        elif path == "admission":
            assert runtime.start_runtime_interaction_listener(b"s" * 32)
            values = ("approval", "gateway-test", "synthetic-turn", "interaction-test", "a" * 64, object())
            assert runtime.register_patch_interaction(*values)
            assert runtime.admit_patch_interaction(*values, lambda choice: True, {
                "prompt": "Synthetic scope", "description": "No execution",
                "allow_custom_input": False, "multi_select": False, "timeout_seconds": 20.0,
                "options": [{"label": "Deny", "value": "deny", "style": "danger"}],
            })
            payload = posted[-1]
        else:
            if path == "delta":
                assert runtime.submit_patch_delta("synthetic-turn", "answer.delta", "synthetic text", "delta")
            else:
                assert runtime.submit_patch_status_notice("synthetic-turn", notice_kind="context-compaction", notice_id="context-compaction:active")
            runtime._coordinators["synthetic-turn"].drain_before_terminal(2)
            payload = posted[-1]
        assert payload["data"].get("profile_id") == profile
        assert payload["data"].get("profile_source") == source
        assert session_key(SidecarEvent.from_dict(payload)) == f"{profile}:synthetic-turn"
    finally:
        runtime.close()


@pytest.mark.parametrize("profile", ["default", "named-test"])
def test_plugin_observer_data_cannot_override_bound_profile(profile):
    runtime, source = _runtime(lambda *args: {"ok": True, "applied": True}, profile)
    try:
        runtime.handle_pre_llm_call(session_id="session-test", turn_id="synthetic-turn", platform="feishu")
        data = {"profile_id": "other-profile", "profile_source": "other", "text": "unchanged"}
        original = copy.deepcopy(data)
        payload = runtime._observer_payload("synthetic-turn", event="answer.delta", event_id="synthetic-delta", phase="delta", data=data)
        assert payload["data"] == {**original, "profile_id": profile, "profile_source": source}
        assert data == original
    finally:
        runtime.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("profile", ["default", "named-test"])
@pytest.mark.parametrize("send_delay", [0.0, 1.1, 2.0])
async def test_plugin_real_http_normal_ack_keeps_one_owner_and_terminal(tmp_path: Path, profile, send_delay):
    class Transport:
        def __init__(self):
            self.sent = []
            self.updated = []

        async def send_card(self, chat_id, card, **kwargs):
            self.sent.append(copy.deepcopy(card))
            return "synthetic-card"

        async def update_card_message(self, message_id, card):
            self.updated.append((message_id, copy.deepcopy(card)))

    transport = Transport()
    app = create_app(transport, card_config={"flush_interval_ms": 1})
    started_acks = []

    @web.middleware
    async def slow_started_ack(request, handler):
        payload = await request.json()
        response = await handler(request)
        if payload.get("event") == "message.started":
            started_acks.append(response.status)
            if send_delay == 2.0 or (send_delay == 1.1 and len(started_acks) == 1):
                await asyncio.sleep(send_delay)
        return response

    app.middlewares.append(slow_started_ack)
    client = TestClient(TestServer(app, host="127.0.0.1"))
    await client.start_server()
    opener = build_opener(ProxyHandler({}))

    def post(payload, timeout):
        request = Request(str(client.make_url('/events')), data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"})
        with opener.open(request, timeout=timeout) as response:
            return json.loads(response.read())

    runtime, _source = _runtime(post, profile)
    try:
        await asyncio.to_thread(runtime.handle_pre_llm_call, session_id="session-test", turn_id="synthetic-turn", platform="feishu")
        expected = runtime_module.TurnState.NATIVE_BYPASS if send_delay == 2.0 else runtime_module.TurnState.CARD_ACTIVE
        assert runtime.turn_state("synthetic-turn") is expected
        await asyncio.sleep(max(0.0, send_delay - 1.6) + .05)
        submitted = await asyncio.to_thread(runtime.submit_patch_delta, "synthetic-turn", "answer.delta", "BODY_PROFILE_END", "delta")
        assert submitted is (expected is runtime_module.TurnState.CARD_ACTIVE)
        if submitted:
            await asyncio.to_thread(runtime._coordinators["synthetic-turn"].drain_before_terminal, 2)
            for _ in range(100):
                if any("BODY_PROFILE_END" in str(card) for _mid, card in transport.updated):
                    break
                await asyncio.sleep(.02)
            assert any(mid == "synthetic-card" and "BODY_PROFILE_END" in str(card) for mid, card in transport.updated)
        await asyncio.to_thread(runtime.handle_post_llm_call, turn_id="synthetic-turn", assistant_response="FINAL_PROFILE_END")
        await asyncio.to_thread(runtime.handle_on_session_end, turn_id="synthetic-turn", completed=True, failed=False, interrupted=False)
        for _ in range(100):
            if transport.updated and "FINAL_PROFILE_END" in str(transport.updated[-1]):
                break
            await asyncio.sleep(.02)
        assert set(app[SESSIONS_KEY]) == {f"{profile}:synthetic-turn"}
        assert len(transport.sent) == 1
        assert transport.updated[-1][0] == "synthetic-card"
        assert "FINAL_PROFILE_END" in str(transport.updated[-1][1])
        record = runtime.take_terminal_record("synthetic-turn")
        assert record["response"] == {"ok": True, "applied": True}
        assert record["payload"]["data"]["profile_id"] == profile
    finally:
        await asyncio.to_thread(runtime.close)
        await client.close()


@pytest.mark.parametrize("responses,expected_state,attempts", [
    ([TimeoutError("synthetic timeout"), {"ok": True, "applied": True}], "CARD_ACTIVE", 2),
    ([TimeoutError("synthetic timeout"), {"ok": True, "applied": False}], "NATIVE_BYPASS", 2),
    ([TimeoutError("synthetic timeout"), TimeoutError("synthetic timeout")], "NATIVE_BYPASS", 2),
    ([{"ok": True, "applied": False, "disposition": "native"}], "NATIVE_BYPASS", 1),
])
def test_plugin_started_unknown_and_duplicate_ack_state_is_bounded(
    monkeypatch, responses, expected_state, attempts
):
    from hermes_feishu_card import hook_runtime

    posted = []
    timeouts = []
    remaining = list(responses)

    def post(payload, timeout):
        posted.append(copy.deepcopy(payload))
        timeouts.append(timeout)
        result = remaining.pop(0)
        if isinstance(result, BaseException):
            raise result
        return result

    runtime, _source = _runtime(post, "default")
    try:
        runtime.handle_pre_llm_call(session_id="session-test", turn_id="synthetic-turn", platform="feishu")
        assert runtime.turn_state("synthetic-turn") is getattr(runtime_module.TurnState, expected_state)
        assert len(posted) == attempts
        assert all(p == posted[0] for p in posted)
        assert timeouts == [0.8] * attempts
        monkeypatch.setattr(hook_runtime, "_plugin_runtime", lambda: runtime)
        # The actual installed Hybrid delta bridge only delegates to PluginRuntime;
        # native-bypass must not secretly emit through an independent Legacy owner.
        monkeypatch.setattr(hook_runtime, "_post_json_sync", lambda *a, **kw: pytest.fail("legacy POST entered"))
        if expected_state == "NATIVE_BYPASS":
            assert hook_runtime.emit_delta_from_hermes_locals_threadsafe({
                "_hfc_authorized": True, "platform": "feishu", "turn_id": "synthetic-turn", "text": "synthetic",
            }, "answer.delta") is False
            assert len(posted) == attempts
    finally:
        runtime.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("profile", ["default", "named-test"])
async def test_signed_transport_late_terminal_ack_preserves_native_suppression(tmp_path, monkeypatch, profile):
    from hermes_feishu_card import hook_runtime

    delivered = asyncio.Event()
    cards = []

    class Transport:
        async def send_card(self, chat_id, card, **kwargs):
            return "synthetic-card"

        async def update_card_message(self, message_id, card):
            if "FINAL_DELAY_END" in str(card):
                await asyncio.sleep(2.1)
                cards.append((message_id, copy.deepcopy(card)))
                delivered.set()

    app = create_app(Transport(), card_config={"flush_interval_ms": 1})

    @web.middleware
    async def slow_terminal_ack(request, handler):
        payload = await request.json()
        response = await handler(request)
        if payload.get("event") == "message.completed":
            # Also delay cached-replay HTTP ACKs: both old 0.8s attempts expire.
            await asyncio.sleep(2.1)
        return response

    app.middlewares.append(slow_terminal_ack)
    client = TestClient(TestServer(app, host="127.0.0.1"))
    await client.start_server()
    signed = runtime_module.SignedEventTransport(
        event_url=str(client.make_url('/events')), timeout_seconds=.8,
        secret_reader=lambda: b"s" * 32,
    )
    runtime, _source = _runtime(signed, profile)
    try:
        await asyncio.to_thread(runtime.handle_pre_llm_call, session_id="session-test", turn_id="synthetic-turn", platform="feishu")
        assert runtime.turn_state("synthetic-turn") is runtime_module.TurnState.CARD_ACTIVE
        await asyncio.to_thread(runtime.handle_post_llm_call, turn_id="synthetic-turn", assistant_response="FINAL_DELAY_END")
        await asyncio.to_thread(runtime.handle_on_session_end, turn_id="synthetic-turn", completed=True, failed=False, interrupted=False)
        await asyncio.wait_for(delivered.wait(), 5)
        assert set(app[SESSIONS_KEY]) == {f"{profile}:synthetic-turn"}
        assert cards and all(mid == "synthetic-card" for mid, _card in cards)
        monkeypatch.setattr(hook_runtime, "_plugin_runtime", lambda: runtime)
        assert runtime._dispositions.get("synthetic-turn") == {"ok": True, "applied": True}
        record = hook_runtime.consume_terminal_record_from_hermes_locals({
            "_hfc_authorized": True, "platform": "feishu", "turn_id": "synthetic-turn",
        })
        assert record is not None
        assert record.response == {"ok": True, "applied": True}
        assert hook_runtime.apply_hybrid_terminal_record(record) == "card"
        # Record and disposition consume the same single delivery claim.
        assert runtime.take_terminal_disposition("synthetic-turn") is None
        assert hook_runtime.consume_terminal_record_from_hermes_locals({
            "_hfc_authorized": True, "platform": "feishu", "turn_id": "synthetic-turn",
        }) is None
    finally:
        await asyncio.to_thread(runtime.close)
        await client.close()


@pytest.mark.parametrize("event", ["message.started", "answer.delta", "tool.updated", "message.completed", "message.failed"])
@pytest.mark.parametrize("requested", [.2, 2.0, 20.0])
def test_signed_event_budget_is_terminal_only_and_still_bounded(monkeypatch, event, requested):
    seen = []

    class Response:
        status = 200
        headers = {}

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def read(self, _limit):
            return b'{"ok":true,"applied":true}'

    def open_response(_request, timeout):
        seen.append(timeout)
        return Response()

    monkeypatch.setattr(runtime_module._NO_PROXY_EVENT_OPENER, "open", open_response)
    signed = runtime_module.SignedEventTransport(
        event_url="http://127.0.0.1:1/events", timeout_seconds=.8,
        secret_reader=lambda: b"s" * 32,
    )
    assert signed({"event": event}, requested) == {"ok": True, "applied": True}
    cap = 10.0 if event in {"message.completed", "message.failed"} else .8
    assert seen == [min(requested, cap)]
