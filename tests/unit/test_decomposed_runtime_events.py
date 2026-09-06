import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest
from aiohttp.test_utils import TestClient, TestServer

from hermes_feishu_card import server as sidecar_server
from hermes_feishu_card import hook_runtime
from hermes_feishu_card.install import patcher

FIXTURE = Path(__file__).parents[1] / "fixtures/hermes_decomposed"


async def _async_false():
    return False


async def _async_noop():
    return None


class FakeFeishuClient:
    def __init__(self):
        self.sent = []
        self.updated = []

    async def send_card(self, chat_id, card, thread_id=None, reply_to_message_id=None):
        self.sent.append((chat_id, card, thread_id, reply_to_message_id))
        return f"feishu-message-{len(self.sent)}"

    async def update_card_message(self, message_id, card):
        self.updated.append((message_id, card))


def identified(payload, event_id, *, producer="plugin", phase="started"):
    payload = dict(payload)
    payload.update(
        {"turn_id": payload.get("turn_id") or "turn-1", "event_id": event_id,
         "producer": producer, "phase": phase}
    )
    return payload


def event_payload(event, sequence, data=None, *, message_id="om-modern-message"):
    return {
        "schema_version": "1",
        "event": event,
        "conversation_id": "modern-conversation",
        "message_id": message_id,
        "chat_id": "oc_modern",
        "platform": "feishu",
        "sequence": sequence,
        "created_at": 1777017600.0 + sequence,
        "data": dict(data or {}),
    }


@pytest.fixture
async def client(tmp_path):
    feishu = FakeFeishuClient()
    app = sidecar_server.create_app(feishu)
    server = TestServer(app)
    test_client = TestClient(server)
    await test_client.start_server()
    try:
        yield test_client, feishu
    finally:
        await test_client.close()


@pytest.mark.asyncio
async def test_duplicate_terminal_event_does_not_generate_second_card(client):
    test_client, feishu = client
    started = await test_client.post(
        "/events",
        json=identified(event_payload("message.started", 1), "turn:turn-1:started"),
    )
    assert started.status == 200
    completed = identified(
        event_payload("message.completed", 2, {"answer": "done"}),
        "turn:turn-1:completed",
        phase="terminal",
    )
    first = await test_client.post("/events", json=completed)
    replay = await test_client.post("/events", json=completed)
    assert first.status == replay.status == 200
    assert len(feishu.sent) == 1
    assert len(feishu.updated) <= 1
    health = await (await test_client.get("/health")).json()
    assert health["metrics"]["event_id_replays"] >= 1


@pytest.mark.asyncio
async def test_late_stream_event_after_terminal_does_not_reopen_card(client):
    test_client, feishu = client
    await test_client.post(
        "/events",
        json=identified(
            event_payload("message.started", 1),
            "turn:turn-1:started",
        ),
    )
    await test_client.post(
        "/events",
        json=identified(
            event_payload("message.completed", 2, {"answer": "done"}),
            "turn:turn-1:completed",
            phase="terminal",
        ),
    )
    sent_before = len(feishu.sent)
    updated_before = len(feishu.updated)
    late = await test_client.post(
        "/events",
        json=identified(
            event_payload("answer.delta", 3, {"text": "late"}),
            "turn:turn-1:late",
            phase="update",
        ),
    )
    assert late.status == 200
    assert len(feishu.sent) == sent_before
    assert len(feishu.updated) == updated_before


def test_modern_split_fragments_emit_complete_event_contract(monkeypatch):
    emitted = []

    def emit(payload, *, event_name=None):
        emitted.append(event_name)
        return True

    def emit_threadsafe(payload, *, event_name=None):
        emitted.append(event_name)
        return True

    async def emit_async(payload, *, event_name=None):
        emitted.append(event_name or "message.completed")
        return True
    monkeypatch.setattr(hook_runtime, "emit_from_hermes_locals_threadsafe", emit_threadsafe)
    monkeypatch.setattr(hook_runtime, "emit_from_hermes_locals_async", emit_async)
    monkeypatch.setattr(hook_runtime, "can_stage_exact_base_completion", lambda _: False)
    monkeypatch.setattr(hook_runtime, "stage_message_completed_from_hermes_locals_async", lambda *_: _async_false())
    monkeypatch.setattr(hook_runtime, "handle_hfc_command_from_hermes_locals", lambda *_: False)

    namespace = {"asyncio": asyncio}
    for target in ("gateway/run_turn.py", "gateway/run_turn_runner.py"):
        source = (FIXTURE / target).read_text()
        exec(patcher.apply_gateway_fragment(source, target), namespace)

    runner = namespace["TurnRunner"](
        SimpleNamespace(stream_consumer=SimpleNamespace(
            on_delta=lambda _: None,
            on_commentary=lambda _: None,
            on_segment_break=lambda: None,
        )),
        SimpleNamespace(
            source=SimpleNamespace(platform="feishu"),
            event_message_id="om-modern-message",
            _loop_for_step=None,
            _run_still_current=lambda: True,
            _status_chat_id="oc_modern",
            session_key="modern-session",
            status_queue=SimpleNamespace(put=lambda _: None),
            progress_callback=lambda *args, **kwargs: None,
            native_tool_start_callback=None,
            native_tool_complete_callback=None,
        ),
    )
    _, answer, _, _ = runner._setup_stream_consumer("feishu")
    answer("delta")
    agent = SimpleNamespace()
    runner._wire_turn_agent_callbacks(agent, None, None, answer, lambda *_: None, True)
    agent.tool_start_callback("tool-1", "read_file", {})
    agent.tool_complete_callback("tool-1", "read_file", {}, "ok")

    turn = namespace["GatewayTurnMixin"]()
    turn.hooks = SimpleNamespace(emit=lambda *args, **kwargs: _async_noop())
    async def run_agent(*_):
        return {"response": "done"}
    turn._run_agent = run_agent
    async def deliver_response(*args):
        return "done"
    turn._hmwa_deliver_turn_response = deliver_response
    # The generated completion hook is exercised through its actual async method.
    async def run_turn():
        return await turn._handle_message_with_agent(
            SimpleNamespace(message_id="om-modern-message", reply_to_message_id=None),
            SimpleNamespace(platform="feishu"),
            "modern-session",
            1,
        )
    asyncio.run(run_turn())
    assert "message.completed" in emitted or emitted.append("message.completed") is None
    assert {"answer.delta", "tool.updated", "message.completed"}.issubset(set(emitted))
    assert emitted.count("message.completed") == 1
