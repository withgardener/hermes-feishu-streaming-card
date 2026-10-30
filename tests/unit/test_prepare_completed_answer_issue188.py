"""Completion reconciliation regression for GitHub issue #188."""

from hermes_feishu_card.events import SidecarEvent
from hermes_feishu_card.session import CardSession


def _event(name: str, sequence: int, data: dict) -> SidecarEvent:
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


def test_short_terminal_postscript_does_not_replace_substantive_streamed_answer():
    session = CardSession(conversation_id="c", message_id="m", chat_id="oc_test")
    answer = (
        "## 结论\n\n"
        "升级可以继续，当前配置和运行状态均已完成核对。\n\n"
        "- 已检查版本与依赖\n"
        "- 已验证关键配置\n"
        "- 已完成核心回归测试\n\n"
        "以上内容是需要保留给用户的正式答案。"
    )
    postscript = "Ad-hoc 验证：PASS"

    session.apply(_event("answer.delta", 1, {"text": answer}))
    session.apply(
        _event(
            "tool.updated",
            2,
            {"tool_id": "verify", "name": "verify", "status": "completed"},
        )
    )
    session.apply(_event("message.completed", 3, {"answer": postscript}))

    assert session.answer_text.startswith(answer)
    assert session.answer_text.endswith(postscript)
    assert answer not in "\n".join(
        entry.content for entry in session.timeline.snapshot()
    )


def test_short_preface_still_yields_to_authoritative_completed_answer():
    session = CardSession(conversation_id="c", message_id="m", chat_id="oc_test")
    preface = "我先核对一下。"
    final = "最终结果已经核对完毕，配置正常，可以继续升级。"

    session.apply(_event("answer.delta", 1, {"text": preface}))
    session.apply(
        _event(
            "tool.updated",
            2,
            {"tool_id": "verify", "name": "verify", "status": "completed"},
        )
    )
    session.apply(_event("message.completed", 3, {"answer": final}))

    assert session.answer_text == final
