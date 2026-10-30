from __future__ import annotations

import ast
import copy
import json
import logging
import os
from pathlib import Path
import subprocess
from types import ModuleType
import sys
import time
from dataclasses import replace
import gc
import weakref

import pytest

from hermes_feishu_card import hermes_plugin_runtime as runtime_module
from hermes_feishu_card.events import SidecarEvent
from hermes_feishu_card.session import CardSession


@pytest.fixture
def dispatcher(monkeypatch):
    root = Path(os.environ["HFC_FIXED_TAG_SOURCE_ROOT"])
    assert (
        subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=root, text=True
        ).strip()
        == "3c27eb6234bf91b8ceee9e9071591b31e9b148cb"
    )
    source = subprocess.check_output(["git", "show", "HEAD:model_tools.py"], cwd=root)
    tree = ast.parse(source)
    nodes = [
        copy.deepcopy(n)
        for n in tree.body
        if isinstance(n, ast.FunctionDef)
        and n.name in {"_tool_result_observer_fields", "_emit_post_tool_call_hook"}
    ]
    assert len(nodes) == 2
    # Execute the exact official observer dispatcher; imports/framework registry
    # are isolated, no model/tool execution or production Hermes modules loaded.
    values = {"json": json, "logger": logging.getLogger(__name__)}
    for node in nodes:
        node.returns = None
        for arg in node.args.args + node.args.kwonlyargs:
            arg.annotation = None
    exec(
        compile(
            ast.fix_missing_locations(ast.Module(body=nodes, type_ignores=[])),
            "<actual-official-post-tool-dispatcher>",
            "exec",
        ),
        values,
    )
    lifecycle = ModuleType("hermes_cli.lifecycle")
    lifecycle.has_hook = lambda name: name == "post_tool_call"
    monkeypatch.setitem(sys.modules, "hermes_cli.lifecycle", lifecycle)
    return values, lifecycle


def active():
    posted = []
    runtime = runtime_module.PluginRuntime(
        post=lambda p, t: (
            posted.append(copy.deepcopy(p)) or {"ok": True, "applied": True}
        )
    )
    assert runtime.bind_ingress_from_values(
        "default",
        "fallback_default",
        "synthetic-session",
        "synthetic-gateway",
        "generation",
        "synthetic-chat",
        "synthetic-input",
        "synthetic-input",
        "",
    )
    runtime.handle_pre_llm_call(
        session_id="synthetic-session", turn_id="synthetic-turn", platform="feishu"
    )
    return runtime, posted


def approval():
    return dict(
        session_key="synthetic-gateway",
        turn_id="synthetic-turn",
        tool_call_id="synthetic-call",
        command="synthetic marker",
        surface="gateway",
    )


def tool_status(
    runtime,
    posted,
    dispatcher,
    result,
    *,
    status=None,
    call="synthetic-call",
    session_id="synthetic-session",
):
    values, lifecycle = dispatcher
    lifecycle.invoke_hook = lambda name, **kwargs: runtime.handle_post_tool_call(
        **kwargs
    )
    kwargs = dict(
        function_name="synthetic_marker",
        function_args={},
        result=result,
        session_id=session_id,
        turn_id="synthetic-turn",
        tool_call_id=call,
        duration_ms=8210,
    )
    if status is not None:
        kwargs["status"] = status
    before = sum(
        p["event"] == "tool.updated" and p["data"].get("call_id") == call
        for p in posted
    )
    values["_emit_post_tool_call_hook"](**kwargs)
    deadline = time.monotonic() + 1
    while (
        sum(
            p["event"] == "tool.updated" and p["data"].get("call_id") == call
            for p in posted
        )
        <= before
        and time.monotonic() < deadline
    ):
        time.sleep(0.001)
    assert (
        sum(
            p["event"] == "tool.updated" and p["data"].get("call_id") == call
            for p in posted
        )
        > before
    )
    payload = next(
        p
        for p in reversed(posted)
        if p["event"] == "tool.updated" and p["data"].get("call_id") == call
    )
    event = SidecarEvent.from_dict(payload)
    session = CardSession(
        conversation_id=event.conversation_id,
        message_id=event.message_id,
        chat_id=event.chat_id,
    )
    assert session.apply(event)
    if payload["data"]["status"] in {"blocked", "timeout", "unverified"}:
        assert_terminal_tool_render(session, payload, payload["data"]["status"])
    return payload["data"]["status"], session.tools[call].status


