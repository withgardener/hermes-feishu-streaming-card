import json
import logging
import threading
import pytest
from tests.unit.test_clarify_delivery_admission import (
    official_clarify as official_clarify,
)
from tests.unit.test_approval_tool_status import dispatcher as dispatcher, active
from hermes_feishu_card import hook_runtime
from hermes_feishu_card.events import SidecarEvent
from hermes_feishu_card.session import CardSession
from hermes_feishu_card.render import render_card
import ast
import contextvars
import copy
import subprocess
import time
import typing
from pathlib import Path
from types import ModuleType, SimpleNamespace

import os

F = Path(os.environ["HFC_FIXED_TAG_SOURCE_ROOT"])
SHA = "3c27eb6234bf91b8ceee9e9071591b31e9b148cb"


def blob(path):
    return subprocess.check_output(["git", "show", SHA + ":" + path], cwd=F)


def approval_scope(monkeypatch):
    source = blob("tools/approval.py")
    tree = ast.parse(source)
    fields = {"_approval_session_key", "_approval_turn_id", "_approval_tool_call_id"}
    methods = {
        "set_current_session_key",
        "reset_current_session_key",
        "set_current_observability_context",
        "reset_current_observability_context",
        "get_current_session_key",
    }
    nodes = [
        copy.deepcopy(n)
        for n in tree.body
        if (
            isinstance(n, ast.AnnAssign)
            and isinstance(n.target, ast.Name)
            and n.target.id in fields
        )
        or (isinstance(n, ast.FunctionDef) and n.name in methods)
    ]
    assert len(nodes) == 8
    module = ModuleType("tools.approval")
    module.__dict__.update(contextvars=contextvars)
    exec(
        compile(
            ast.fix_missing_locations(ast.Module(body=nodes, type_ignores=[])),
            "<canonical-approval-context>",
            "exec",
            flags=__import__("__future__").annotations.compiler_flag,
        ),
        module.__dict__,
    )
    import sys

    monkeypatch.setitem(sys.modules, "tools.approval", module)
    monkeypatch.setattr(sys.modules["tools"], "approval", module, raising=False)
    return module


def execute_dispatch(
    registry_callback,
    *,
    turn_id="synthetic-turn",
    tool_call_id="synthetic-call",
    session_id="synthetic-session",
    post_tool_hook=None,
):
    source = blob("model_tools.py")
    tree = ast.parse(source)
    chunks = []
    for parent in ast.walk(tree):
        for _name, value in ast.iter_fields(parent):
            if not isinstance(value, list):
                continue
            for index, node in enumerate(value):
                if isinstance(node, ast.Assign) and any(
                    isinstance(t, ast.Name) and t.id == "_dispatch_start"
                    for t in node.targets
                ):
                    candidate = value[index : index + 6]
                    if (
                        len(candidate) == 6
                        and isinstance(candidate[1], ast.Assign)
                        and isinstance(candidate[2], ast.Try)
                        and isinstance(candidate[3], ast.Try)
                        and candidate[3].finalbody
                        and isinstance(candidate[4], ast.Assign)
                        and isinstance(candidate[5], ast.Expr)
                    ):
                        chunks.append(candidate)
    assert len(chunks) == 1
    nodes = copy.deepcopy(chunks[0])
    if post_tool_hook is None:
        nodes = nodes[:5]
    calls = []

    def dispatch(name, args, **kwargs):
        assert name == "clarify"
        calls.append((name, args, kwargs))
        return registry_callback()

    ns = {
        "time": time,
        "Dict": typing.Dict,
        "Any": typing.Any,
        "registry": SimpleNamespace(dispatch=dispatch),
        "function_name": "clarify",
        "function_args": {},
        "task_id": "synthetic-task",
        "session_id": session_id,
        "turn_id": turn_id,
        "tool_call_id": tool_call_id,
        "user_task": None,
        "api_request_id": "synthetic-api",
        "skip_tool_execution_middleware": True,
        "_emit_post_tool_call_hook": post_tool_hook,
        "_tool_middleware_trace": [],
    }
    exec(
        compile(
            ast.fix_missing_locations(ast.Module(body=nodes, type_ignores=[])),
            "<canonical-dispatch-context-finally>",
            "exec",
        ),
        ns,
    )
    assert len(calls) == 1
    return ns["result"]


