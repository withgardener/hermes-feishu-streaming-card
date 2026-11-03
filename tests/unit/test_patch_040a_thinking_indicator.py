"""PATCH-040a: one reasoning-step line in a task body, and tail-kept live thinking.

The task preset streams no reasoning into the body (``stream_thinking_to_body`` is False), so a
model that emits only reasoning + tool calls used to leave the body empty between calls. These
tests pin the replacement contract: at most ONE extra body line, always the newest step, always
replaced (never accumulated), and always yielding to a tool action or a real answer.
"""
import json

import pytest

from hermes_feishu_card import render
from hermes_feishu_card.card_limits import inspect_card_limits
from hermes_feishu_card.events import SidecarEvent
from hermes_feishu_card.session import CardSession


def event(name, sequence, data):
    return SidecarEvent.from_dict(dict(
        schema_version="1", event=name, sequence=sequence, platform="feishu",
        conversation_id="conversation", message_id="turn", chat_id="chat",
        created_at=1700000000 + sequence, data=data,
    ))


def session(**values):
    value = CardSession(conversation_id="conversation", message_id="turn", chat_id="chat")
    for key, item in values.items():
        setattr(value, key, item)
    return value


def thinking_session(*blocks):
    value = session()
    for index, block in enumerate(blocks):
        assert value.apply(event("thinking.delta", index, {"text": block, "mode": "append_block"}))
    return value


def task_card(value, **options):
    options.setdefault("stream_thinking_to_body", False)
    result = render.render_card_result(value, presentation="task", **options)
    assert result.disposition == "card"
    assert inspect_card_limits(result.card).safe
    return result


def elements(card):
    return card["body"]["elements"]


def of_id(card, element_id):
    return [item for item in elements(card) if item.get("element_id") == element_id]


def main_content_ids(card):
    return [item.get("element_id", "") for item in elements(card)
            if str(item.get("element_id", "")).startswith("main_content")]


def main_text(card):
    return "".join(item.get("content", "") for item in elements(card)
                   if str(item.get("element_id", "")).startswith("main_content"))


def panel(card):
    return next(item for item in elements(card) if item.get("element_id") == "auxiliary_timeline")


def panel_text(card):
    return str(panel(card))


def body_markdown_outside_panel(card):
    return [item for item in elements(card)
            if item.get("tag") == "markdown"
            and item.get("element_id") not in {"auxiliary_timeline", "footer"}
            and not str(item.get("element_id", "")).startswith("auxiliary_timeline")]


def test_thinking_only_body_shows_one_step_and_no_main_content():
    value = thinking_session("先确认仓库状态和分支。")
    card = task_card(value).card
    actions = of_id(card, "task_action")
    assert len(actions) == 1
    assert actions[0]["content"] == "先确认仓库状态和分支。"
    assert len(actions[0]["content"]) <= 80
    assert main_content_ids(card) == []
    assert "实时思考" in panel_text(card)


def test_next_block_replaces_the_line_and_the_panel_keeps_the_full_text():
    value = thinking_session("先确认仓库状态和分支。", "再读 render.py 的正文来源。")
    card = task_card(value).card
    actions = of_id(card, "task_action")
    assert [item["content"] for item in actions] == ["再读 render.py 的正文来源。"]
    assert panel_text(card).count("先确认仓库状态和分支。") == 1
    assert panel_text(card).count("再读 render.py 的正文来源。") == 1
    # The panel keeps the full accumulation, in arrival order.
    assert (panel_text(card).index("先确认仓库状态和分支。")
            < panel_text(card).index("再读 render.py 的正文来源。"))
    live_entries = [item for item in panel(card)["elements"]
                    if str(item.get("element_id", "")).startswith("auxiliary_timeline_reasoningentry_")]
    assert len(live_entries) == 1


def test_running_tool_owns_the_action_line():
    value = thinking_session("先确认仓库状态和分支。")
    assert value.apply(event("tool.updated", 1, {
        "tool_id": "t1", "name": "terminal", "status": "running",
        "detail": "rg -n answer_text render.py",
    }))
    card = task_card(value).card
    actions = of_id(card, "task_action")
    assert len(actions) == 1
    assert actions[0]["content"] == "执行命令：rg -n answer_text render.py"
    assert "先确认仓库状态和分支。" not in actions[0]["content"]


def test_answer_delta_takes_the_body_back():
    value = thinking_session("先确认仓库状态和分支。")
    assert value.apply(event("answer.delta", 1, {"text": "已经改好了。"}))
    card = task_card(value).card
    assert main_text(card) == "已经改好了。"
    assert [item["content"] for item in of_id(card, "task_action")] != ["先确认仓库状态和分支。"]
    assert "先确认仓库状态和分支。" not in main_text(card)