@pytest.mark.parametrize(
    "choice,expected",
    [
        ("deny", "blocked"),
        ("timeout", "timeout"),
        ("once", "completed"),
        ("session", "completed"),
        ("always", "completed"),
    ],
)
@pytest.mark.parametrize(
    "result",
    [
        {"approved": False, "outcome": "denied", "writes": 0},
        {"error": "synthetic denied"},
        {"approved": "false"},
        "free text",
        [False],
        None,
    ],
)
def test_actual_dispatcher_authoritative_approval_controls_tool_status(
    dispatcher, choice, expected, result
):
    runtime, posted = active()
    try:
        exact = approval()
        runtime.handle_pre_approval_request(**exact)
        runtime.handle_post_approval_response(**exact, choice=choice)
        # Official dispatcher derives ok/error from the actual result before HFC.
        encoded = json.dumps(result) if isinstance(result, (dict, list)) else result
        actual = tool_status(runtime, posted, dispatcher, encoded)
        wanted = (
            "failed"
            if expected == "completed"
            and isinstance(result, dict)
            and result.get("error")
            else expected
        )
        assert actual == (wanted, wanted)
    finally:
        runtime.close()


@pytest.mark.parametrize(
    "status,expected",
    [
        ("ok", "blocked"),
        ("error", "blocked"),
        ("cancelled", "cancelled"),
        ("timeout", "timeout"),
        ("blocked", "blocked"),
        ("unexpected", "failed"),
    ],
)
def test_explicit_dispatch_status_only_ok_error_are_overridden(
    dispatcher, status, expected
):
    runtime, posted = active()
    try:
        exact = approval()
        runtime.handle_pre_approval_request(**exact)
        runtime.handle_post_approval_response(**exact, choice="deny")
        assert tool_status(runtime, posted, dispatcher, "not JSON", status=status) == (
            expected,
            expected,
        )
    finally:
        runtime.close()


@pytest.mark.parametrize(
    "mismatch",
    ["missing", "session_key", "turn_id", "tool_call_id", "command", "surface"],
)
def test_unmatched_authoritative_approval_never_changes_tool_result(
    dispatcher, mismatch
):
    runtime, posted = active()
    try:
        exact = approval()
        if mismatch != "missing":
            runtime.handle_pre_approval_request(**exact)
        wrong = exact.copy()
        if mismatch != "missing":
            wrong[mismatch] = "another-synthetic-value"
        runtime.handle_post_approval_response(**wrong, choice="deny")
        assert tool_status(
            runtime,
            posted,
            dispatcher,
            json.dumps({"approved": False, "outcome": "denied"}),
        ) == ("completed", "completed")
    finally:
        runtime.close()


def test_other_call_does_not_consume_matched_denial(dispatcher):
    runtime, posted = active()
    try:
        exact = approval()
        runtime.handle_pre_approval_request(**exact)
        runtime.handle_post_approval_response(**exact, choice="deny")
        assert tool_status(runtime, posted, dispatcher, "{}", call="other-call") == (
            "completed",
            "completed",
        )
        assert tool_status(runtime, posted, dispatcher, "{}") == ("blocked", "blocked")
    finally:
        runtime.close()


@pytest.mark.parametrize(
    "choice,expected", [("deny", "blocked"), ("timeout", "timeout")]
)
def test_hfc_owned_approval_still_supplies_authoritative_tool_outcome(
    dispatcher, choice, expected
):
    runtime, posted = active()
    try:
        exact = approval()
        runtime.handle_pre_approval_request(**exact)
        key = runtime._approval_values(exact)
        runtime._pending_approvals[key] = replace(
            runtime._pending_approvals[key], hfc_owned=True
        )
        runtime.handle_post_approval_response(**exact, choice=choice)
        assert tool_status(runtime, posted, dispatcher, "{}") == (expected, expected)
    finally:
        runtime.close()


def test_wrong_tool_session_cannot_consume_outcome(dispatcher):
    runtime, posted = active()
    try:
        exact = approval()
        runtime.handle_pre_approval_request(**exact)
        runtime.handle_post_approval_response(**exact, choice="deny")
        values, lifecycle = dispatcher
        lifecycle.invoke_hook = lambda name, **kwargs: runtime.handle_post_tool_call(
            **kwargs
        )
        values["_emit_post_tool_call_hook"](
            function_name="synthetic_marker",
            function_args={},
            result="{}",
            session_id="other-session",
            turn_id="synthetic-turn",
            tool_call_id="synthetic-call",
        )
        assert (
            runtime._turns["synthetic-turn"]._approval_tool_outcomes["synthetic-call"]
            == "blocked"
        )
        assert not any(p["event"] == "tool.updated" for p in posted)
        assert tool_status(runtime, posted, dispatcher, "{}") == ("blocked", "blocked")
    finally:
        runtime.close()


