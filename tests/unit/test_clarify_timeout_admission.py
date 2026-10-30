"""Real loopback admission added after the window6 timeout display failure."""
import ast
import asyncio
import copy
import inspect
import time

import pytest

from aiohttp.test_utils import TestClient, TestServer

from hermes_feishu_card import hermes_plugin_runtime as runtime_module
from hermes_feishu_card.runtime_interaction_transport import RuntimeInteractionListener
from tests.integration.test_server import FakeFeishuClient, create_app, TRANSPORT_ROOT_SECRET
from tests.unit.test_clarify_timeout_status import (
    official_clarify as official_clarify,
    dispatcher as dispatcher,
    test_owned_real_wait_timeout_must_not_be_completed as original_contract,
)


HTTP_TRANSPORT_TIMEOUT_SECONDS = 0.8
HTTP_CLARIFY_TIMEOUT_SECONDS = 1.0


def _real_http_contract(function):
    """Share the I/O substitutions and budget between both extracted paths."""
    assert HTTP_CLARIFY_TIMEOUT_SECONDS > HTTP_TRANSPORT_TIMEOUT_SECONDS
    body = []
    removed = 0
    for node in function.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Attribute) and isinstance(t.value, ast.Name)
            and t.value.id == "runtime" and t.attr in {"_post", "_runtime_interaction_listener"}
            for t in node.targets
        ):
            removed += 1
        else:
            body.append(node)
    assert removed == 2
    function.body = body
    replaced = 0
    for node in ast.walk(function):
        if isinstance(node, ast.Constant) and type(node.value) is float and node.value == 0.04:
            node.value = HTTP_CLARIFY_TIMEOUT_SECONDS
            replaced += 1
    assert replaced == 1
    return function


@pytest.mark.parametrize("specialized", [False, True], ids=["generic", "specialized"])
@pytest.mark.parametrize("admission_elapsed", [0.0, 0.08], ids=["immediate", "modeled-80ms"])
async def test_original_timeout_contract_with_actual_signed_sidecar_admission(
    official_clarify, dispatcher, monkeypatch, tmp_path, specialized, admission_elapsed
):
    monkeypatch.setenv("HERMES_FEISHU_CARD_STATE_DIR", str(tmp_path / "state"))
    client = TestClient(TestServer(create_app(
        FakeFeishuClient(), session_store_directory=tmp_path / "sessions",
        event_auth_required=True,
    )))
    await client.start_server()
    transport = runtime_module.SignedEventTransport(
        event_url=str(client.make_url("/events")), timeout_seconds=HTTP_TRANSPORT_TIMEOUT_SECONDS,
        secret_reader=lambda: TRANSPORT_ROOT_SECRET,
    )
    receipts = []
    observed_budgets = []
    runtimes = []

    def active():
        posted = []
        admission_offset = [0.0]

        def post(payload, timeout):
            posted.append(copy.deepcopy(payload))
            receipt = transport(payload, timeout)
            receipts.append((payload["event"], receipt))
            if payload["event"] == "interaction.requested":
                observed_budgets.append(payload["data"]["timeout_seconds"])
                # Model admission overhead without sleeping or replacing the
                # original Hermes wait's real monotonic deadline.
                admission_offset[0] += admission_elapsed
            return receipt

        runtime = runtime_module.PluginRuntime(post=post, now=lambda: time.time() + admission_offset[0])
        runtimes.append(runtime)
        assert runtime.bind_ingress_from_values(
            "default", "fallback_default", "synthetic-session", "synthetic-gateway",
            "generation", "synthetic-chat", "synthetic-input", "synthetic-input", "",
        )
        runtime.handle_pre_llm_call(
            session_id="synthetic-session", turn_id="synthetic-turn", platform="feishu",
        )
        assert runtime.turn_state("synthetic-turn") is runtime_module.TurnState.CARD_ACTIVE
        listener = RuntimeInteractionListener(TRANSPORT_ROOT_SECRET, runtime.resolve_runtime_interaction_payload)
        listener.start()
        runtime._runtime_interaction_listener = listener
        return runtime, posted

    # Reuse the exact prior end-to-end contract, changing only its admission I/O
    # seam and fake listener. Its dispatcher ContextVars, canonical waiter,
    # installed renderer callback, posthook, event parser and card assertions stay.
    tree = ast.parse(inspect.getsource(original_contract))
    function = tree.body[0]
    assert isinstance(function, ast.FunctionDef)
    function.name = "exercise"
    # The real signed HTTP contract has a transport budget plus scheduling
    # margin. Pure waiter contracts retain their original 40ms deadline.
    _real_http_contract(function)
    namespace = dict(original_contract.__globals__, active=active)
    exec(compile(ast.fix_missing_locations(tree), "<prior-contract-real-http-admission>", "exec"), namespace)
    try:
        if specialized:
            exercise = _specialized_contract(
                official_clarify, dispatcher, monkeypatch, tmp_path, active_override=active,
            )
            await asyncio.to_thread(exercise)
        else:
            await asyncio.to_thread(namespace["exercise"], official_clarify, dispatcher, monkeypatch, tmp_path)
        admissions = [r for event, r in receipts if event == "interaction.requested"]
        assert len(admissions) == 1
        assert observed_budgets == [HTTP_CLARIFY_TIMEOUT_SECONDS]
        assert admissions[0] == {
            "ok": True, "applied": True,
            "delivery": {"outcome": "delivered"}, "runtime_admission": True,
        }
        assert all(runtime._closed for runtime in runtimes)
    finally:
        for runtime in runtimes:
            runtime.close()
        await client.close()


