"""PATCH-037: text streamed before a tool call must stay in the card body.

Hermes sends an assistant's pre-tool text as ordinary ``answer.delta`` events.
HFC archives that already-streamed prefix into a timeline ``思考 N`` entry as
soon as the turn keeps going after a tool
(``CardSession._archive_current_answer_to_reasoning``), which is intentional —
but the card body then held only the closing sentence while the opening
paragraph existed solely inside the collapsed 思考过程/执行过程 panel.

PATCH-037 re-surfaces those archived prefaces as ordinary body blocks above the
main content (``pre_tool_text_N``), bounded to the last
``MAX_BODY_PREFACE_BLOCKS`` entries of at most ``MAX_BODY_PREFACE_CHARS``
characters each. The timeline keeps its own copy for the panel, so nothing is
hidden; a pending approval keeps today's layout untouched (the decision must
stay on top), and PATCH-012's body tool-summary row stays suppressed.

Every scenario drives a real ``CardSession`` through the real event objects and
renders with the real renderer — no mocks of the code under test.
"""

import time

import pytest

from hermes_feishu_card.render import (
    MAX_BODY_PREFACE_BLOCKS,
    MAX_BODY_PREFACE_CHARS,
    render_card,
)
from hermes_feishu_card.session import CardSession, InteractionOption, InteractionState
from hermes_feishu_card.events import SidecarEvent

# Production card.reading_preset: task (see ~/.hermes_feishu_card/config.yaml).
PROD_RENDER = dict(
    presentation="task",
    show_reasoning=True,
    stream_thinking_to_body=False,
    hide_successful_tool_activity=True,
    reasoning_format="panel",
    timeline_expanded=False,
    timeline_order="newest_first",
)

TEXT_A = "我先查一下磁盘占用和日志，稍等。"
TEXT_B = "查完了：/var 占用 71%，日志里没有新的错误。"


def _event(seq: int, name: str, data: dict) -> SidecarEvent:
    return SidecarEvent.from_dict(
        {
            "schema_version": "1",
            "event": name,
            "conversation_id": "conv-1",
            "message_id": "msg-1",
            "chat_id": "chat-1",
            "platform": "feishu",
            "sequence": seq,
            "created_at": 1700000000.0 + seq,
            "data": data,
        }
    )


def _tool(seq: int, tool_id: str, status: str, detail: str = "df -h") -> SidecarEvent:
    return _event(
        seq,
        "tool.updated",
        {
            "tool_id": tool_id,
            "call_id": tool_id,
            "name": "terminal",
            "status": status,
            "detail": detail,
        },
    )


def _body_elements(card: dict) -> list:
    """Top-level elements of either card shape (session body card or legacy card)."""
    return card.get("body", {}).get("elements") or card.get("elements") or []


def _ids(card: dict) -> list:
    return [element.get("element_id") or element.get("tag") for element in _body_elements(card)]


def _preface_blocks(card: dict) -> list:
    return [
        element
        for element in _body_elements(card)
        if str(element.get("element_id") or "").startswith("pre_tool_text_")
    ]


def _panel_text(card: dict) -> str:
    for element in _body_elements(card):
        if element.get("element_id") == "auxiliary_timeline":
            return "\n".join(
                str(child.get("content") or "")
                for child in element.get("elements") or []
            )
    return ""


def _main_content(card: dict) -> str:
    for element in _body_elements(card):
        if element.get("element_id") == "main_content":
            return str(element.get("content") or "")
    return ""


def _preface_then_answer() -> CardSession:
    """TEXT_A -> tool -> TEXT_B: the production shape of a narrated tool call."""
    session = CardSession(conversation_id="conv-1", message_id="msg-1", chat_id="chat-1")
    seq = iter(range(0, 99))
    session.apply(_event(next(seq), "answer.delta", {"text": TEXT_A}))
    session.apply(_tool(next(seq), "call-1", "running"))
    session.apply(_tool(next(seq), "call-1", "completed", "df -h\n/var 71%"))
    session.apply(_event(next(seq), "answer.delta", {"text": TEXT_B}))
    session.apply(_event(next(seq), "message.completed", {"answer": TEXT_B}))
    return session


def _answer_only() -> CardSession:
    session = CardSession(conversation_id="conv-1", message_id="msg-1", chat_id="chat-1")
    seq = iter(range(0, 99))
    session.apply(_tool(next(seq), "call-1", "running"))
    session.apply(_tool(next(seq), "call-1", "completed", "df -h\n/var 71%"))
    session.apply(_event(next(seq), "answer.delta", {"text": TEXT_B}))
    session.apply(_event(next(seq), "message.completed", {"answer": TEXT_B}))
    return session


