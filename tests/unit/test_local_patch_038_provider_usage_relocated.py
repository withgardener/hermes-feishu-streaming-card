"""PATCH-038: the footer channel prefix has to survive a moved result dict.

Hermes v0.22.2 built the gateway result dict in ``TurnRunner.run_sync``, where
HFC rendered a ``HERMES_FEISHU_CARD_PROVIDER_USAGE`` block that rewrote
``usage["model"]`` through ``hook_runtime.effective_response_model(agent)`` — the
only place the named custom-provider channel (``OKHEMA/...``) is still known,
because the gateway normalises ``custom:okhema`` down to the ``custom`` bucket
before the card ever sees it. v0.22.5 split that method and left the dict in the
extracted ``TurnRunner._run_sync_scoped`` body, so
``install/provider_route.py`` found no candidate, returned the source unchanged,
and the footer silently fell back to ``custom/CLAUDE/Sonnet-5.5``.

The tests below drive the real installer functions over verbatim source
excerpts (no live checkout is read) and then run the *rendered* code: the
capture is executed, its result feeds HFC's own completion-event builder, and the
card footer is rendered. A footer assertion that only checks the helper
function would pass even if the fragment never reached the result dict.
"""

import textwrap
import types

import pytest

from hermes_feishu_card import hook_runtime
from hermes_feishu_card.events import SidecarEvent
from hermes_feishu_card.install import patcher
from hermes_feishu_card.install.provider_route import (
    PROVIDER_USAGE_BEGIN,
    PROVIDER_USAGE_END,
    apply_provider_route_patch,
    has_provider_route_capture,
    provider_route_location,
    remove_provider_route_patch,
)
from hermes_feishu_card.render import render_card
from hermes_feishu_card.session import CardSession

# Verbatim shape of gateway/run_turn_runner.py:1339-1354 (Hermes v0.22.5 tag):
# the result dict lives in the extracted _run_sync_scoped body, not in run_sync.
V0225_SOURCE = textwrap.dedent(
    '''
    _LEDGER_PASSTHROUGH_KEYS = ("session_id",)


    class TurnRunner:
        def run_sync(self):
            return self._run_sync_scoped()

        def _run_sync_scoped(self, ctx):
            result = {"final_response": "查完了：/var 占用 71%", "session_id": "s-1"}
            final_response = result.get("final_response")
            # Actual token counts from the agent instance used for this run.
            agent = ctx.agent_holder[0]
            has_comp = bool(agent) and hasattr(agent, "context_compressor")
            comp = agent.context_compressor if has_comp else None
            usage = {
                "last_prompt_tokens": getattr(comp, "last_prompt_tokens", 0) if has_comp else 0,
                "input_tokens": getattr(agent, "session_prompt_tokens", 0) if has_comp else 0,
                "output_tokens": getattr(agent, "session_completion_tokens", 0) if has_comp else 0,
                "model": getattr(agent, "model", None) if agent else None,
                # Most failed results name no provider; the error card's sign-in / update-key action needs it.
                "provider": getattr(agent, "provider", None) if agent else None,
                "context_length": (getattr(comp, "context_length", 0) or 0) if has_comp else 0,
                **{key: result.get(key) for key in _LEDGER_PASSTHROUGH_KEYS if key in result},
            }
            return usage
    '''
)

# Verbatim shape of gateway/run_turn_runner.py:2167-2180 (Hermes v0.22.2 branch):
# the SAME dict inside run_sync, which is what the 5.0.2 installer rendered into.
V0222_SOURCE = textwrap.dedent(
    '''
    class TurnRunner:
        def run_sync(self):
            result = {"final_response": "查完了：/var 占用 71%"}
            agent = self._ctx.agent_holder[0]
            has_comp = bool(agent) and hasattr(agent, "context_compressor")
            comp = agent.context_compressor if has_comp else None
            usage = {
                "last_prompt_tokens": getattr(comp, "last_prompt_tokens", 0) if has_comp else 0,
                "input_tokens": getattr(agent, "session_prompt_tokens", 0) if has_comp else 0,
                "output_tokens": getattr(agent, "session_completion_tokens", 0) if has_comp else 0,
                "model": getattr(agent, "model", None) if agent else None,
                "provider": getattr(agent, "provider", None) if agent else None,
                "context_length": (getattr(comp, "context_length", 0) or 0) if has_comp else 0,
            }
            return usage
    '''
)