def _specialized_contract(
    official_clarify, dispatcher, monkeypatch, tmp_path, *, active_override=None,
):
    """The actual agent-specialized helper never enters model_tools dispatch."""
    import __future__
    import subprocess
    import sys
    import threading
    import types
    from pathlib import Path
    from tests.unit.test_clarify_timeout_status import F, SHA

    source = subprocess.check_output(
        ["git", "show", f"{SHA}:agent/tool_executor.py"], cwd=F,
    )
    module = ast.parse(source)
    helper = next(n for n in module.body if isinstance(n, ast.FunctionDef)
                  and n.name == "_run_agent_tool_execution_middleware")
    assert "set_current_observability_context" not in ast.unparse(helper)
    assert "_approval_turn_id" not in source.decode()
    middleware = types.ModuleType("hermes_cli.middleware")
    middleware.apply_tool_request_middleware = lambda _name, args, **kw: types.SimpleNamespace(payload=args, trace=[])
    middleware.run_tool_execution_middleware = lambda _name, args, next_call, **kw: next_call(args)
    plugins = types.ModuleType("hermes_cli.plugins")
    def resolve_pre_tool_block(name, args, **kwargs):
        from hermes_feishu_card import hook_runtime
        hook_runtime._plugin_runtime().handle_pre_tool_call(tool_name=name, args=args, **kwargs)
        return None
    plugins.resolve_pre_tool_block = resolve_pre_tool_block
    hermes_cli = types.ModuleType("hermes_cli")
    hermes_cli.__path__ = []
    relay = types.SimpleNamespace(execute=lambda _name, args, pipeline, **kw: (pipeline(args), args))
    agent_package = types.ModuleType("agent")
    agent_package.relay_tools = relay
    for name, value in [("hermes_cli", hermes_cli), ("hermes_cli.middleware", middleware),
                        ("hermes_cli.plugins", plugins), ("agent", agent_package)]:
        monkeypatch.setitem(sys.modules, name, value)
    globals_ = {"threading": threading, "json": __import__("json"),
                "_begin_tool_execution": lambda *a, **kw: None,
                "_ManagedToolResult": types.SimpleNamespace}
    exec(compile(ast.fix_missing_locations(ast.Module(body=[copy.deepcopy(helper)], type_ignores=[])),
                 "<exact-agent-specialized-dispatch>", "exec",
                 flags=__future__.annotations.compiler_flag), globals_)
    current_agent = types.SimpleNamespace(
        session_id="synthetic-session", _current_turn_id="synthetic-turn",
        _current_api_request_id="synthetic-api",
        _tool_guardrails=types.SimpleNamespace(before_call=lambda *a: types.SimpleNamespace(allows_execution=True)),
    )

    def specialized_dispatch(registry_callback, *, post_tool_hook, **kwargs):
        result = globals_["_run_agent_tool_execution_middleware"](
            current_agent, function_name="clarify", function_args={"question": "synthetic question", "choices": ["A"]},
            effective_task_id="synthetic-task", tool_call_id="synthetic-call",
            execute=lambda args: registry_callback(),
        ).result
        # Actual helper's terminal emitter delegates this same canonical posthook.
        post_tool_hook(function_name="clarify", function_args={}, result=result,
                       task_id="synthetic-task", session_id="synthetic-session",
                       turn_id="synthetic-turn", tool_call_id="synthetic-call",
                       api_request_id="synthetic-api", duration_ms=40)
        return result

    contract_source = inspect.getsource(original_contract).replace(
        'p["event"] == "tool.updated"',
        'p["event"] == "tool.updated" and p["phase"] == "terminal"',
    )
    tree = ast.parse(contract_source)
    tree.body[0].name = "exercise_specialized"
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and node.value in {"outer-turn", "outer-call"}:
            node.value = ""
        if isinstance(node, ast.Assert) and isinstance(node.test, ast.Compare) and isinstance(node.test.left, ast.Name) and node.test.left.id == "bound":
            node.test.comparators = [ast.parse('[("", "", "synthetic-gateway")]', mode="eval").body]
    if active_override is not None:
        _real_http_contract(tree.body[0])
    namespace = dict(original_contract.__globals__, execute_dispatch=specialized_dispatch)
    if active_override is not None:
        namespace["active"] = active_override
    exec(compile(ast.fix_missing_locations(tree), "<prior-contract-specialized-dispatch>", "exec"), namespace)
    return lambda: namespace["exercise_specialized"](official_clarify, dispatcher, monkeypatch, tmp_path)