@pytest.mark.parametrize(
    "case", ["timeout", "cancel", "user_answer_looks_like_timeout", "missing_handle"]
)
def test_official_wait_authority_distinguishes_real_states(
    official_clarify, case, monkeypatch
):
    module, _ = official_clarify
    if case == "missing_handle":

        def no_deadline_lookup():
            raise AssertionError("missing handle must not enter the wait loop")

        monkeypatch.setattr(
            module, "time", SimpleNamespace(monotonic=no_deadline_lookup)
        )
        assert module.wait_for_response("synthetic-missing", timeout=0.04) is None
        return
    entry = module.register(
        "synthetic-control", "synthetic-gateway", "synthetic", ["A"]
    )
    timer = None
    if case == "cancel":
        timer = threading.Timer(0.01, lambda: module.clear_session("synthetic-gateway"))
        timer.start()
    elif case == "user_answer_looks_like_timeout":
        assert (
            module.resolve_gateway_clarify(
                entry.clarify_id, "[user did not respond within 0m]"
            )
            is True
        )
    started = time.monotonic()
    answer = module.wait_for_response(
        entry.clarify_id, timeout=0.5 if case == "cancel" else 0.04
    )
    elapsed = time.monotonic() - started
    if timer:
        timer.join(timeout=1)
    if case == "timeout":
        assert (
            answer is None
            and entry.response is None
            and not entry.event.is_set()
            and elapsed >= 0.04
        )
    elif case == "cancel":
        assert answer == "" and entry.event.is_set() and elapsed < 0.5
    else:
        assert answer == "[user did not respond within 0m]" and entry.event.is_set()


def test_owned_real_wait_timeout_must_not_be_completed(
    official_clarify, dispatcher, monkeypatch, tmp_path
):
    clarify, callback = official_clarify
    monkeypatch.setattr(clarify, "get_clarify_timeout", lambda: 0.04)
    runtime, posted = active()

    class Listener:
        resolve_url = "http://127.0.0.1:12345/runtime/interactions/resolve"

        def accepts(self):
            return True

        def close(self):
            return True

        def snapshot(self):
            return {"poisoned": False}

    runtime._runtime_interaction_listener = Listener()
    monkeypatch.setattr(hook_runtime, "_plugin_runtime", lambda: runtime)

    def ack(payload, timeout):
        posted.append(copy.deepcopy(payload))
        return {
            "ok": True,
            "applied": True,
            "delivery": {"outcome": "delivered"},
            "runtime_admission": True,
        }

    runtime._post = ack

    class Adapter:
        def pause_typing_for_chat(self, *args):
            pass

        async def send_clarify(self, **kwargs):
            raise AssertionError("owned path must not native-send")

    ctx = SimpleNamespace(
        _status_adapter=Adapter(),
        session_key="synthetic-gateway",
        _status_chat_id="synthetic-chat",
    )
    namespace = {
        "ctx": ctx,
        "agent": SimpleNamespace(_current_turn_id="synthetic-turn"),
        "logger": logging.getLogger(__name__),
    }
    exec(
        compile(
            ast.fix_missing_locations(ast.Module(body=[callback], type_ignores=[])),
            "<exact-rendered-current-owned-clarify>",
            "exec",
        ),
        namespace,
    )
    source = subprocess.check_output(
        ["git", "show", SHA + ":tools/clarify_tool.py"], cwd=F
    )
    parsed = ast.parse(source)
    wanted = [
        n
        for n in parsed.body
        if isinstance(n, (ast.Import, ast.ImportFrom, ast.FunctionDef))
        and (
            (isinstance(n, (ast.Import, ast.ImportFrom)) and n.lineno < 25)
            or isinstance(n, ast.FunctionDef)
        )
        and (
            not isinstance(n, ast.FunctionDef)
            or n.name
            in {
                "_flatten_choice",
                "_invoke_callback",
                "_parse_multi_select_response",
                "clarify_tool",
            }
        )
    ]
    values = {"MAX_CHOICES": 4}
    exec(
        compile(
            ast.fix_missing_locations(ast.Module(body=wanted, type_ignores=[])),
            "<canonical-clarify-tool>",
            "exec",
        ),
        values,
    )
    token = hook_runtime.publish_canonical_turn_id("synthetic-turn")
    try:
        dispatch, lifecycle = dispatcher
        lifecycle.invoke_hook = lambda name, **kwargs: runtime.handle_post_tool_call(
            **kwargs
        )
        approval = approval_scope(monkeypatch)
        session_token = approval.set_current_session_key("synthetic-gateway")
        outer_tokens = approval.set_current_observability_context(
            turn_id="outer-turn", tool_call_id="outer-call"
        )
        bound = []
        original_callback = namespace["_clarify_callback_sync"]

        def actual_callback(question, choices, multi_select=False):
            bound.append(
                (
                    approval._approval_turn_id.get(),
                    approval._approval_tool_call_id.get(),
                    approval.get_current_session_key(),
                )
            )
            return original_callback(question, choices, multi_select=multi_select)

        try:
            started = time.monotonic()
            result = execute_dispatch(
                lambda: values["clarify_tool"](
                    "synthetic question", ["A"], callback=actual_callback
                ),
                post_tool_hook=dispatch["_emit_post_tool_call_hook"],
            )
            elapsed = time.monotonic() - started
            assert bound == [("synthetic-turn", "synthetic-call", "synthetic-gateway")]
            assert (
                approval._approval_turn_id.get(),
                approval._approval_tool_call_id.get(),
            ) == ("outer-turn", "outer-call")
        finally:
            approval.reset_current_observability_context(outer_tokens)
            approval.reset_current_session_key(session_token)
        assert "error" not in json.loads(result)
        observed_status = dispatch["_tool_result_observer_fields"](result)[0]
        deadline = time.monotonic() + 1
        while (
            not any(p["event"] == "tool.updated" for p in posted)
            and time.monotonic() < deadline
        ):
            time.sleep(0.001)
        payload = next(p for p in posted if p["event"] == "tool.updated")
        event = SidecarEvent.from_dict(payload)
        session = CardSession(
            conversation_id=event.conversation_id,
            message_id=event.message_id,
            chat_id=event.chat_id,
        )
        assert session.apply(event)
        card = render_card(session, presentation="task")
        (tmp_path / "observation.json").write_text(
            json.dumps(
                {
                    "observed_official_dispatch_status": observed_status,
                    "event_status": payload["data"]["status"],
                    "session_status": session.tools["synthetic-call"].status,
                    "elapsed": elapsed,
                    "actual_timeout_response_is_ordinary_json_without_error": True,
                    "card": card,
                },
                indent=2,
                ensure_ascii=False,
            )
            + "\n"
        )
        assert payload["data"]["status"] == "timeout"
        assert session.tools["synthetic-call"].status == "timeout"
        from tests.unit.test_approval_tool_status import assert_terminal_tool_render

        assert_terminal_tool_render(session, payload, "timeout")
    finally:
        assert hook_runtime.clear_canonical_turn_id(token)
        runtime.close()


