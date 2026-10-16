"""PATCH-024 / PATCH-016 retirement: Hermes system notices are HFC cards (user request 2026-10-14)."""
import asyncio
from types import SimpleNamespace

from hermes_feishu_card import hook_runtime


class _Src:
    platform = "feishu"
    chat_id = "oc_x"
    thread_id = ""


def test_compaction_status_is_claimed_as_turn_card_phase(monkeypatch):
    posted = []

    def capture(local_vars, event_name="message.started"):
        posted.append(hook_runtime.build_event(event_name, local_vars))
        return True

    monkeypatch.setattr(hook_runtime, "emit_from_hermes_locals_threadsafe", capture)
    for text in (
        "🗜️ Compacting context — summarizing earlier conversation so I can continue...",
        "🗜️ Compacting context — still summarizing earlier conversation so I can continue...",
    ):
        assert hook_runtime.handle_status_from_hermes_locals(
            {"source": _Src(), "message_id": "om_task", "_run_still_current": lambda: True},
            event_type="lifecycle", message=text,
        ) is True
    assert len(posted) == 2
    for payload in posted:
        assert payload["event"] == "system.notice"
        assert payload["data"]["notice_kind"] == "context-compaction"
        assert payload["data"]["notice_id"] == "context-compaction:active"
        assert payload["data"]["title"] == "正在压缩上下文"
        assert payload["data"]["phase"] == "started"


def test_working_family_is_one_running_card_per_anchor():
    first, second = "⏳ Working — 1 min", "⏳ Working — 2 min — iteration 4/90, reading config.yaml"
    a = hook_runtime._hfc_classify_system_notice(first)
    b = hook_runtime._hfc_classify_system_notice(second)
    assert a["title"] == b["title"] == "运行中"
    assert a["notice_kind"] == b["notice_kind"] == "heartbeat"
    assert a["notice_terminal"] is False
    mid = hook_runtime._hfc_independent_notice_message_id
    assert mid("oc_x", first, a, anchor="om_t") == mid("oc_x", second, b, anchor="om_t")
    assert mid("oc_x", second, b, anchor="om_t") != mid("oc_x", second, b, anchor="om_u")
    for text in ("⏳ Retrying in 3.0s (attempt 2/3)", "⏳ Waiting for approval",
                 "⏳ loading Qwen3 into memory — 42%"):
        assert hook_runtime._hfc_classify_system_notice(text)["notice_kind"] == "heartbeat"
    wait = hook_runtime._hfc_classify_system_notice(
        "⏳ Gateway is restarting and is not accepting new work right now.")
    assert wait["notice_kind"] == "gateway-restart" and wait["level"] == "warning"


def test_restart_completion_and_online_are_green_cards():
    for text in ("♻ Gateway restarted successfully. Your session continues.",
                 "♻️ Gateway restarted successfully. Your session continues.",
                 hook_runtime._HFC_GATEWAY_ONLINE_TEXT):
        notice = hook_runtime._hfc_classify_system_notice(text)
        assert notice["title"] == "Gateway 重启完成" and notice["level"] == "success", text
        assert notice["notice_terminal"] is True
        assert hook_runtime._hfc_notice_plain_text(notice) is None


def test_restart_completion_send_posts_card_not_text(monkeypatch):
    from hermes_feishu_card.notice_producers import RESTARTED, install_notice_producers
    sent, posts = [], []

    class Adapter:
        _app_id = "fixture"

        async def _hfc_original_send(self, chat_id, content, **kwargs):
            sent.append(content)
            return SimpleNamespace(success=True, message_id="om_text")
        send = hook_runtime._hfc_send_with_native_command_result_card

    class Runner:
        _primary_profile_name = "default"

        def __init__(self):
            self.adapter = Adapter()
            self.adapters = {"feishu": self.adapter}
            self._profile_adapters = {}

        async def _send_restart_notification(self):
            return await self.adapter.send("oc_x", RESTARTED)

    async def post(url, payload, timeout):
        posts.append(payload)
        return {"ok": True, "applied": True, "delivery": {"outcome": "delivered"}}

    async def allowed(*_a, **_k):
        return True

    monkeypatch.setattr(hook_runtime, "_post_json_ordered_response", post)
    monkeypatch.setattr(hook_runtime, "_hfc_direct_card_allowed_async", allowed)
    monkeypatch.setattr(hook_runtime, "load_runtime_config",
                        lambda: SimpleNamespace(enabled=True, event_url="http://sidecar/events", timeout_seconds=1))
    install_notice_producers(Runner)
    result = asyncio.run(Runner()._send_restart_notification())
    assert result.success
    assert sent == []
    assert posts[-1]["event"] == "system.notice"
    assert posts[-1]["data"]["notice_kind"] == "gateway-restart"
    assert posts[-1]["data"]["level"] == "success"