def test_actual_specialized_clarify_dispatch_cannot_depend_on_generic_approval_context(
    official_clarify, dispatcher, monkeypatch, tmp_path,
):
    _specialized_contract(official_clarify, dispatcher, monkeypatch, tmp_path)()


from tests.unit.test_clarify_timeout_status import (
    admitted_clarify as admitted_clarify, approval_scope,
)


@pytest.mark.parametrize("ack_elapsed, expected", [(0.08, True), (1.01, False)])
def test_admission_ack_must_still_precede_descriptor_deadline(
    admitted_clarify, monkeypatch, ack_elapsed, expected,
):
    runtime, _posted, entry, identity, _clock = admitted_clarify
    runtime._patch_interactions.clear()
    assert runtime.register_patch_interaction("clarify", *identity)
    clock = [time.time()]
    started = clock[0]
    monkeypatch.setattr(runtime, "_now", lambda: clock[0])
    descriptors = []
    def acknowledged(payload, _timeout):
        descriptors.append(payload["data"]["_hfc_runtime_admission"])
        clock[0] += ack_elapsed
        return {"ok": True, "applied": True,
                "delivery": {"outcome": "delivered"}, "runtime_admission": True}
    runtime._post = acknowledged
    assert runtime.admit_patch_interaction(
        "clarify", *identity, lambda _choice: True,
        {"prompt": "synthetic question", "description": "", "allow_custom_input": True,
         "multi_select": False, "timeout_seconds": HTTP_CLARIFY_TIMEOUT_SECONDS,
         "options": [{"label": "A", "value": "A", "style": "default"}]},
    ) is expected
    assert len(descriptors) == 1
    assert descriptors[0]["expires_at"] == started + HTTP_CLARIFY_TIMEOUT_SECONDS


