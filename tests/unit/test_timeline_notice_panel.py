"""The 思考与工具 panel is for thinking and tool work — not for notices alone.

The panel was created whenever the timeline had ANY entry, and notices (a deferred-compression
hint, a skill-loading note) were rendered inside it. A session with no tool calls then showed a
panel headed "思考与工具 · 0 次工具调用": a panel advertising zero of the thing it is named after
while displaying something unrelated. Notices render standalone in that case instead, so the hint
stays visible.
"""
import pytest

from hermes_feishu_card.events import SidecarEvent
from hermes_feishu_card.render import render_card
from hermes_feishu_card.session import CardSession

BASE = {
    "schema_version": "1",
    "conversation_id": "chat-1",
    "message_id": "msg-1",
    "chat_id": "oc_abc",
    "platform": "feishu",
    "created_at": 0.0,
}
COMPRESSION_NOTICE = "ℹ️ 上下文压缩已推迟 — 摘要仍在生成中。本回合将不压缩继续。"


def _session(*events) -> CardSession:
    session = CardSession(conversation_id="chat-1", message_id="msg-1", chat_id="oc_abc")
    for sequence, event in enumerate(events, start=1):
        session.apply(SidecarEvent(sequence=sequence, **event, **BASE))
    return session


def _notice_event(**extra):
    return {
        "event": "system.notice",
        "data": {
            "title": "上下文压缩提示",
            "level": "info",
            "content": COMPRESSION_NOTICE,
            "notice_kind": "compression",
            "notice_id": "compression-1",
            **extra,
        },
    }


def _tool_event(name="terminal", status="completed"):
    return {
        "event": "tool.updated",
        "data": {"tool_id": "t1", "name": name, "status": status},
    }


def _panels(card):
    return [e for e in card["body"]["elements"] if e.get("tag") == "collapsible_panel"]


def test_a_notice_only_timeline_renders_no_thinking_panel():
    """The reported bug: a panel headed "0 次工具调用" holding a compression hint."""
    card = render_card(_session(_notice_event()))
    text = str(card)

    assert _panels(card) == []
    assert "思考与工具" not in text
    assert "0 次工具调用" not in text
    # The hint itself has to survive: it is actionable, and hiding it would be worse than the
    # misleading header this fixes.
    assert "上下文压缩已推迟" in text


def test_a_timeline_with_tool_work_still_uses_the_panel():
    """Unchanged for real work: the notice keeps riding inside the panel."""
    card = render_card(_session(_tool_event(), _notice_event()))
    panels = _panels(card)

    assert len(panels) == 1
    # Android confirmed that a static direction arrow and "open" hint mislead
    # while expanded. The same neutral action hint survives local toggles.
    assert panels[0]["header"]["title"]["content"] == "思考过程（点按展开/收起）"
    assert "上下文压缩已推迟" in str(panels[0])


def test_reasoning_alone_still_earns_the_panel():
    """The rule keys on work existing, not on tool calls specifically."""
    session = _session(
        {"event": "answer.delta", "data": {"text": "先确认版本。"}},
        _tool_event(),
    )
    card = render_card(session)

    assert len(_panels(card)) == 1
    assert "思考过程" in str(_panels(card)[0])


def test_a_session_with_nothing_to_show_has_no_panel():
    assert _panels(render_card(_session())) == []


@pytest.mark.parametrize("presentation, label", [("classic", "思考过程"), ("task", "执行过程")])
@pytest.mark.parametrize("expanded", [True, False])
def test_panel_header_describes_both_toggle_states_without_changing_content(presentation, label, expanded):
    session = _session(
        _tool_event(),
        {"event": "message.completed", "data": {"answer": "正文保留 BODY_END"}},
    )
    card = render_card(session, presentation=presentation, timeline_expanded=expanded)
    other = render_card(session, presentation=presentation, timeline_expanded=not expanded)
    panel = _panels(card)[0]
    other_panel = _panels(other)[0]
    assert panel["expanded"] is expanded
    assert other_panel["expanded"] is not expanded
    assert panel["header"]["title"] == {"tag": "plain_text", "content": label + "（点按展开/收起）"}
    assert panel["header"] == other_panel["header"]
    assert panel["elements"] == other_panel["elements"]
    assert [e for e in card["body"]["elements"] if e.get("tag") != "collapsible_panel"] == [
        e for e in other["body"]["elements"] if e.get("tag") != "collapsible_panel"
    ]
    assert "BODY_END" in str(card)
    assert "点开查看" not in str(card)
    assert "▸" not in panel["header"]["title"]["content"]


def test_task_reading_preset_honors_explicit_collapsed_override():
    from hermes_feishu_card.reading import expand_reading_preset
    from hermes_feishu_card.render_options import card_render_options

    session = _session(_tool_event())
    options = card_render_options(expand_reading_preset({
        "reading_preset": "task", "timeline_expanded": False,
    }))
    assert options["presentation"] == "task"
    assert options["timeline_expanded"] is False
    panel = _panels(render_card(session, **options))[0]
    assert panel["expanded"] is False
    assert panel["header"]["title"]["content"] == "执行过程（点按展开/收起）"