def test_working_heartbeat_is_not_timer_recalled_as_text():
    assert hook_runtime._transient_notice_recall_seconds("⏳ Working — 2 min") is None


import pytest  # noqa: E402


@pytest.mark.parametrize("text,title,level", [
    ("✅ 后台任务已完成 — `cd /root/.hermes/scripts && ZMD_DRY_RUN=1 …` (10s)", "后台任务已完成", "success"),
    ("✅ 后台任务已完成", "后台任务已完成", "success"),
    ("✅ Background task finished — `printf ok` (6s)", "后台任务已完成", "success"),
    ("✅ Background task finished (1h 2m)", "后台任务已完成", "success"),
    ("❌ 后台任务失败 — `pytest -q` (12s, 退出码 1)。最后输出：\n```\nFAILED x\n```\n可以让我重新运行它，或显示完整日志。",
     "后台任务失败", "error"),
    ("❌ Background task failed — `cmd` (exit 1). Last output:\n```\nboom\n```\nAsk me to rerun it or show the full log.",
     "后台任务失败", "error"),
])
def test_concise_background_process_notice_is_a_card(text, title, level):
    # LOCAL PATCH (PATCH-024): the gateway's concise watcher line (zh or en locale) becomes a card.
    notice = hook_runtime._hfc_classify_system_notice(text)
    assert notice is not None, text
    assert notice["title"] == title and notice["level"] == level
    assert notice["notice_kind"] == "background-process" and notice["notice_terminal"] is True
    assert hook_runtime._hfc_notice_plain_text(notice) is None


@pytest.mark.parametrize("text", [
    "✅ 后台任务已完成，但需要注意",            # free text after the template
    "✅ Background task finished but needs attention",
    "✅ 后台任务已完成 — `unclosed",
    "> ✅ 后台任务已完成 — `x` (1s)",           # a quote inside an answer
    "解释一下：✅ 后台任务已完成",
])
def test_lookalike_answers_are_not_background_cards(text):
    notice = hook_runtime._hfc_classify_system_notice(text)
    assert notice is None or notice.get("notice_kind") != "background-process", text


@pytest.mark.parametrize("text", [
    "🧠 Holographic — recalled 1 memory",
    "🧠 Holographic — recalled 3 memories",
    "🧠 Holographic — recalled 10 memories",
    "🧠 Holographic — recalled 21 memories",
    "🧠 Holographic — recalled 150 memories",
    "🧠 Holographic — recalled relevant memory",
    "🧠 Holographic — recalled 1 memory  🧠 Local — recalled 2 memories",
])
def test_memory_recall_status_is_folded_into_current_turn_card(monkeypatch, text):
    posted = []

    def capture(local_vars, event_name="message.started"):
        posted.append(hook_runtime.build_event(event_name, local_vars))
        return True

    monkeypatch.setattr(hook_runtime, "emit_from_hermes_locals_threadsafe", capture)
    assert hook_runtime.handle_status_from_hermes_locals(
        {"source": _Src(), "message_id": "om_turn", "_run_still_current": lambda: True},
        event_type="lifecycle", message=text,
    ) is True
    assert len(posted) == 1
    payload = posted[0]
    assert payload["event"] == "system.notice"
    assert payload["data"]["notice_kind"] == "memory-recall"
    assert payload["data"]["notice_id"] == "memory-recall"
    assert payload["data"]["title"] == "记忆召回"
    assert payload["data"]["notice_scope"] == "session"
    assert payload["data"]["content"] == text
    assert payload["data"].get("create_session") is not True


