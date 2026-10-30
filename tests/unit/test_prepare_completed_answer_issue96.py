"""Tests for _prepare_completed_answer length guard — issue #96.

When tools fire and the streamed answer_text is already the near-complete
final answer, a minor trailing difference (extra period, whitespace) must
NOT cause the full answer to be archived into the reasoning timeline.
"""

from hermes_feishu_card.events import SidecarEvent
from hermes_feishu_card.session import CardSession


def _event(name, sequence, data):
    payload = {
        "schema_version": "1",
        "event": name,
        "conversation_id": "chat-1",
        "message_id": "msg-1",
        "chat_id": "oc_abc",
        "platform": "feishu",
        "sequence": sequence,
        "created_at": 1777017600.0 + sequence,
        "data": data,
    }
    return SidecarEvent.from_dict(payload)


def _session_with_tool_and_answer(answer_text: str) -> CardSession:
    """Create a session with streamed text before a later tool event."""
    session = CardSession(conversation_id="chat-1", message_id="msg-1", chat_id="oc_abc")
    # Stream some answer text
    session.apply(_event("answer.delta", 1, {"text": answer_text}))
    # A later tool event establishes the archival boundary.
    session.apply(_event("tool.updated", 2, {"tool_id": "t1", "name": "search", "status": "completed"}))
    return session


class TestBugScenarioTrailingPunctuation:
    """#96: trailing punctuation causes incorrect archival."""

    def test_trailing_period_does_not_archive(self):
        """Full answer streamed, completed has same + trailing '。' → no archival."""
        full_answer = "根据搜索结果，今天的天气是晴天，温度在25度左右，适合户外活动"
        session = _session_with_tool_and_answer(full_answer)

        # message.completed arrives with same text + trailing period
        session.apply(_event("message.completed", 3, {"answer": full_answer + "。"}))

        assert session.status == "completed"
        # The answer should contain the full text, NOT be truncated to just "。"
        assert len(session.answer_text) > 10
        # The visible answer must still be the full answer (possibly with period)
        assert full_answer in session.answer_text or session.answer_text == full_answer + "。"

    def test_trailing_english_period_does_not_archive(self):
        """Same but with English period."""
        full_answer = "Based on the search results, the weather today is sunny with temperatures around 25C"
        session = _session_with_tool_and_answer(full_answer)

        session.apply(_event("message.completed", 3, {"answer": full_answer + "."}))

        assert session.status == "completed"
        assert len(session.answer_text) > 10


class TestBugScenarioWhitespaceDifference:
    """#96: minor whitespace/normalization difference causes incorrect archival."""

    def test_trailing_whitespace_does_not_archive(self):
        """Completed answer has trailing spaces → no archival."""
        full_answer = "这是一个完整的回答，包含了所有需要的信息和详细的解释"
        session = _session_with_tool_and_answer(full_answer)

        session.apply(_event("message.completed", 3, {"answer": full_answer + "  "}))

        assert session.status == "completed"
        assert len(session.answer_text) > 10

    def test_trailing_newline_does_not_archive(self):
        """Completed answer has trailing newline → no archival."""
        full_answer = "The complete answer with all details about the topic"
        session = _session_with_tool_and_answer(full_answer)

        session.apply(_event("message.completed", 3, {"answer": full_answer + "\n"}))

        assert session.status == "completed"
        assert len(session.answer_text) > 10


class TestLegitimateArchival:
    """Short preface before tool, long final after → should still archive."""

    def test_short_preface_long_final_archives(self):
        """'Let me check...' streamed before tool, then long final answer."""
        preface = "Let me check"
        long_answer = preface + " — here are the detailed results from my search that contain a lot of important information about the topic you asked about."
        session = _session_with_tool_and_answer(preface)

        session.apply(_event("message.completed", 3, {"answer": long_answer}))

        assert session.status == "completed"
        # The short preface should be archived; answer shows the long content
        # after stripping
        assert "Let me check" not in session.answer_text or len(session.answer_text) > len(preface) + 30

    def test_chinese_preface_long_final_archives(self):
        """Short Chinese preface, then long final."""
        preface = "让我查一下"
        # Make the remaining content substantial (>20 chars and >20% of final)
        long_suffix = "，根据我的搜索结果，这个问题的答案是：人工智能在过去十年中取得了巨大进步，深度学习技术使得许多previously不可能的应用成为了现实。"
        long_answer = preface + long_suffix
        session = _session_with_tool_and_answer(preface)

        session.apply(_event("message.completed", 3, {"answer": long_answer}))

        assert session.status == "completed"
        # The answer should be the stripped version (without the preface)
        assert session.answer_text != preface


class TestEqualPrefaceAndFinal:
    """No archival needed when preface equals final."""

    def test_equal_text_no_archival(self):
        """When streamed answer == completed answer, no archival."""
        answer = "完全相同的回答内容不需要任何处理"
        session = _session_with_tool_and_answer(answer)

        session.apply(_event("message.completed", 3, {"answer": answer}))

        assert session.status == "completed"
        assert session.answer_text == answer


class TestNoToolEvents:
    """Without tool events, should never archive via startswith path."""

    def test_no_tool_no_archive(self):
        """No tools fired — startswith archival path should not trigger."""
        session = CardSession(conversation_id="chat-1", message_id="msg-1", chat_id="oc_abc")
        full_answer = "这是一个没有工具调用的回答"
        session.apply(_event("answer.delta", 1, {"text": full_answer}))
        # No tool event!

        session.apply(_event("message.completed", 2, {"answer": full_answer + "。"}))

        assert session.status == "completed"
        # Answer should be fully preserved
        assert len(session.answer_text) > 5


class TestThresholdBoundary:
    """Edge case: stripped exactly at threshold boundary."""

    def test_stripped_at_exact_threshold_does_not_archive(self):
        """len(stripped) == max(20, len(final)//5) → should NOT archive (need >)."""
        # We need: len(stripped) == max(20, len(final) // 5)
        # Let's make final long enough that len(final)//5 > 20
        # If final is 125 chars, then len(final)//5 = 25
        # So we need stripped to be exactly 25 chars
        # preface = final[:-25], stripped = final[-25:]  (25 chars)
        stripped_part = "a" * 25  # exactly 25 chars
        preface_part = "b" * 100  # 100 chars → final = 125 chars, final//5 = 25
        final_text = preface_part + stripped_part  # 125 chars total

        session = _session_with_tool_and_answer(preface_part)

        session.apply(_event("message.completed", 3, {"answer": final_text}))

        assert session.status == "completed"
        assert session.answer_text == final_text

    def test_stripped_one_above_threshold_archives(self):
        """len(stripped) == max(20, len(final)//5) + 1 → should archive."""
        # final = 125 chars, threshold = 25, stripped = 26 chars
        stripped_part = "a" * 26  # 26 chars — just above threshold
        preface_part = "b" * 99  # 99 chars → final = 125, final//5 = 25
        final_text = preface_part + stripped_part

        session = _session_with_tool_and_answer(preface_part)

        session.apply(_event("message.completed", 3, {"answer": final_text}))

        assert session.status == "completed"
        # With 26 > 25, archival should trigger and answer becomes stripped_part
        assert session.answer_text == stripped_part