def _pending_approval() -> InteractionState:
    return InteractionState(
        interaction_id="i-1",
        kind="approval",
        prompt="需要授权后继续执行",
        description="**完整命令**\nrm -rf /tmp/hfc-patch-037-test",
        status="pending",
        requested_at=time.time(),
        timeout_seconds=300.0,
        options=[
            InteractionOption(label="允许一次", value="once"),
            InteractionOption(label="拒绝", value="deny"),
        ],
    )


def test_pre_tool_text_is_rendered_in_the_body_above_the_main_content():
    session = _preface_then_answer()
    card = render_card(session, **PROD_RENDER)

    blocks = _preface_blocks(card)
    assert [block["content"] for block in blocks] == [TEXT_A]
    assert blocks[0]["element_id"] == "pre_tool_text_0"
    assert _main_content(card) == TEXT_B
    # The preface reads above the answer it preceded, not below it.
    assert _ids(card).index("pre_tool_text_0") < _ids(card).index("main_content")


def test_a_turn_without_pre_tool_text_keeps_the_unpatched_layout():
    card = render_card(_answer_only(), **PROD_RENDER)

    # Exactly the pre-patch layout: the patch adds nothing when no preface was archived.
    assert _ids(card) == ["main_content", "auxiliary_timeline"]
    assert _preface_blocks(card) == []
    assert _main_content(card) == TEXT_B
    assert TEXT_A not in _panel_text(card)


@pytest.mark.parametrize("interaction_mode", ["card", "callback"])
def test_a_pending_approval_keeps_the_decision_on_top_and_skips_the_prefaces(interaction_mode):
    session = _preface_then_answer()
    session.active_interaction = _pending_approval()
    card = render_card(session, interaction_mode=interaction_mode, **PROD_RENDER)

    assert session.active_interaction.status == "pending"
    assert _preface_blocks(card) == []
    assert all(not str(element_id).startswith("pre_tool_text_") for element_id in _ids(card))
    body_text = "\n".join(
        str(element.get("content") or "") for element in _body_elements(card)
    )
    # The decision itself is still on the card, and still above any old output.
    assert "需要授权后继续执行" in body_text


def test_only_the_last_six_archived_prefaces_reach_the_body():
    session = CardSession(conversation_id="conv-1", message_id="msg-1", chat_id="chat-1")
    seq = iter(range(0, 199))
    for index in range(1, 9):
        session.apply(_event(next(seq), "answer.delta", {"text": f"前文{index}"}))
        session.apply(_tool(next(seq), f"call-{index}", "running"))
    # The closing answer archives the last preface and becomes the main content.
    session.apply(_event(next(seq), "answer.delta", {"text": TEXT_B}))
    session.apply(_event(next(seq), "message.completed", {"answer": TEXT_B}))

    archived = [
        entry.content
        for entry in session.timeline.snapshot()
        if entry.kind == "reasoning"
    ]
    assert archived == [f"前文{index}" for index in range(1, 9)]

    blocks = _preface_blocks(render_card(session, **PROD_RENDER))
    assert MAX_BODY_PREFACE_BLOCKS == 6
    assert [block["content"] for block in blocks] == [
        f"前文{index}" for index in range(3, 9)
    ]
    assert [block["element_id"] for block in blocks] == [
        f"pre_tool_text_{index}" for index in range(6)
    ]


def test_an_overlong_preface_is_truncated_with_the_overflow_label():
    long_preface = "长" * (MAX_BODY_PREFACE_CHARS + 400)
    session = CardSession(conversation_id="conv-1", message_id="msg-1", chat_id="chat-1")
    seq = iter(range(0, 99))
    session.apply(_event(next(seq), "answer.delta", {"text": long_preface}))
    session.apply(_tool(next(seq), "call-1", "running"))
    session.apply(_event(next(seq), "answer.delta", {"text": TEXT_B}))
    session.apply(_event(next(seq), "message.completed", {"answer": TEXT_B}))

    blocks = _preface_blocks(render_card(session, **PROD_RENDER))
    assert len(blocks) == 1
    content = blocks[0]["content"]
    assert len(content) <= MAX_BODY_PREFACE_CHARS
    assert content.endswith("前文过长，已折叠")
    assert long_preface not in content


def test_the_timeline_panel_keeps_its_own_copy_of_the_preface():
    session = _preface_then_answer()
    card = render_card(session, **PROD_RENDER)

    panel = _panel_text(card)
    assert "auxiliary_timeline" in _ids(card)
    assert "思考 1" in panel
    assert TEXT_A in panel
    # Same text, two surfaces: the body block is not a move out of the panel.
    assert TEXT_A in [block["content"] for block in _preface_blocks(card)]


def test_patch_012_still_hides_the_body_tool_activity_row():
    session = _preface_then_answer()
    card = render_card(session, **PROD_RENDER)

    element_ids = _ids(card)
    assert not any(str(element_id).startswith("tool_activity") for element_id in element_ids)
    # ... while the tool row inside the panel is still there (PATCH-012 scope).
    assert "terminal" in _panel_text(card)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))