def test_memory_recall_notice_lookalike_extra_words_are_rejected(monkeypatch):
    posted = []
    monkeypatch.setattr(hook_runtime, "emit_from_hermes_locals_threadsafe",
                        lambda *args, **kwargs: posted.append(args) or True)
    assert hook_runtime.handle_status_from_hermes_locals(
        {"source": _Src(), "_run_still_current": lambda: True},
        event_type="lifecycle", message="🧠 Holographic — recalled 1 memories",
    ) is False
    assert posted == []


@pytest.mark.parametrize("event_type,text", [
    ("warn", "🧠 Holographic — recalled 1 memory"),
    ("lifecycle", "🧠 Holographic — recalled 1 memory (details)"),
    ("lifecycle", "Quoted: 🧠 Holographic — recalled 1 memory"),
    ("lifecycle", "🧠 Holographic — recalled 1 memory\nextra"),
])
def test_memory_recall_lookalikes_are_not_claimed(monkeypatch, event_type, text):
    posted = []
    monkeypatch.setattr(hook_runtime, "emit_from_hermes_locals_threadsafe",
                        lambda *args, **kwargs: posted.append(args) or True)
    assert hook_runtime.handle_status_from_hermes_locals(
        {"source": _Src(), "_run_still_current": lambda: True},
        event_type=event_type, message=text,
    ) is False
    assert hook_runtime.handle_status_from_hermes_locals(
        {"source": _Src(), "_run_still_current": lambda: True},
        event_type="lifecycle", message="📦 Pre-API compression: ~123,456 tokens near the context/output limit. Compacting before the next model call. extra",
    ) is False
    assert posted == []
    # The ordinary adapter-send classifier must never turn a quoted assistant answer into a notice.
    assert hook_runtime._hfc_classify_system_notice(text) is None


def test_status_callback_notices_have_narrow_fixed_producer_anchors():
    recall_notice = hook_runtime._hfc_classify_status_callback_notice(
        "lifecycle", "🧠 Holographic — recalled 1 memory"
    )
    assert recall_notice is not None and recall_notice["notice_kind"] == "memory-recall"
    assert hook_runtime._hfc_classify_status_callback_notice(
        "lifecycle", "Quoted: 🧠 Holographic — recalled 1 memory"
    ) is None
    assert hook_runtime._hfc_classify_status_callback_notice(
        "lifecycle", "Quoted: 🗜️ Compacting context — summarizing earlier conversation so I can continue..."
    ) is None
    assert hook_runtime._hfc_classify_status_callback_notice(
        "lifecycle", "⚠️  Reached maximum iterations (150). Requesting summary..."
    ) is None
    done_notice = hook_runtime._hfc_classify_status_callback_notice(
        "compacted", "✓ Context compaction complete — continuing turn..."
    )
    assert done_notice is not None and done_notice["title"] == "上下文压缩完成"


def test_memory_recall_notices_fold_into_the_card_timeline_without_new_notice_card():
    from hermes_feishu_card.session import CardSession
    from hermes_feishu_card.events import SidecarEvent

    session = CardSession(conversation_id="chat-1", message_id="om_turn", chat_id="oc_x")
    for sequence, text in enumerate((
        "🧠 Holographic — recalled 1 memory",
        "🧠 Holographic — recalled 2 memories",
    ), 1):
        payload = hook_runtime.build_event("system.notice", {
            "source": _Src(), "message_id": "om_turn", "conversation_id": "chat-1",
            "_hfc_notice_title": "记忆召回", "_hfc_notice_level": "info",
            "_hfc_notice_kind": "memory-recall", "_hfc_notice_id": "memory-recall",
            "_hfc_notice_scope": "session", "content": text,
        })
        assert payload is not None
        payload["sequence"] = sequence
        assert session.apply(SidecarEvent.from_dict(payload))
    entries = [entry for entry in session.timeline.snapshot() if entry.kind == "notice"]
    assert len(entries) == 1
    assert entries[0].notice_id == "memory-recall"
    assert entries[0].content == "🧠 Holographic — recalled 2 memories"
    assert session.delivery_kind == "chat"


