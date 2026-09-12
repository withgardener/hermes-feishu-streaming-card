from hermes_feishu_card.hook_runtime import _completion_tokens
from hermes_feishu_card.render import _render_footer
from hermes_feishu_card.session import CardSession


def test_completion_token_extraction_preserves_cache_and_prompt_counts():
    tokens = _completion_tokens(
        {
            "tokens": {
                "prompt_tokens": 120,
                "input_tokens": 100,
                "output_tokens": 20,
                "cache_read_tokens": 90,
                "cache_write_tokens": 10,
            }
        },
        "ok",
    )

    assert tokens == {
        "prompt_tokens": 120,
        "input_tokens": 100,
        "output_tokens": 20,
        "cache_read_tokens": 90,
        "cache_write_tokens": 10,
    }


def test_completion_token_extraction_derives_prompt_count_for_legacy_payload():
    tokens = _completion_tokens(
        {"tokens": {"input_tokens": 100, "output_tokens": 20, "cache_read_tokens": 90, "cache_write_tokens": 10}},
        "ok",
    )

    assert tokens["prompt_tokens"] == 200


def test_completion_token_extraction_uses_agent_result_cache_counts():
    tokens = _completion_tokens(
        {
            "tokens": {"input_tokens": 100, "output_tokens": 20},
            "agent_result": {
                "cache_read_tokens": 90,
                "cache_write_tokens": 10,
            },
        },
        "ok",
    )

    assert tokens["prompt_tokens"] == 200
    assert tokens["cache_read_tokens"] == 90
    assert tokens["cache_write_tokens"] == 10


def test_queued_patcher_path_carries_cache_counts():
    from hermes_feishu_card.install import patcher

    block = "\n".join(patcher._render_queued_complete_hook_block("    ", "\n"))

    assert '"prompt_tokens": result.get("prompt_tokens", 0)' in block
    assert '"cache_read_tokens": result.get("cache_read_tokens", 0)' in block
    assert '"cache_write_tokens": result.get("cache_write_tokens", 0)' in block


def test_footer_shows_prompt_cache_hit_rate_when_cache_read_tokens_exist():
    session = CardSession(conversation_id="c", message_id="m", chat_id="c")
    session.status = "completed"
    session.tokens = {
        "input_tokens": 1000,
        "prompt_tokens": 1000,
        "cache_read_tokens": 850,
        "cache_write_tokens": 100,
    }

    footer = _render_footer(session)

    assert "cache 85%" in footer


def test_footer_omits_cache_rate_when_prompt_tokens_are_unavailable():
    session = CardSession(conversation_id="c", message_id="m", chat_id="c")
    session.status = "completed"
    session.tokens = {"cache_read_tokens": 850}

    footer = _render_footer(session)

    assert "cache" not in footer


def test_footer_omits_cache_rate_when_custom_fields_do_not_request_it():
    session = CardSession(conversation_id="c", message_id="m", chat_id="c")
    session.status = "completed"
    session.tokens = {"prompt_tokens": 1000, "cache_read_tokens": 850}

    footer = _render_footer(session, footer_fields=["duration", "model"])

    assert "cache" not in footer