@pytest.mark.parametrize("mode", ["normal", "raises"])
def test_official_dispatch_sets_and_restores_exact_tool_context(
    official_clarify, monkeypatch, mode
):
    approval = approval_scope(monkeypatch)
    outer = approval.set_current_observability_context(
        turn_id="outer-turn", tool_call_id="outer-call"
    )
    session = approval.set_current_session_key("synthetic-gateway")
    seen = []

    def callback():
        seen.append(
            (
                approval._approval_turn_id.get(),
                approval._approval_tool_call_id.get(),
                approval.get_current_session_key(),
            )
        )
        if mode == "raises":
            raise RuntimeError("synthetic registry error")
        return "synthetic-result"

    try:
        if mode == "raises":
            with pytest.raises(RuntimeError, match="synthetic registry error"):
                execute_dispatch(callback)
        else:
            assert execute_dispatch(callback) == "synthetic-result"
        assert seen == [("synthetic-turn", "synthetic-call", "synthetic-gateway")]
        assert (
            approval._approval_turn_id.get(),
            approval._approval_tool_call_id.get(),
        ) == ("outer-turn", "outer-call")
    finally:
        approval.reset_current_observability_context(outer)
        approval.reset_current_session_key(session)
    assert (
        approval._approval_turn_id.get() == approval._approval_tool_call_id.get() == ""
    )


@pytest.fixture
def admitted_clarify(official_clarify, monkeypatch):
    from hermes_feishu_card import hermes_plugin_runtime as runtime_module

    clarify, _ = official_clarify
    runtime, posted = active()

    class Listener:
        resolve_url = "http://127.0.0.1:12345/runtime/interactions/resolve"

        def accepts(self):
            return True

        def close(self):
            return True

        def snapshot(self):
            return {"poisoned": False}

    runtime._runtime_interaction_listener = Listener()

    def ack(payload, timeout):
        posted.append(copy.deepcopy(payload))
        return {
            "ok": True,
            "applied": True,
            "delivery": {"outcome": "delivered"},
            "runtime_admission": True,
        }

    runtime._post = ack
    entry = clarify.register(
        "synthetic-wait", "synthetic-gateway", "synthetic question", ["A"]
    )
    identity = (
        "synthetic-gateway",
        "synthetic-turn",
        "synthetic-wait",
        "a" * 64,
        entry,
    )
    assert runtime.register_patch_interaction("clarify", *identity)
    assert runtime.admit_patch_interaction(
        "clarify",
        *identity,
        lambda choice: clarify.resolve_gateway_clarify(entry.clarify_id, choice),
        {
            "prompt": "synthetic question",
            "description": "",
            "allow_custom_input": True,
            "multi_select": False,
            "timeout_seconds": 60.0,
            "options": [{"label": "A", "value": "A", "style": "default"}],
        },
    )
    clock = SimpleNamespace(value=100.0)
    monkeypatch.setattr(runtime_module, "monotonic", lambda: clock.value)
    try:
        yield runtime, posted, entry, identity, clock
    finally:
        runtime.close()