def test_pre_tool_event_does_not_consume_terminal_approval_outcome(dispatcher):
    runtime, posted = active()
    try:
        exact = approval()
        runtime.handle_pre_approval_request(**exact)
        runtime.handle_post_approval_response(**exact, choice="deny")
        runtime.handle_pre_tool_call(
            turn_id="synthetic-turn",
            tool_call_id="synthetic-call",
            tool_name="synthetic_marker",
        )
        assert tool_status(runtime, posted, dispatcher, "{}") == ("blocked", "blocked")
    finally:
        runtime.close()


def test_matched_approval_outcomes_are_bounded_and_follow_turn_cleanup(dispatcher):
    runtime, posted = active()
    try:
        for i in range(130):
            exact = approval()
            exact["tool_call_id"] = f"call-{i}"
            runtime.handle_pre_approval_request(**exact)
            # Wait for admission queue to finish, without terminal drain closing it.
            coordinator = runtime._coordinators["synthetic-turn"]
            deadline = time.monotonic() + 1
            while coordinator._queue.unfinished_tasks and time.monotonic() < deadline:
                time.sleep(0.001)
            runtime.handle_post_approval_response(**exact, choice="deny")
            deadline = time.monotonic() + 1
            while coordinator._queue.unfinished_tasks and time.monotonic() < deadline:
                time.sleep(0.001)
        turn = runtime._turns["synthetic-turn"]
        ref = weakref.ref(turn)
        assert len(turn._approval_tool_outcomes) == 128
        assert turn._approval_outcome_overflow is True
        assert tool_status(runtime, posted, dispatcher, "{}", call="call-127") == (
            "blocked",
            "blocked",
        )
        assert tool_status(runtime, posted, dispatcher, "{}", call="call-128") == (
            "unverified",
            "unverified",
        )
        assert tool_status(
            runtime,
            posted,
            dispatcher,
            json.dumps({"writes": 1}),
            call="new-after-overflow",
        ) == ("unverified", "unverified")
        assert tool_status(
            runtime,
            posted,
            dispatcher,
            "{}",
            call="explicit-cancel-after-overflow",
            status="cancelled",
        ) == ("cancelled", "cancelled")
        assert len(runtime._turns) == 1
        assert len(runtime._pending_approvals) == 0
        del turn, coordinator
        runtime.handle_on_session_reset(old_session_id="synthetic-session")
        gc.collect()
        assert not runtime._turns and ref() is None
        assert runtime.bind_ingress_from_values(
            "default",
            "fallback_default",
            "synthetic-session",
            "synthetic-gateway",
            "generation-new",
            "synthetic-chat",
            "synthetic-input-new",
            "synthetic-input-new",
            "",
        )
        runtime.handle_pre_llm_call(
            session_id="synthetic-session", turn_id="synthetic-turn", platform="feishu"
        )
        runtime.handle_post_approval_response(**approval(), choice="deny")
        assert tool_status(runtime, posted, dispatcher, "{}") == (
            "completed",
            "completed",
        )
    finally:
        runtime.close()


@pytest.mark.asyncio
async def test_wrong_session_cannot_poison_terminal_event_fence(dispatcher, tmp_path):
    from aiohttp.test_utils import TestClient, TestServer
    from hermes_feishu_card.server import create_app, SESSIONS_KEY
    import asyncio

    class Transport:
        async def send_card(self, chat_id, card, **kwargs):
            return "synthetic-card"

        async def update_card_message(self, message_id, card):
            pass

    runtime, posted = active()
    values, lifecycle = dispatcher
    lifecycle.invoke_hook = lambda name, **kwargs: runtime.handle_post_tool_call(
        **kwargs
    )
    client = TestClient(
        TestServer(
            create_app(
                Transport(),
                card_config={"flush_interval_ms": 1},
                session_store_directory=tmp_path / "sessions",
            )
        )
    )
    await client.start_server()
    try:
        exact = approval()
        runtime.handle_pre_approval_request(**exact)
        runtime.handle_post_approval_response(**exact, choice="deny")
        for session in ("wrong-session", "synthetic-session"):
            values["_emit_post_tool_call_hook"](
                function_name="synthetic_marker",
                function_args={},
                result="{}",
                session_id=session,
                turn_id="synthetic-turn",
                tool_call_id="synthetic-call",
            )
        await asyncio.to_thread(runtime.drain_observers, 1)
        responses = []
        for payload in posted:
            response = await client.post("/events", json=payload)
            responses.append((payload["event"], response.status, await response.json()))
        assert all(status == 200 for _event, status, _body in responses), responses
        sessions = list(client.app[SESSIONS_KEY].values())
        assert len(sessions) == 1
        assert sessions[0].tools["synthetic-call"].status == "blocked"
    finally:
        await asyncio.to_thread(runtime.close)
        await client.close()


