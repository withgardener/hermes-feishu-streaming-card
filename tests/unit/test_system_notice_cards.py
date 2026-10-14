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