@pytest.mark.parametrize("event_type,text,title", [
    ("lifecycle", "🗜️ Compacting context — summarizing earlier conversation so I can continue...", "正在压缩上下文"),
    ("lifecycle", "🗜️ Compacting context — still summarizing earlier conversation so I can continue...", "正在压缩上下文"),
    ("lifecycle", "📦 Pre-API compression: ~123,456 tokens near the context/output limit. Compacting before the next model call.", "正在压缩上下文"),
    ("lifecycle", "📦 Preflight compression: ~120,000 tokens >= 100,000 threshold. This may take a moment.", "正在压缩上下文"),
    ("lifecycle", "💤 Resumed after 3600s idle — compacting ~120,000 tokens before continuing.", "正在压缩上下文"),
    ("lifecycle", "🗜️ Context too large (~250,000 tokens) — compressing (1/3)...", "正在压缩上下文"),
    ("lifecycle", "🗜️ Compressed 30 → 12 messages, retrying...", "正在压缩上下文"),
    ("lifecycle", "🗜️ Compressed ~250,000 → ~120,000 tokens, retrying...", "正在压缩上下文"),
    ("lifecycle", "🗜️ Context reduced to 120,000 tokens (was 250,000), retrying...", "正在压缩上下文"),
    ("lifecycle", "⚠️ Iteration budget exhausted (150/150) — asking model to summarise", "即将生成摘要"),
    ("compacted", "✓ Context compaction complete — continuing turn...", "上下文压缩完成"),
])
def test_routine_compression_statuses_stay_on_current_turn_card(monkeypatch, event_type, text, title):
    posted = []

    def capture(local_vars, event_name="message.started"):
        posted.append(hook_runtime.build_event(event_name, local_vars))
        return True

    monkeypatch.setattr(hook_runtime, "emit_from_hermes_locals_threadsafe", capture)
    assert hook_runtime.handle_status_from_hermes_locals(
        {"source": _Src(), "message_id": "om_turn", "_run_still_current": lambda: True},
        event_type=event_type, message=text,
    ) is True
    assert len(posted) == 1
    payload = posted[0]
    assert payload["event"] == "system.notice"
    assert payload["data"]["notice_kind"] == "context-compaction"
    assert payload["data"]["notice_id"] == "context-compaction:active"
    assert payload["data"]["title"] == title
    assert payload["data"]["phase"] == "started"
    assert payload["data"]["notice_scope"] == "session"


@pytest.mark.parametrize("text", [
    "⚠️ auxiliary compression model failed (model x)",
    "⚠️  Reached maximum iterations (150). Requesting summary...",
    "↻ Updated gateway user service definition to match the current Hermes install",
])
def test_status_callback_only_claims_known_producers(text):
    assert hook_runtime._hfc_classify_status_callback_notice("lifecycle", text) is None


@pytest.mark.parametrize("text", [
    "Quoted: 🗜️ Compacting context — summarizing earlier conversation so I can continue...",
    "🗜️ Compacting context — summarizing earlier conversation so I can continue... extra",
    "📦 Pre-API compression: ~123,456 tokens near the context/output limit. Compacting before the next model call. extra",
    "✓ Context compaction complete — continuing turn...\nquoted",
])
def test_compression_status_lookalikes_are_not_claimed(monkeypatch, text):
    posted = []
    monkeypatch.setattr(hook_runtime, "emit_from_hermes_locals_threadsafe",
                        lambda *args, **kwargs: posted.append(args) or True)
    assert hook_runtime.handle_status_from_hermes_locals(
        {"source": _Src(), "_run_still_current": lambda: True},
        event_type="lifecycle", message=text,
    ) is False
    assert posted == []