def test_wrong_session_without_approval_keeps_existing_observer_contract(dispatcher):
    runtime, posted = active()
    try:
        assert tool_status(
            runtime, posted, dispatcher, "{}", session_id="other-session"
        ) == ("completed", "completed")
    finally:
        runtime.close()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "choice,expected", [("deny", "blocked"), ("timeout", "timeout")]
)
async def test_lost_first_tool_observer_retries_authoritative_status_and_exact_payload_replays(
    dispatcher, tmp_path, choice, expected
):
    import asyncio
    import threading
    from urllib.request import Request, build_opener, ProxyHandler
    from aiohttp.test_utils import TestClient, TestServer
    from hermes_feishu_card.server import create_app, SESSIONS_KEY

    class Transport:
        async def send_card(self, chat_id, card, **kwargs):
            return "synthetic-card"

        async def update_card_message(self, message_id, card):
            pass

    runtime, posted = active()
    values, lifecycle = dispatcher
    lifecycle.invoke_hook = lambda name, **kwargs: runtime.handle_post_tool_call(
        **kwargs
    )
    client = TestClient(
        TestServer(
            create_app(
                Transport(),
                card_config={"flush_interval_ms": 1},
                session_store_directory=tmp_path / "sessions",
            )
        )
    )
    await client.start_server()
    dropped = threading.Event()
    acknowledgements = []
    tool_attempts = []
    opener = build_opener(ProxyHandler({}))

    def post(payload, timeout):
        if payload["event"] == "tool.updated":
            tool_attempts.append(copy.deepcopy(payload))
            if len(tool_attempts) == 1:
                dropped.set()
                return None  # No server request: the first observer is actually lost.
        request = Request(
            str(client.make_url("/events")),
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"},
        )
        with opener.open(request, timeout=timeout) as response:
            answer = json.loads(response.read())
        acknowledgements.append((payload["event"], answer))
        return answer

    try:
        response = await client.post("/events", json=posted[0])
        assert response.status == 200
        runtime._post = post
        exact = approval()
        runtime.handle_pre_approval_request(**exact)
        runtime.handle_post_approval_response(**exact, choice=choice)

        def emit():
            values["_emit_post_tool_call_hook"](
                function_name="synthetic_marker",
                function_args={},
                result="{}",
                session_id="synthetic-session",
                turn_id="synthetic-turn",
                tool_call_id="synthetic-call",
            )

        emit()
        assert await asyncio.to_thread(dropped.wait, 1)
        emit()
        await asyncio.to_thread(runtime.drain_observers, 2)
        assert len(tool_attempts) == 2
        assert [p["data"]["status"] for p in tool_attempts] == [expected, expected]
        assert any(
            event == "tool.updated" and body.get("applied") is True
            for event, body in acknowledgements
        )
        # Actual byte-identical transport replay must use the same sequence/time.
        replay = await client.post("/events", json=tool_attempts[-1])
        assert replay.status == 200
        sessions = list(client.app[SESSIONS_KEY].values())
        assert len(sessions) == 1
        assert sessions[0].tools["synthetic-call"].status == expected
        assert_terminal_tool_render(sessions[0], tool_attempts[-1], expected)
    finally:
        await asyncio.to_thread(runtime.close)
        await client.close()


def assert_terminal_tool_render(session, payload, status):
    from hermes_feishu_card.render import render_card

    expected = {"blocked": "已拒绝", "timeout": "已超时", "unverified": "结果待核对"}[
        status
    ]
    name = payload["data"]["name"]
    call = payload["data"]["call_id"]

    def strings(value):
        if isinstance(value, str):
            return [value]
        if isinstance(value, dict):
            return [s for v in value.values() for s in strings(v)]
        if isinstance(value, list):
            return [s for v in value for s in strings(v)]
        return []

    def check():
        for presentation in ("classic", "task"):
            card = render_card(
                session, presentation=presentation, timeline_expanded=True
            )
            rows = [s for s in strings(card) if name in s]
            assert rows, (presentation, status, card)
            assert any(expected in row for row in rows), (presentation, status, rows)
            assert all(
                "✓" not in row and "⏳" not in row and "进行中" not in row
                for row in rows
            ), (presentation, status, rows)

    check()
    late = copy.deepcopy(payload)
    late.update(
        sequence=payload["sequence"] + 1,
        event_id="synthetic-late-start",
        phase="started",
    )
    late["data"].update(status="pending")
    assert session.apply(SidecarEvent.from_dict(late))
    assert session.tools[call].status == status
    terminal = copy.deepcopy(payload)
    terminal.update(
        event="message.completed",
        sequence=payload["sequence"] + 2,
        event_id="synthetic-final",
        phase="terminal",
    )
    terminal["data"] = {"answer": "SYNTHETIC_FINAL_END"}
    assert session.apply(SidecarEvent.from_dict(terminal))
    assert session.tools[call].status == status
    check()
