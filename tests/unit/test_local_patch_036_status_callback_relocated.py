"""PATCH-036: the status anchor moved out of TurnRunner in Hermes v0.22.5.

Hermes v0.22.2 defined ``_status_callback_sync`` as a closure inside
``gateway/run_turn_runner.py::_run_agent_inner``. v0.22.5 moved it to
``gateway/run_turn_progress.py::GatewayTurnProgressMixin`` and left only the
``agent.status_callback = ctx._status_callback_sync`` wiring behind, so HFC
5.0.12's legacy-only scan reported the anchor missing (doctor
``compatibility: partial``) and PATCH-024's status-notice cards had no hook.

The predicates below must accept BOTH shapes and stay as strict as before:
a same-named stub, a wrong signature, or a lost turn-context binding must all
be refused (doctor then reports the anchor missing instead of the hook landing
on a function that is not the status path).

The fixtures are verbatim fragments of the two upstream layouts; no test reads
a live Hermes checkout.
"""

import ast
import textwrap

import pytest

from hermes_feishu_card.install import detect, patcher


# --- fixtures ---------------------------------------------------------------

# v0.22.2 shape: the closure lives inside _run_agent_inner, whose locals are the
# seam the hook receives. Body trimmed to the parts the predicate inspects.
LEGACY_RUN_PY = textwrap.dedent(
    '''
    async def _run_agent_inner(self, turn):
        source = turn.source
        event_message_id = turn.event_message_id
        _status_chat_id = turn.chat_id
        _loop_for_step = asyncio.get_running_loop()
        _run_still_current = self._run_still_current

        def _status_callback_sync(event_type: str, message: str) -> None:
            if not _run_still_current():
                return
            self._send_status(source, _status_chat_id, event_message_id, event_type, message)

        agent.status_callback = _status_callback_sync
        return await agent.run()
    '''
)

# v0.22.5 shape: the same callback as a method of GatewayTurnProgressMixin, body
# copied from gateway/run_turn_progress.py:981-1008 of the v0.22.5 tag.
V0225_PROGRESS_PY = textwrap.dedent(
    '''
    import logging

    logger = logging.getLogger(__name__)


    class GatewayTurnProgressMixin:
        def _status_live(self) -> bool:
            return bool(self._ctx._status_adapter) and self._ctx._run_still_current()

        def _status_callback_sync(self, event_type: str, message: str) -> None:
            from gateway.run import _prepare_gateway_status_message, _redact_gateway_user_facing_secrets, _send_or_update_status_coro
            from gateway.warning_notifications import is_warning_status, render_notification
            ctx = self._ctx
            if ctx.mute_notification_reply or not self._status_live():
                return
            prepared = _prepare_gateway_status_message(ctx.source.platform, event_type, message)
            if prepared is None:
                logger.debug(
                    "status_callback suppressed for %s/%s: %s",
                    ctx.source.platform.value if ctx.source.platform else "unknown", event_type,
                    _redact_gateway_user_facing_secrets(str(message or ""))[:160],
                )
                return

            def present():
                fut = self._schedule(
                    _send_or_update_status_coro(ctx._status_adapter, ctx._status_chat_id, event_type, prepared, ctx._status_thread_metadata),
                    f"status_callback ({event_type}) scheduling error",
                )
                if fut is not None and ctx._cleanup_progress:
                    fut.add_done_callback(self._track_future_cleanup_id)
            render_notification(present, platform=ctx.source.platform, user_config=ctx.user_config,
                                diagnostic=is_warning_status(event_type, message))
    '''
).lstrip("\n")

# gateway/run_turn_runner.py of v0.22.5: only the assignment remains, which is
# exactly what the legacy scan matches on and then fails to resolve.
V0225_RUN_TURN_RUNNER_PY = textwrap.dedent(
    '''
    class TurnRunner:
        def _wire_turn_agent_callbacks(self, agent, ctx):
            ctx = self._ctx
            from gateway.run_turn_progress import local_viewer_turn
            agent.status_callback, agent.notice_callback = ctx._status_callback_sync, (
                self._local_notice_callback_sync if local_viewer_turn(self) else self._notice_callback_sync)
    '''
).lstrip("\n")