@pytest.fixture
def correlated(admitted_clarify):
    from hashlib import sha256
    runtime, posted, entry, old_identity, clock = admitted_clarify
    fingerprint = sha256(b"synthetic question\0['A']\0False").hexdigest()
    identity = (*old_identity[:3], fingerprint, entry)
    # Replace the shared fixture placeholder before constructing this exact state.
    runtime._patch_interactions.clear()
    assert runtime.register_patch_interaction("clarify", *identity)
    assert runtime.admit_patch_interaction(
        "clarify", *identity, lambda _choice: True,
        {"prompt": "synthetic question", "description": "", "allow_custom_input": True,
         "multi_select": False, "timeout_seconds": 60.0,
         "options": [{"label": "A", "value": "A", "style": "default"}]},
    )
    return runtime, entry, identity, clock


def pretool(runtime, **patch):
    args = {"tool_name": "clarify", "tool_call_id": "synthetic-call",
            "turn_id": "synthetic-turn", "session_id": "synthetic-session",
            "args": {"question": "synthetic question", "choices": ["A"]}}
    args.update(patch)
    runtime.handle_pre_tool_call(**args)


def wait_without_generic_context(monkeypatch, correlated, *, turn="", call="", after=None):
    from hermes_feishu_card import hook_runtime
    runtime, entry, identity, clock = correlated
    approval = approval_scope(monkeypatch)
    monkeypatch.setattr(hook_runtime, "_plugin_runtime", lambda: runtime)
    session_token = approval.set_current_session_key("synthetic-gateway")
    correlation = approval.set_current_observability_context(turn_id=turn, tool_call_id=call)
    canonical = hook_runtime.publish_canonical_turn_id("synthetic-turn")
    def waiter(_id, timeout):
        clock.value += timeout + 0.01
        if after:
            after()
        return None
    try:
        assert hook_runtime.wait_for_owned_clarify(
            {"_hfc_authorized": True, "platform": "feishu", "turn_id": "synthetic-turn"},
            {"session_identity": identity[0], "interaction_id": identity[2], "fingerprint": identity[3]},
            entry, waiter, 1.0,
        ) is None
    finally:
        hook_runtime.clear_canonical_turn_id(canonical)
        approval.reset_current_observability_context(correlation)
        approval.reset_current_session_key(session_token)


@pytest.mark.parametrize("case", ["missing", "wrong-session", "wrong-turn", "wrong-tool",
    "wrong-args", "conflicting-call", "conflicting-same-call", "posttool", "replay",
    "other-thread", "nonempty-wrong-context", "partial-context", "late-posttool"])
def test_specialized_correlation_rejects_unproven_or_late_call(monkeypatch, correlated, case):
    import threading
    runtime, entry, identity, clock = correlated
    patch = {}
    if case == "wrong-session": patch["session_id"] = "wrong"
    if case == "wrong-turn": patch["turn_id"] = "wrong"
    if case == "wrong-tool": patch["tool_name"] = "other"
    if case == "wrong-args": patch["args"] = {"question": "other", "choices": ["A"]}
    if case == "other-thread":
        thread = threading.Thread(target=lambda: pretool(runtime))
        thread.start(); thread.join()
    elif case != "missing":
        pretool(runtime, **patch)
    if case == "conflicting-call": pretool(runtime, tool_call_id="second-call")
    if case == "conflicting-same-call": pretool(runtime, args={"question": "other"})
    def complete():
        runtime.handle_post_tool_call(tool_name="clarify", tool_call_id="synthetic-call",
            turn_id="synthetic-turn", session_id="synthetic-session", status="ok")
    if case in {"posttool", "replay"}: complete()
    if case == "replay": pretool(runtime)
    wait_without_generic_context(monkeypatch, correlated,
        turn="wrong" if case == "nonempty-wrong-context" else "synthetic-turn" if case == "partial-context" else "",
        call="wrong" if case == "nonempty-wrong-context" else "",
        after=complete if case == "late-posttool" else None)
    assert runtime._turns["synthetic-turn"]._approval_tool_outcomes == {}


