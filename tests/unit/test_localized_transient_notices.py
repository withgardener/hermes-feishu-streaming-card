"""Known en/zh templates, using exact fixed-upstream composition and send slices."""
import hashlib
import json
import logging
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

from hermes_feishu_card import hook_runtime as runtime
from hermes_feishu_card.install import patcher


FIXTURE = json.loads((Path(__file__).parents[1] / "fixtures/localized_busy_e06df9c.json").read_text(encoding="utf-8"))


def upstream_gateway(monkeypatch, language, *, onboarding=False):
    busy = FIXTURE["locales"][language]["busy"]
    def translate(key, **kwargs):
        return busy[key.removeprefix("gateway.busy.")].format(**kwargs)
    monkeypatch.setitem(sys.modules, "gateway.run", SimpleNamespace(
        _AGENT_PENDING_SENTINEL=object(), _hermes_home=Path("/unused"),
        _load_gateway_config=lambda: {}, _platform_config_key=lambda _: "feishu",
    ))
    monkeypatch.setitem(sys.modules, "gateway.display_config", SimpleNamespace(
        resolve_display_setting=lambda *args: True,
    ))
    monkeypatch.setitem(sys.modules, "agent.onboarding", SimpleNamespace(
        BUSY_INPUT_FLAG="busy", is_seen=lambda *args: not onboarding,
        busy_input_hint_gateway=lambda mode: "保留操作指南 /busy queue",
        mark_seen=lambda *args: None,
    ))
    parts = []
    for item in FIXTURE["slices"]:
        assert hashlib.sha256(item["source"].encode()).hexdigest() == item["sha256"]
        parts.append(item["source"])
    source = "from __future__ import annotations\nclass Gateway:\n" + "\n".join(parts) + "\n"
    patched = patcher._apply_busy_recall_patch(source)
    assert patched != source
    assert patcher.remove_patch(patched) == source
    namespace = {"t": translate, "logger": logging.getLogger(__name__),
                 "format_iteration_progress": lambda n, maximum: f"iteration {n}/{maximum}"}
    exec(compile(patched, "<upstream-e06df9c-busy>", "exec"), namespace)
    gateway = namespace["Gateway"]()
    gateway._agent_has_active_subagents = lambda agent: agent.subagents
    gateway._reply_anchor_for_event = lambda event: event.message_id
    gateway._busy_reply_to = lambda event, anchor: anchor
    gateway._thread_metadata_for_source = lambda source, anchor: {"thread_id": source.thread_id}
    return gateway


def compose(gateway, kind, *, detail=False):
    event = SimpleNamespace(message_id="om_input", source=SimpleNamespace(
        platform="feishu", profile_id="secondary", chat_id="chat_fixture", thread_id="topic_fixture"))
    agent = SimpleNamespace(subagents=kind == "steered_subagents",
        get_activity_summary=lambda: {"current_tool": "terminal", "api_call_count": 3, "max_iterations": 9} if detail else {})
    state = SimpleNamespace(turn=SimpleNamespace(started_ts=60))
    message = gateway._compose_busy_ack_message(event, 180 if detail else 60, state, agent,
        is_steer_mode=kind.startswith("steered"), is_queue_mode=kind in {"queued", "subagent", "compressing"},
        is_redirect_mode=kind == "redirected", demoted_for_subagents=kind == "subagent",
        demoted_for_compression=kind == "compressing")
    return event, message


@pytest.mark.parametrize("language", ["en", "zh"])
@pytest.mark.parametrize("kind", ["redirected", "interrupting", "steered", "steered_subagents"])
@pytest.mark.parametrize("detail", [False, True])
async def test_actual_busy_composition_and_patched_send_schedule_recall(monkeypatch, language, kind, detail):
    gateway = upstream_gateway(monkeypatch, language)
    event, message = compose(gateway, kind, detail=detail)
    sent, posts = [], []
    async def send(**kwargs):
        sent.append(kwargs)
        return SimpleNamespace(success=True, message_id="om_ack")
    async def post(url, payload, timeout):
        posts.append((url, payload))
        return {"ok": True}
    monkeypatch.setattr(runtime, "load_runtime_config", lambda: SimpleNamespace(
        enabled=True, event_url="http://127.0.0.1:8765/events", timeout_seconds=0.8))
    monkeypatch.setattr(runtime, "_post_json_ordered_response", post)
    monkeypatch.delenv("HERMES_FEISHU_CARD_PROFILE_ID", raising=False)
    await gateway._send_busy_reply(event, SimpleNamespace(_send_with_retry=send), message)
    assert sent == [{"chat_id": "chat_fixture", "content": message, "reply_to": "om_input",
                     "metadata": {"thread_id": "topic_fixture"}}]
    assert posts == [("http://127.0.0.1:8765/recall/schedule", {
        "message_id": "om_ack", "delay_seconds": 15.0,
        "route": {"profile_id": "secondary", "chat_id": "chat_fixture", "conversation_id": "topic_fixture"}})]


@pytest.mark.parametrize("language", ["en", "zh"])
@pytest.mark.parametrize("kind", ["queued", "subagent", "compressing"])
@pytest.mark.parametrize("detail", [False, True])
def test_actual_busy_queue_demotion_remains_visible(monkeypatch, language, kind, detail):
    _, message = compose(upstream_gateway(monkeypatch, language), kind, detail=detail)
    assert runtime._transient_notice_recall_seconds(message) is None


