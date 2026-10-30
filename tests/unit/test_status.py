import pytest

from hermes_feishu_card.events import SidecarEvent
from hermes_feishu_card.session import CardSession
from hermes_feishu_card.status import (
    StatusConfig,
    infer_progress_handoff,
    normalize_display_status,
    resolve_display_status,
)


@pytest.mark.parametrize(
    "value",
    ["thinking", "in_progress", "waiting", "completed", "failed"],
)
def test_normalize_display_status_accepts_exact_values(value):
    assert normalize_display_status(value) == value


@pytest.mark.parametrize(
    "value",
    [None, True, 1, "", "running", "COMPLETED", " completed "],
)
def test_normalize_display_status_rejects_invalid_values(value):
    assert normalize_display_status(value) == ""


def test_explicit_completed_wins_over_progress_words():
    session = CardSession(conversation_id="oc_1", message_id="om_1", chat_id="oc_1")
    session.status = "completed"
    session.answer_text = "数据收集中，数据到位后我会继续生成报告。"
    session.display_status = "completed"

    status = resolve_display_status(session, StatusConfig.defaults())

    assert status.value == "completed"
    assert status.source == "explicit"


def test_inference_requires_active_and_future_signals():
    config = StatusConfig.defaults()

    assert infer_progress_handoff("正在分析，请稍等", config) is False
    assert infer_progress_handoff("数据收集中，数据到位后我会继续生成报告", config) is True


def test_inference_supports_english_marker_pairs():
    config = StatusConfig.defaults()

    assert infer_progress_handoff("I am gathering the data now.", config) is False
    assert infer_progress_handoff("I am gathering the data and will continue when it arrives.", config) is True


def test_status_config_accepts_custom_marker_pairs():
    config = StatusConfig.from_mapping(
        {"active_markers": ["QUEUED"], "future_markers": ["Resume Later"]}
    )

    assert config.active_markers == ("queued",)
    assert config.future_markers == ("resume later",)
    assert infer_progress_handoff("Queued now; RESUME LATER", config) is True


@pytest.mark.parametrize(
    "value",
    [None, {}, {"active_markers": []}, {"future_markers": "later"}],
)
def test_status_config_invalid_or_missing_marker_groups_use_defaults(value):
    config = StatusConfig.from_mapping(value)

    assert config.active_markers
    assert config.future_markers


@pytest.mark.parametrize(
    "answer",
    [
        "",
        "   ",
        "正在分析这一方法的历史影响，结论如下。",
        "The report discusses work in progress across the industry.",
        "数据到位后我会继续生成报告。",
    ],
)
def test_completed_final_answer_is_not_changed_by_empty_or_single_marker_group(answer):
    session = CardSession(conversation_id="oc_1", message_id="om_1", chat_id="oc_1")
    session.status = "completed"
    session.answer_text = answer

    status = resolve_display_status(session, StatusConfig.defaults())

    assert status.value == "completed"
    assert status.source == "session"


def test_completed_handoff_with_paired_markers_is_inferred_in_progress():
    session = CardSession(conversation_id="oc_1", message_id="om_1", chat_id="oc_1")
    session.status = "completed"
    session.answer_text = "资料收集中，全部到位后我会继续整理。"

    status = resolve_display_status(session, StatusConfig.defaults())

    assert status.value == "in_progress"
    assert status.source == "inferred"


def test_failed_session_wins_over_handoff_inference():
    session = CardSession(conversation_id="oc_1", message_id="om_1", chat_id="oc_1")
    session.status = "failed"
    session.answer_text = "数据收集中，数据到位后我会继续生成报告。"

    status = resolve_display_status(session, StatusConfig.defaults())

    assert status.value == "failed"
    assert status.source == "session"


def test_explicit_value_wins_over_failed_session():
    session = CardSession(conversation_id="oc_1", message_id="om_1", chat_id="oc_1")
    session.status = "failed"
    session.display_status = "waiting"

    status = resolve_display_status(session, StatusConfig.defaults())

    assert status.value == "waiting"
    assert status.source == "explicit"


def test_failed_session_wins_over_pending_interaction():
    session = CardSession(conversation_id="oc_1", message_id="om_1", chat_id="oc_1")
    session.apply(
        SidecarEvent(
            schema_version="1",
            event="interaction.requested",
            conversation_id="oc_1",
            message_id="om_1",
            chat_id="oc_1",
            platform="feishu",
            sequence=1,
            created_at=0.0,
            data={"interaction_id": "i_1", "prompt": "请选择"},
        )
    )
    session.status = "failed"

    status = resolve_display_status(session, StatusConfig.defaults())

    assert status.value == "failed"
    assert status.source == "session"


def test_pending_interaction_wins_over_handoff_inference():
    session = CardSession(conversation_id="oc_1", message_id="om_1", chat_id="oc_1")
    session.answer_text = "数据收集中，数据到位后我会继续生成报告。"
    session.apply(
        SidecarEvent(
            schema_version="1",
            event="interaction.requested",
            conversation_id="oc_1",
            message_id="om_1",
            chat_id="oc_1",
            platform="feishu",
            sequence=1,
            created_at=0.0,
            data={"interaction_id": "i_1", "prompt": "请选择"},
        )
    )
    session.status = "completed"

    status = resolve_display_status(session, StatusConfig.defaults())

    assert status.value == "waiting"
    assert status.source == "session"


def test_invalid_explicit_value_falls_back_to_session_status():
    session = CardSession(conversation_id="oc_1", message_id="om_1", chat_id="oc_1")
    session.status = "completed"
    session.answer_text = "最终报告已完成。"
    session.display_status = "done"

    status = resolve_display_status(session, StatusConfig.defaults())

    assert status.value == "completed"
    assert status.source == "session"