# v0.22.5 TurnRunner that still owns the callback as a direct method. Used only
# to prove the ambiguous-anchor rule still fires when both homes exist.
DUPLICATE_TURN_RUNNER_PY = textwrap.dedent(
    '''
    class TurnRunner:
        def _status_callback_sync(self, event_type: str, message: str) -> None:
            ctx = self._ctx
            if not self._status_live():
                return
            self._send_status(event_type, message)
    '''
).lstrip("\n")

LEGACY_STATUS_ARGS = dict(
    callback_name="_status_callback_sync",
    begin_marker=patcher.STATUS_PATCH_BEGIN,
    end_marker=patcher.STATUS_PATCH_END,
    renderer=patcher._render_status_hook_block,
    required_outer_names=(
        "source",
        "event_message_id",
        "_status_chat_id",
        "_loop_for_step",
        "_run_still_current",
    ),
    required_callback_args=("event_type", "message"),
    allow_turn_context=True,
)


def _markers(text):
    return [
        line.strip()
        for line in text.splitlines()
        if line.strip().startswith("# HERMES_FEISHU_CARD_")
        and line.strip().endswith("_BEGIN")
    ]


# --- (a) the legacy nested closure is still recognised ----------------------


def test_legacy_nested_status_callback_is_still_patchable():
    module = ast.parse(LEGACY_RUN_PY)
    assert detect._has_legacy_status_callback(module) is True
    # no split modules handed over: unchanged v0.22.2 answer
    assert detect._has_patchable_status_callback(module) is True


def test_legacy_nested_status_callback_still_gets_the_hook():
    rendered = patcher._apply_callback_patch(LEGACY_RUN_PY, **LEGACY_STATUS_ARGS)
    assert rendered.count(patcher.STATUS_PATCH_BEGIN) == 1
    ast.parse(rendered)
    # inserted at the top of the closure body, before its own run guard
    hook = rendered.index(patcher.STATUS_PATCH_BEGIN)
    assert hook < rendered.index("if not _run_still_current():")


# --- (b) the v0.22.5 split layout is recognised ----------------------------


def test_split_status_callback_is_recognised():
    progress = ast.parse(V0225_PROGRESS_PY)
    assert patcher.has_split_status_callback(progress) is True
    # the legacy module on its own still reports False ...
    assert detect._has_patchable_status_callback(ast.parse(V0225_RUN_TURN_RUNNER_PY)) is False
    # ... and True once the split module is offered to the same predicate
    assert (
        detect._has_patchable_status_callback(
            ast.parse(V0225_RUN_TURN_RUNNER_PY), split_modules=(progress,)
        )
        is True
    )


def test_split_status_callback_gets_the_hook_after_the_turn_context_binding():
    sources = {"gateway/run_turn_progress.py": V0225_PROGRESS_PY}
    rendered = patcher.apply_gateway_fragment(
        V0225_PROGRESS_PY,
        "gateway/run_turn_progress.py",
        completion_sources=sources,
    )
    assert _markers(rendered) == [patcher.STATUS_PATCH_BEGIN]
    ast.parse(rendered)
    hook = rendered.index(patcher.STATUS_PATCH_BEGIN)
    # after `ctx = self._ctx`, before the mute/live guard that follows it
    assert rendered.index("ctx = self._ctx") < hook
    assert hook < rendered.index("if ctx.mute_notification_reply or not self._status_live():")
    # the hook reads the turn context, never the (absent) closure locals
    block = rendered[hook : rendered.index(patcher.STATUS_PATCH_END)]
    assert '"source": _hfc_turn_ctx.source,' in block
    assert '"chat_id": _hfc_turn_ctx._status_chat_id,' in block
    assert '"message_id": _hfc_turn_ctx.event_message_id,' in block
    assert "_hfc_turn_ctx._run_still_current()" in block


# --- (c) neither home: refuse ----------------------------------------------


def test_no_status_callback_anywhere_is_not_patchable():
    bare = textwrap.dedent(
        '''
        class GatewayTurnProgressMixin:
            def _status_live(self) -> bool:
                return False
        '''
    ).lstrip("\n")
    assert patcher.has_split_status_callback(ast.parse(bare)) is False
    assert detect._has_patchable_status_callback(ast.parse(bare)) is False
    assert (
        detect._has_patchable_status_callback(
            ast.parse(V0225_RUN_TURN_RUNNER_PY), split_modules=(ast.parse(bare),)
        )
        is False
    )


# --- (d) a same-named function that is not the status callback is refused ---