@pytest.mark.parametrize("language", ["en", "zh"])
@pytest.mark.parametrize("kind", ["redirected", "interrupting", "steered", "steered_subagents"])
def test_actual_onboarding_is_retained(monkeypatch, language, kind):
    _, message = compose(upstream_gateway(monkeypatch, language, onboarding=True), kind)
    assert runtime._transient_notice_recall_seconds(message) is None


@pytest.mark.parametrize("text", ["⏳ Compressing context", "⏳ Compressing context...",
                                   "⏳ 正在压缩上下文", "⏳ 正在压缩上下文..."])
def test_known_single_compression_status(text):
    assert runtime._transient_notice_recall_seconds(text) == 15.0


@pytest.mark.parametrize("text", [
    "⏳ Subagent working", "⏳ 子代理正在工作", "⏳ Working — 12 min", "⏳ 工作中 — 12 分钟",
    "↪ Redirected current run is an example", "↪ 已重定向当前运行，这是一段回答正文",
    "↪ Redirected current run. I'll adjust using your correction.\nKeep this instruction.",
    "↪ 已重定向当前运行。我会根据你的修正进行调整。\n保留操作指南",
    "⏳ 正在压缩上下文。稍后必须重新发送消息", "⏳ 已排队至下一回合", "⏳ 正在等待未知状态",
    "⏩ 已引导至当前运行及其活跃的子代理。你的消息将在下一次工具调用后送达。",
    "↪ Exécution redirigée", "⏳ 正在壓縮上下文",
])
def test_unknown_or_important_status_is_not_disposable(text):
    assert runtime._transient_notice_recall_seconds(text) is None


def test_string_like_objects_do_not_authorize_recall():
    class Answer:
        def __str__(self):
            return "↪ 已重定向当前运行。我会根据你的修正进行调整。"
    assert runtime._transient_notice_recall_seconds(Answer()) is None


@pytest.mark.parametrize("outcome", ["send_failed", "missing_id", "other_platform", "invalid_profile", "recall_refused", "recall_raised"])
async def test_localized_busy_failure_retains_send_result(monkeypatch, outcome):
    calls = []
    async def schedule(*args, **kwargs):
        calls.append((args, kwargs))
        if outcome == "recall_raised":
            raise OSError("isolated test failure")
        return False
    monkeypatch.setattr(runtime, "schedule_message_recall_async", schedule)
    source = SimpleNamespace(platform="telegram" if outcome == "other_platform" else "feishu",
        chat_id="chat_fixture", thread_id="topic_fixture", profile_id="../invalid" if outcome == "invalid_profile" else "secondary")
    result = SimpleNamespace(success=outcome != "send_failed", message_id="" if outcome == "missing_id" else "om_ack")
    assert not await runtime.recall_busy_redirect_ack_async(SimpleNamespace(source=source),
        "↪ 已重定向当前运行。我会根据你的修正进行调整。", result)
    assert bool(calls) == (outcome in {"recall_refused", "recall_raised"})


@pytest.mark.parametrize("text", ["⏳ Compressing context", "⏳ 正在压缩上下文"])
@pytest.mark.parametrize("context_kind", ["valid", "foreign", "invalid"])
@pytest.mark.parametrize("recall_raises", [False, True])
async def test_actual_adapter_egress_preserves_plain_text_and_result(monkeypatch, text, context_kind, recall_raises):
    runtime.reset_runtime_state()
    calls, sent = [], []
    result = SimpleNamespace(success=True, message_id="om_status")
    class Adapter:
        async def _hfc_original_send(self, *args, **kwargs):
            sent.append((args, kwargs))
            return result
    async def allowed(*args):
        return True
    async def schedule(*args, **kwargs):
        calls.append((args, kwargs))
        if recall_raises:
            raise OSError("isolated recall failure")
        return True
    monkeypatch.setattr(runtime, "_hfc_direct_card_allowed_async", allowed)
    monkeypatch.setattr(runtime, "schedule_message_recall_async", schedule)
    monkeypatch.delenv("HERMES_FEISHU_CARD_PROFILE_ID", raising=False)
    token = runtime._HFC_FEISHU_DELIVERY_CONTEXT.set({
        "chat_id": "foreign_chat" if context_kind == "foreign" else "chat_fixture",
        "profile_id": "secondary", "profile_invalid": context_kind == "invalid",
    })
    try:
        actual = await runtime._hfc_send_with_native_command_result_card(
            Adapter(), "chat_fixture", text, metadata={"thread_id": "topic_fixture"})
    finally:
        runtime._HFC_FEISHU_DELIVERY_CONTEXT.reset(token)
        runtime.reset_runtime_state()
    assert actual is result
    assert sent == [(("chat_fixture", text), {"reply_to": None, "metadata": {"thread_id": "topic_fixture"}})]
    assert len(calls) == (1 if context_kind == "valid" else 0)
    if calls:
        assert calls[0][1]["route"] == {"profile_id": "secondary", "chat_id": "chat_fixture", "conversation_id": "topic_fixture"}