@pytest.mark.parametrize(
    "case",
    [
        "wrong-handle",
        "wrong-session",
        "wrong-turn",
        "wrong-fingerprint",
        "not-owned",
        "already-response",
        "already-event",
        "empty-call",
        "timeout-zero",
        "timeout-negative",
        "timeout-bool",
        "timeout-inf",
        "timeout-nan",
        "timeout-text",
        "closed",
    ],
)
def test_timeout_observer_rejects_unverified_sources(admitted_clarify, case):
    runtime, _posted, entry, identity, _clock = admitted_clarify
    values = list(identity)
    timeout = 1.0
    call = "synthetic-call"
    if case == "wrong-handle":
        values[4] = SimpleNamespace(response=None, event=threading.Event())
    elif case == "wrong-session":
        values[0] = "unrelated-gateway"
    elif case == "wrong-turn":
        values[1] = "unrelated-turn"
    elif case == "wrong-fingerprint":
        values[3] = "b" * 64
    elif case == "not-owned":
        next(iter(runtime._patch_interactions.values())).hfc_owned = False
    elif case == "already-response":
        entry.response = "A"
    elif case == "already-event":
        entry.event.set()
    elif case == "empty-call":
        call = ""
    elif case == "closed":
        runtime.close()
    else:
        timeout = {
            "timeout-zero": 0,
            "timeout-negative": -1,
            "timeout-bool": True,
            "timeout-inf": float("inf"),
            "timeout-nan": float("nan"),
            "timeout-text": "1",
        }[case]
    assert runtime.clarify_timeout_observer(*values, call, timeout) is None


@pytest.mark.parametrize(
    "case",
    [
        "early-none",
        "answer",
        "empty-cancel",
        "event-cancel",
        "late-response",
        "reset",
        "closed",
        "selected",
        "resolving",
    ],
)
def test_timeout_observer_does_not_guess_non_timeout_results(admitted_clarify, case):
    runtime, _posted, entry, identity, clock = admitted_clarify
    turn = runtime._turns["synthetic-turn"]
    observer = runtime.clarify_timeout_observer(*identity, "synthetic-call", 1.0)
    assert callable(observer)
    response = None
    clock.value = 102
    if case == "early-none":
        clock.value = 100.5
    elif case == "answer":
        response = "[user did not respond within 0m]"
    elif case == "empty-cancel":
        response = ""
    elif case == "event-cancel":
        entry.event.set()
    elif case == "late-response":
        entry.response = "A"
    elif case == "reset":
        runtime.handle_on_session_reset(old_session_id="synthetic-session")
    elif case == "closed":
        runtime.close()
    elif case == "selected":
        next(iter(runtime._patch_interactions.values())).selected_value = "A"
    elif case == "resolving":
        next(iter(runtime._patch_interactions.values())).resolving_value = "A"
    observer(response)
    assert turn._approval_tool_outcomes == {}


def test_timeout_display_survives_completed_wait_registry_expiry_and_replay(
    admitted_clarify, dispatcher
):
    from tests.unit.test_approval_tool_status import tool_status

    runtime, posted, _entry, identity, clock = admitted_clarify
    observer = runtime.clarify_timeout_observer(*identity, "synthetic-call", 1.0)
    assert callable(observer)
    # Completion can follow state-map expiration: the local borrowed receipt
    # must not recreate an entry or acquire another execution owner.
    runtime._patch_interactions.clear()
    clock.value = 102
    observer(None)
    observer(None)
    assert runtime._patch_interactions == {}
    assert runtime._turns["synthetic-turn"]._approval_tool_outcomes == {
        "synthetic-call": "timeout"
    }
    assert tool_status(runtime, posted, dispatcher, "{}") == ("timeout", "timeout")
    assert tool_status(runtime, posted, dispatcher, "{}") == ("timeout", "timeout")


