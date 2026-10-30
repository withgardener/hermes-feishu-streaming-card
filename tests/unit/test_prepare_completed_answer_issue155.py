"""Completion reconciliation ordering regressions for issue #155."""

from hermes_feishu_card.events import SidecarEvent
from hermes_feishu_card.session import CardSession


def _event(name, sequence, data):
    return SidecarEvent.from_dict(
        {
            "schema_version": "1",
            "event": name,
            "conversation_id": "c",
            "message_id": "m",
            "chat_id": "oc_test",
            "platform": "feishu",
            "sequence": sequence,
            "created_at": 1777017600.0 + sequence,
            "data": data,
        }
    )


def _timeline_content(session: CardSession) -> str:
    return "\n".join(entry.content for entry in session.timeline.snapshot())


def test_tool_before_answer_with_appended_completion_keeps_whole_answer_visible():
    session = CardSession(conversation_id="c", message_id="m", chat_id="oc_test")
    session.apply(_event("tool.updated", 1, {
        "tool_id": "t1", "name": "search", "status": "completed"
    }))
    streamed = "A" * 314
    verifier = "V" * 351
    session.apply(_event("answer.delta", 2, {"text": streamed}))
    session.apply(_event("message.completed", 3, {"answer": streamed + verifier}))

    assert session.answer_text == streamed + verifier
    assert streamed not in "\n".join(
        entry.content for entry in session.timeline.snapshot()
    )


def test_answer_before_tool_archives_preface_and_keeps_final_suffix():
    session = CardSession(conversation_id="c", message_id="m", chat_id="oc_test")
    preface = "我先核对发布说明。"
    final_suffix = "最终结果已经核对完毕，变更内容和版本号均准确无误。"

    session.apply(_event("answer.delta", 1, {"text": preface}))
    session.apply(_event("tool.updated", 2, {
        "tool_id": "t1", "name": "search", "status": "completed"
    }))
    session.apply(_event("message.completed", 3, {"answer": preface + final_suffix}))

    assert session.answer_text == final_suffix
    assert preface in _timeline_content(session)


def test_two_answer_segments_before_tools_are_archived_in_order():
    session = CardSession(conversation_id="c", message_id="m", chat_id="oc_test")
    first_preface = "先检查仓库状态。"
    second_preface = "再检查发布标签。"

    session.apply(_event("answer.delta", 1, {"text": first_preface}))
    session.apply(_event("tool.updated", 2, {
        "tool_id": "t1", "name": "status", "status": "completed"
    }))
    session.apply(_event("answer.delta", 3, {"text": second_preface}))
    session.apply(_event("tool.updated", 4, {
        "tool_id": "t2", "name": "tag", "status": "completed"
    }))
    session.apply(_event("message.completed", 5, {"answer": "最终发布检查完成。"}))

    entries = session.timeline.snapshot()
    assert session.answer_text == "最终发布检查完成。"
    assert [entry.content for entry in entries if entry.kind == "reasoning"] == [
        first_preface,
        second_preface,
    ]


def test_unrelated_completion_after_tool_then_answer_does_not_archive_answer():
    session = CardSession(conversation_id="c", message_id="m", chat_id="oc_test")
    streamed = "流式回答是在工具完成之后产生的。"
    terminal = "终态文本来自独立的完成结果。"

    session.apply(_event("tool.updated", 1, {
        "tool_id": "t1", "name": "search", "status": "completed"
    }))
    session.apply(_event("answer.delta", 2, {"text": streamed}))
    session.apply(_event("message.completed", 3, {"answer": terminal}))

    assert session.answer_text == terminal
    assert streamed not in _timeline_content(session)


def test_empty_completion_keeps_streamed_answer_visible():
    session = CardSession(conversation_id="c", message_id="m", chat_id="oc_test")
    streamed = "工具完成后继续流式输出的完整回答。"

    session.apply(_event("tool.updated", 1, {
        "tool_id": "t1", "name": "search", "status": "completed"
    }))
    session.apply(_event("answer.delta", 2, {"text": streamed}))
    session.apply(_event("message.completed", 3, {"answer": ""}))

    assert session.answer_text == streamed
    assert streamed not in _timeline_content(session)


def test_attachment_completion_keeps_cleaned_terminal_text_authoritative():
    session = CardSession(conversation_id="c", message_id="m", chat_id="oc_test")
    streamed = "工具完成后展示的中间回答。"
    cleaned_terminal_text = "附件已发送，以下是清理后的最终说明。"

    session.apply(_event("tool.updated", 1, {
        "tool_id": "t1", "name": "export", "status": "completed"
    }))
    session.apply(_event("answer.delta", 2, {"text": streamed}))
    session.apply(_event("message.completed", 3, {
        "answer": cleaned_terminal_text,
        "attachments": [{"kind": "file", "name": "report.pdf"}],
    }))

    assert session.answer_text == cleaned_terminal_text
    assert session.attachments == [{"kind": "file", "name": "report.pdf"}]
    assert streamed not in _timeline_content(session)