@pytest.mark.parametrize(
    "old, new",
    [
        (
            "def _status_callback_sync(self, event_type: str, message: str) -> None:",
            "def _status_callback_sync(self, kind: str, text: str) -> None:",
        ),
        # loses the turn-context binding the hook reads from
        ("        ctx = self._ctx\n", "        ctx = None\n"),
        # keeps the shape but is a stub: no live-status guard
        ("if ctx.mute_notification_reply or not self._status_live():",
         "if ctx.mute_notification_reply or not self._ctx_ready:"),
    ],
)
def test_stub_or_wrong_shape_is_refused(old, new):
    mutated = V0225_PROGRESS_PY.replace(old, new)
    assert mutated != V0225_PROGRESS_PY
    assert patcher.has_split_status_callback(ast.parse(mutated)) is False
    # and the hook is not rendered into it
    rendered = patcher.apply_gateway_fragment(
        mutated, "gateway/run_turn_progress.py", completion_sources={}
    )
    assert patcher.STATUS_PATCH_BEGIN not in rendered


def test_extra_required_callback_calls_are_not_guessed():
    # the relocated locator never guesses on preferred-call selection
    tree = ast.parse(V0225_PROGRESS_PY)
    assert (
        patcher._find_turn_progress_callback_body_location(
            tree,
            V0225_PROGRESS_PY.splitlines(keepends=True),
            "_status_callback_sync",
            required_callback_args=("event_type", "message"),
            required_callback_calls=(("_stream_consumer", "on_delta"),),
        )
        is None
    )


# --- (e) both homes present: the ambiguous-anchor rule still fires ----------


def test_both_homes_are_reported_as_ambiguous_anchors():
    cron = textwrap.dedent(
        '''
        async def _deliver_result(job, result):
            return await job.deliver(result)
        '''
    ).lstrip("\n")
    sources = {
        "gateway/run_turn_runner.py": DUPLICATE_TURN_RUNNER_PY,
        "gateway/run_turn_progress.py": V0225_PROGRESS_PY,
    }
    capabilities, locations, error = detect._detect_layout_capabilities(
        sources, cron, "cron/scheduler.py"
    )
    assert capabilities["status_callback"] is True
    assert set(locations["status_callback"]) == {
        "gateway/run_turn_runner.py",
        "gateway/run_turn_progress.py",
    }
    assert "status_callback: ambiguous anchors" in error
    # a non-"supported" capability report is what makes detect_hermes refuse
    assert error != "supported"


# --- (f) one marker in the rendered target ---------------------------------


def test_rendered_progress_target_carries_exactly_one_status_hook():
    sources = {
        "gateway/run_turn_progress.py": V0225_PROGRESS_PY,
        "gateway/run_turn_runner.py": V0225_RUN_TURN_RUNNER_PY,
    }
    rendered = patcher.apply_gateway_fragment(
        V0225_PROGRESS_PY,
        "gateway/run_turn_progress.py",
        completion_sources=sources,
    )
    assert rendered.count(patcher.STATUS_PATCH_BEGIN) == 1
    assert rendered.count(patcher.STATUS_PATCH_END) == 1
    assert _markers(rendered) == [patcher.STATUS_PATCH_BEGIN]


def test_render_then_remove_restores_the_upstream_source():
    # the turn-context block must stay recognisable as owned, or uninstall and
    # the drift-repair path would refuse to strip it
    patched = patcher.apply_gateway_fragment(
        V0225_PROGRESS_PY,
        "gateway/run_turn_progress.py",
        completion_sources={"gateway/run_turn_progress.py": V0225_PROGRESS_PY},
    )
    assert patcher.remove_patch(patched) == V0225_PROGRESS_PY


# --- the new target is part of the manifest / render surface ---------------


def test_run_turn_progress_is_a_declared_decomposed_target():
    from hermes_feishu_card.install import source_layout

    assert "gateway/run_turn_progress.py" in source_layout.DECOMPOSED_GATEWAY_TARGETS
    assert "gateway/run_turn_progress.py" in source_layout.DECOMPOSED_SOURCE_TARGETS
    # and the patcher accepts it as a render target instead of raising
    assert patcher.apply_gateway_fragment(
        V0225_PROGRESS_PY, "gateway/run_turn_progress.py"
    )


def test_ownership_accepts_run_turn_progress_as_a_layout_extension():
    from hermes_feishu_card.install import decomposed_ownership
    import inspect

    source = inspect.getsource(decomposed_ownership._inspect)
    assert '"gateway/run_turn_progress.py"' in source