@pytest.mark.parametrize(
    "status, expected",
    [
        ("cancelled", "cancelled"),
        ("blocked", "blocked"),
        ("timeout", "timeout"),
        ("running", "failed"),
        ("unverified", "failed"),
        (None, "timeout"),
        (False, "failed"),
    ],
)
def test_timeout_hint_preserves_explicit_dispatch_status(
    admitted_clarify, dispatcher, status, expected
):
    from tests.unit.test_approval_tool_status import tool_status

    runtime, posted, _entry, identity, clock = admitted_clarify
    observer = runtime.clarify_timeout_observer(*identity, "synthetic-call", 1.0)
    clock.value = 102
    observer(None)
    assert tool_status(runtime, posted, dispatcher, "{}", status=status) == (
        expected,
        expected,
    )


@pytest.mark.parametrize(
    "case",
    [
        "official-before-turn",
        "official-before-session",
        "official-before-empty-call",
        "official-after-turn",
        "official-after-session",
        "official-after-call",
        "canonical-before",
        "canonical-after",
        "runtime-replaced",
        "wait-raises",
    ],
)
def test_owned_wait_bridge_keeps_original_semantics_and_exact_correlation(
    admitted_clarify, official_clarify, monkeypatch, case
):
    runtime, _posted, entry, identity, clock = admitted_clarify
    approval = approval_scope(monkeypatch)
    monkeypatch.setattr(hook_runtime, "_plugin_runtime", lambda: runtime)
    local = {"_hfc_authorized": True, "platform": "feishu", "turn_id": "synthetic-turn"}
    interaction = {
        "session_identity": identity[0],
        "interaction_id": identity[2],
        "fingerprint": identity[3],
    }
    tokens = [
        hook_runtime.publish_canonical_turn_id(
            "wrong-turn" if case == "canonical-before" else "synthetic-turn"
        )
    ]
    session_token = approval.set_current_session_key(
        "wrong-session" if case == "official-before-session" else "synthetic-gateway"
    )
    original = approval.set_current_observability_context(
        turn_id="outer-turn", tool_call_id="outer-call"
    )
    calls = []

    def waiter(interaction_id, timeout):
        calls.append((interaction_id, timeout))
        clock.value = 102
        if case == "official-after-turn":
            approval._approval_turn_id.set("wrong-turn")
        elif case == "official-after-session":
            approval._approval_session_key.set("wrong-session")
        elif case == "official-after-call":
            approval._approval_tool_call_id.set("wrong-call")
        elif case == "canonical-after":
            assert hook_runtime.clear_canonical_turn_id(tokens.pop())
            tokens.append(hook_runtime.publish_canonical_turn_id("wrong-turn"))
        elif case == "runtime-replaced":
            monkeypatch.setattr(hook_runtime, "_plugin_runtime", lambda: object())
        elif case == "wait-raises":
            raise RuntimeError("original wait canary")
        return None

    def tool():
        return hook_runtime.wait_for_owned_clarify(
            local, interaction, entry, waiter, 1.0
        )

    try:
        kwargs = (
            {"turn_id": "wrong-turn"}
            if case == "official-before-turn"
            else {"tool_call_id": ""}
            if case == "official-before-empty-call"
            else {}
        )
        if case == "wait-raises":
            with pytest.raises(RuntimeError, match="original wait canary"):
                execute_dispatch(tool, **kwargs)
        else:
            assert execute_dispatch(tool, **kwargs) is None
        assert calls == [("synthetic-wait", 1.0)]
        assert runtime._turns["synthetic-turn"]._approval_tool_outcomes == {}
    finally:
        approval.reset_current_observability_context(original)
        approval.reset_current_session_key(session_token)
        for token in reversed(tokens):
            assert hook_runtime.clear_canonical_turn_id(token)


def test_clarify_timeout_display_outcomes_keep_existing_128_bound(
    admitted_clarify, dispatcher
):
    from tests.unit.test_approval_tool_status import tool_status

    runtime, posted, _entry, identity, clock = admitted_clarify
    for index in range(129):
        observer = runtime.clarify_timeout_observer(*identity, f"call-{index}", 1.0)
        assert callable(observer)
        clock.value += 2.0
        observer(None)
    turn = runtime._turns["synthetic-turn"]
    assert len(turn._approval_tool_outcomes) == 128
    assert turn._approval_outcome_overflow is True
    assert tool_status(runtime, posted, dispatcher, "{}", call="call-127") == (
        "timeout",
        "timeout",
    )
    assert tool_status(runtime, posted, dispatcher, "{}", call="call-128") == (
        "unverified",
        "unverified",
    )