@pytest.mark.parametrize("source, expected", [
    ("第一段**重点**。\n\n## 结论\n> 需要改 render.py 的正文来源，避免堆积。", "需要改 render.py 的正文来源，避免堆积。"),
    ("分析一下这段代码。\n\n```python\nprint(12345678)\n```", "分析一下这段代码。"),
    ("- 列表项写的步骤也要能显示。", "列表项写的步骤也要能显示。"),
    ("开头一行。\n同一段里更新的那一行。", "同一段里更新的那一行。"),
    ("前一步。\n\n`  **读代码**  \n\n", "读代码"),
])
def test_markup_is_stripped_and_the_newest_line_wins(source, expected):
    value = session(thinking_text=source)
    card = task_card(value).card
    assert [item["content"] for item in of_id(card, "task_action")] == [expected]


def test_single_very_long_line_is_capped_and_keeps_its_tail():
    source = "推理" * 1000 + "最后一句结论"
    assert len(source) > 2000
    value = session(thinking_text=source)
    card = task_card(value).card
    action = of_id(card, "task_action")[0]["content"]
    assert len(action) <= 80
    assert action.startswith("…")
    assert action.endswith("最后一句结论")
    assert "\n" not in action


def test_completed_turn_has_no_step_line():
    value = session(thinking_text="先确认仓库状态和分支。", status="completed")
    card = task_card(value).card
    assert of_id(card, "task_action") == []


def test_classic_preset_is_untouched(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("classic rendering must not consult the task step line")

    monkeypatch.setattr(render, "_thinking_body_step_text", forbidden)
    value = thinking_session("先确认仓库状态和分支。")
    result = render.render_card_result(value, presentation="classic")
    assert result.disposition == "card"
    ids = [item.get("element_id") for item in elements(result.card)]
    # Classic streams the reasoning into the body and adds no panel entry of its own.
    assert ids == ["main_content", "main_divider", "footer"]
    assert "task_action" not in ids
    assert main_text(result.card) == "先确认仓库状态和分支。"


def test_live_thinking_keeps_its_tail_while_archived_entries_keep_their_head():
    archived = "ARCH-HEAD-MARK " + "旧" * 1400 + " ARCH-TAIL-MARK"
    live = "LIVE-HEAD-MARK " + "新" * 1400 + " LIVE-TAIL-SENTINEL"
    value = session(thinking_text=live)
    value.timeline.record_reasoning(archived)
    card = task_card(value).card
    entries = {item["element_id"]: item.get("content", "") for item in panel(card)["elements"]}
    live_body = entries["auxiliary_timeline_reasoningentry_1"]
    archived_body = entries["auxiliary_timeline_reasoningentry_0"]
    assert "实时思考" in live_body
    assert "LIVE-TAIL-SENTINEL" in live_body
    assert "LIVE-HEAD-MARK" not in live_body
    assert live_body.split("\n", 1)[1].startswith("…")
    assert len(live_body.split("\n", 1)[1]) <= 1200
    assert "思考 1" in archived_body
    assert "ARCH-HEAD-MARK" in archived_body
    assert "ARCH-TAIL-MARK" not in archived_body
    assert "思考内容过长，已截断" in archived_body


def test_body_never_accumulates_reasoning_paragraphs():
    value = thinking_session(
        "第一段推演：先看仓库状态。",
        "第二段推演：再确认正文来源。",
        "第三段推演：最后写测试。",
    )
    card = task_card(value).card
    body_lines = body_markdown_outside_panel(card)
    assert len(body_lines) == 1
    assert body_lines[0].get("element_id") == "task_action"
    assert body_lines[0]["content"] == "第三段推演：最后写测试。"
    assert main_content_ids(card) == []
    assert "第一段推演" not in json.dumps([item for item in elements(card)
                                        if item.get("element_id") != "auxiliary_timeline"],
                                       ensure_ascii=False)


def test_twelve_timeline_entries_plus_the_step_line_stay_within_limits():
    value = session(thinking_text="最新一步：跑完回归再提交。")
    for index in range(12):
        value.timeline.record_reasoning(f"历史思考 {index}：" + "推演内容" * 40)
    value.timeline.record_tool("t1", "terminal", "completed", "pytest tests/unit")
    result = render.render_card_result(value, presentation="task", stream_thinking_to_body=False)
    assert result.disposition == "card"
    assert inspect_card_limits(result.card).safe
    assert [item["content"] for item in of_id(result.card, "task_action")] == ["最新一步：跑完回归再提交。"]