# The block the 5.0.2 installer rendered into v0.22.2, byte for byte; the capture
# sits at the indent of the statement it follows.
EXPECTED_BLOCK_LINES = (
    "# HERMES_FEISHU_CARD_PROVIDER_USAGE_BEGIN",
    "try:",
    "    from hermes_feishu_card.hook_runtime import effective_response_model as _hfc_effective_model",
    '    usage["model"] = _hfc_effective_model(agent) or usage["model"]',
    "except Exception:",
    "    pass",
    "# HERMES_FEISHU_CARD_PROVIDER_USAGE_END",
)


def _expected_block(indent: str) -> str:
    return "".join(indent + line + "\n" for line in EXPECTED_BLOCK_LINES)

PROD_RENDER = dict(
    presentation="task",
    footer_fields=("duration", "model", "cache_rate", "context"),
)


def _agent(model="CLAUDE/Sonnet-5.5", provider="custom", requested_provider="custom:okhema"):
    return types.SimpleNamespace(
        model=model, provider=provider, requested_provider=requested_provider,
    )


def _run_rendered_capture(source: str, agent) -> dict:
    """Execute the rendered installer output and return its usage dict."""
    rendered = apply_provider_route_patch(source)
    namespace: dict = {}
    exec(compile(rendered, "<rendered-run-turn-runner>", "exec"), namespace)
    runner = namespace["TurnRunner"]()
    ctx = types.SimpleNamespace(agent_holder=[agent])
    return runner._run_sync_scoped(ctx)


def _footer(card: dict) -> str:
    for element in card.get("body", {}).get("elements") or []:
        if element.get("element_id") == "footer":
            return str(element.get("content") or "")
    return ""


def _card_for(usage: dict) -> dict:
    agent_result = {"final_response": "查完了：/var 占用 71%", **usage}
    data = hook_runtime._event_data("message.completed", {"agent_result": agent_result}, None, None)
    event = SidecarEvent.from_dict(
        {
            "schema_version": "1",
            "event": "message.completed",
            "conversation_id": "conv-1",
            "message_id": "msg-1",
            "chat_id": "chat-1",
            "platform": "feishu",
            "sequence": 3,
            "created_at": 1700000000.0,
            "data": data,
        }
    )
    session = CardSession(conversation_id="conv-1", message_id="msg-1", chat_id="chat-1")
    session.apply(event)
    return render_card(session, **PROD_RENDER)


def test_the_v0225_result_builder_is_recognised():
    assert provider_route_location(V0225_SOURCE) is not None
    assert has_provider_route_capture(V0225_SOURCE) is True
    index, mode = provider_route_location(V0225_SOURCE)
    assert mode == "USAGE"
    # The insertion point is the end of the usage assignment (the closing brace).
    assert V0225_SOURCE.splitlines()[index - 1].strip() == "}"


def test_the_capture_lands_exactly_once_and_is_removable():
    rendered = apply_provider_route_patch(V0225_SOURCE)

    assert rendered.count(PROVIDER_USAGE_BEGIN) == 1
    assert rendered.count(PROVIDER_USAGE_END) == 1
    assert _expected_block("        ") in rendered
    assert remove_provider_route_patch(rendered) == V0225_SOURCE
    # Rendering an already-rendered source is a no-op, as the installer re-renders.
    assert apply_provider_route_patch(rendered) == rendered


def test_the_installer_entry_point_renders_the_capture_and_removes_it():
    # apply_gateway_fragment is the single renderer every decomposed target uses.
    rendered = patcher.apply_gateway_fragment(V0225_SOURCE, "gateway/run_turn_runner.py")

    assert rendered.count(PROVIDER_USAGE_BEGIN) == 1
    assert patcher.remove_patch(rendered) == V0225_SOURCE


def test_the_v0222_run_sync_layout_still_renders_the_same_block():
    rendered = apply_provider_route_patch(V0222_SOURCE)

    assert provider_route_location(V0222_SOURCE)[1] == "USAGE"
    assert rendered.count(PROVIDER_USAGE_BEGIN) == 1
    assert _expected_block("        ") in rendered
    assert remove_provider_route_patch(rendered) == V0222_SOURCE