def test_specialized_correlation_idempotence_expired_state_and_thread_reuse(monkeypatch, correlated):
    runtime, entry, identity, clock = correlated
    pretool(runtime)
    observation = runtime.clarify_tool_call_for_wait(*identity)
    assert observation is not None
    pretool(runtime)
    assert runtime.clarify_tool_call_for_wait(*identity) is observation
    # Preserve the original borrowed-state contract: registry expiry during a
    # completed wait does not discard exact still-live tool identity.
    wait_without_generic_context(monkeypatch, correlated, after=runtime._patch_interactions.clear)
    assert runtime._turns["synthetic-turn"]._approval_tool_outcomes == {"synthetic-call": "timeout"}
    runtime.handle_post_tool_call(tool_name="clarify", tool_call_id="synthetic-call",
        turn_id="synthetic-turn", session_id="synthetic-session", status="ok")
    assert not runtime.clarify_tool_call_is_current("synthetic-gateway", "synthetic-turn", observation)
    pretool(runtime)
    assert not runtime.clarify_tool_call_is_current("synthetic-gateway", "synthetic-turn", observation)
    pretool(runtime, tool_call_id="fresh-call")
    assert runtime._turns["synthetic-turn"]._clarify_tool_calls["fresh-call"] is not None


def test_specialized_correlation_is_bounded_until_turn_cleanup(correlated):
    runtime, entry, identity, clock = correlated
    for i in range(129):
        call = f"call-{i}"
        pretool(runtime, tool_call_id=call)
        runtime.handle_post_tool_call(tool_name="clarify", tool_call_id=call,
            turn_id="synthetic-turn", session_id="synthetic-session", status="ok")
    assert len(runtime._turns["synthetic-turn"]._clarify_tool_calls) == 128
    assert runtime.clarify_tool_call_for_wait(*identity) is None
    runtime.handle_on_session_reset(old_session_id="synthetic-session")
    assert "synthetic-turn" not in runtime._turns


def test_three_overlapping_calls_remain_poisoned_until_all_exact_posts(correlated):
    runtime, entry, identity, clock = correlated
    for call in ["one", "two", "three"]:
        pretool(runtime, tool_call_id=call)
        if call != "one":
            assert runtime.clarify_tool_call_for_wait(*identity) is None
    assert all(v.active and v.ambiguous for v in runtime._turns["synthetic-turn"]._clarify_tool_calls.values())
    for call in ["one", "two"]:
        runtime.handle_post_tool_call(tool_name="clarify", tool_call_id=call,
            turn_id="synthetic-turn", session_id="synthetic-session", status="ok")
        assert runtime.clarify_tool_call_for_wait(*identity) is None
    pretool(runtime, tool_call_id="four")
    assert runtime.clarify_tool_call_for_wait(*identity) is None
    for call in ["three", "four"]:
        runtime.handle_post_tool_call(tool_name="clarify", tool_call_id=call,
            turn_id="synthetic-turn", session_id="synthetic-session", status="ok")
    pretool(runtime, tool_call_id="fresh")
    assert runtime.clarify_tool_call_for_wait(*identity).tool_call_id == "fresh"


@pytest.mark.parametrize("wrong", ["tool", "thread", "session"])
def test_unrelated_posthook_cannot_release_official_correlation(correlated, wrong):
    import threading
    runtime, entry, identity, clock = correlated
    pretool(runtime)
    observation = runtime.clarify_tool_call_for_wait(*identity)
    kwargs = dict(tool_name="other" if wrong == "tool" else "clarify",
                  tool_call_id="synthetic-call", turn_id="synthetic-turn",
                  session_id="other" if wrong == "session" else "synthetic-session", status="ok")
    if wrong == "thread":
        thread = threading.Thread(target=lambda: runtime.handle_post_tool_call(**kwargs))
        thread.start();thread.join()
    else:
        runtime.handle_post_tool_call(**kwargs)
    assert runtime.clarify_tool_call_is_current("synthetic-gateway", "synthetic-turn", observation)