def test_an_unknown_result_shape_is_left_untouched():
    source = textwrap.dedent(
        '''
        class TurnRunner:
            def run_sync(self):
                return {"final_response": "no usage dict here"}
        '''
    )

    assert has_provider_route_capture(source) is False
    assert apply_provider_route_patch(source) == source
    assert PROVIDER_USAGE_BEGIN not in apply_provider_route_patch(source)


def test_two_result_builders_are_refused_rather_than_guessed():
    ambiguous = V0222_SOURCE.replace(
        "    class TurnRunner:", "    class LegacyRunner:"
    ) + textwrap.dedent(
        '''
        class TurnRunner:
            def _run_sync_scoped(self, ctx):
                agent = ctx.agent_holder[0]
                usage = {
                    "model": getattr(agent, "model", None) if agent else None,
                    "provider": getattr(agent, "provider", None) if agent else None,
                }
                return usage
        '''
    )

    assert has_provider_route_capture(ambiguous) is False
    assert apply_provider_route_patch(ambiguous) == ambiguous


def test_provider_usage_is_a_declared_decomposed_anchor():
    assert patcher.DECOMPOSED_LAYOUT_MARKERS["provider_usage"] == PROVIDER_USAGE_BEGIN


def test_a_minimal_source_set_without_a_result_dict_stays_installable():
    """The anchor is visible and singular, but a synthetic tree is not refused.

    A minimal source set (upstream's decomposed fixtures) has no gateway result
    dict, so the capture cannot be placed there by definition. Doctor still
    reports the anchor missing and hermes-preflight rejects any anchor that is
    not True, which is where the loud failure belongs — not in the layout gate.
    """
    from hermes_feishu_card.install import detect

    capabilities, locations, error = detect._detect_layout_capabilities(
        {"gateway/run_turn_runner.py": "class TurnRunner:\n    pass\n"},
        "",
        "cron/scheduler.py",
    )
    assert capabilities["provider_usage"] is False
    assert locations["provider_usage"] == ()
    assert "provider_usage" not in (error or "")


def test_end_to_end_footer_shows_the_named_channel():
    """Rendered capture -> HFC completion event -> card footer reads OKHEMA/..."""
    usage = _run_rendered_capture(V0225_SOURCE, _agent())
    assert usage["model"] == "OKHEMA/CLAUDE/Sonnet-5.5"

    footer = _footer(_card_for(usage))
    assert footer.startswith("OKHEMA/CLAUDE/Sonnet-5.5")


def test_end_to_end_footer_follows_the_fallback_route():
    agent = _agent(provider="custom", requested_provider=None)
    agent._provider_fallback_route = ("CLAUDE/Sonnet-5.5", "custom:okhema")

    usage = _run_rendered_capture(V0225_SOURCE, agent)
    assert usage["model"] == "OKHEMA/CLAUDE/Sonnet-5.5"
    assert _footer(_card_for(usage)).startswith("OKHEMA/CLAUDE/Sonnet-5.5")


def test_end_to_end_without_the_capture_loses_the_channel_prefix():
    """The negative control: without the fragment the same turn loses OKHEMA/.

    This is the shape production showed after the v0.22.5 switch: the footer
    falls back to the bare agent model because the gateway has already collapsed
    ``custom:okhema`` into its ``custom`` bucket.
    """
    namespace: dict = {}
    exec(compile(V0225_SOURCE, "<unrendered-run-turn-runner>", "exec"), namespace)
    usage = namespace["TurnRunner"]()._run_sync_scoped(
        types.SimpleNamespace(agent_holder=[_agent()])
    )
    assert usage["model"] == "CLAUDE/Sonnet-5.5"

    footer = _footer(_card_for(usage))
    assert footer.startswith("CLAUDE/Sonnet-5.5")
    assert "OKHEMA/" not in footer


def test_end_to_end_builtin_provider_is_untouched():
    usage = _run_rendered_capture(V0225_SOURCE, _agent(model="gpt-5", provider="openrouter", requested_provider="openrouter"))
    assert usage["model"] == "openrouter/gpt-5"
    assert _footer(_card_for(usage)).startswith("openrouter/gpt-5")


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))
