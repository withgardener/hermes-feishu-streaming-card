from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import http.client
import json
import queue
import signal
import socket
import subprocess
import sys
from threading import Barrier, Event, Thread
import time
from urllib import error, request

import pytest

from hermes_feishu_card import event_auth
from hermes_feishu_card import hermes_plugin_runtime as plugin_runtime
from hermes_feishu_card.runtime_interaction_transport import (
    MAX_RUNTIME_INTERACTION_BODY_BYTES,
    RUNTIME_INTERACTION_PATH,
    RuntimeInteractionListener,
)


def active_runtime(*, now=None):
    runtime = plugin_runtime.PluginRuntime(
        post=lambda _payload, _timeout: {"ok": True, "applied": True},
        now=now or (lambda: 100.0),
    )
    assert runtime.bind_ingress_from_values(
        "default", "fallback_default", "session-1", "gateway-session-1",
        "generation-1", "oc_1", "om_1", "om_parent", "thread-1",
    )
    runtime.handle_pre_llm_call(
        session_id="session-1", turn_id="turn-1", platform="feishu"
    )
    return runtime


def interaction_args(handle, *, kind="approval", interaction_id="interaction-1"):
    return (
        kind, "gateway-session-1", "turn-1", interaction_id, "a" * 64,
        handle,
    )


def callback_body(descriptor, choice="approve"):
    return {
        "protocol": descriptor["protocol"],
        "runtime_id": descriptor["runtime_id"],
        "interaction_key": descriptor["interaction_key"],
        "token": descriptor["token"],
        "choice": choice,
        "expires_at": descriptor["expires_at"],
    }


def canonical(value):
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def post(url, secret, payload, *, nonce="runtime-callback-nonce-0001"):
    body = canonical(payload)
    headers = {"Content-Type": "application/json"}
    headers.update(event_auth.sign_runtime_interaction_request(
        secret, RUNTIME_INTERACTION_PATH, body, nonce=nonce,
    ))
    req = request.Request(url, data=body, headers=headers, method="POST")
    try:
        with request.urlopen(req, timeout=1.0) as response:
            return response.status, json.loads(response.read())
    except error.HTTPError as exc:
        return exc.code, json.loads(exc.read())


@pytest.mark.parametrize("kind", ("approval", "clarify", "slash"))
def test_real_callback_invokes_exact_resolver_and_wakes_original_wait(kind):
    secret = b"i" * 32
    runtime = active_runtime()
    handle = object()
    args = interaction_args(handle, kind=kind, interaction_id=kind)
    original_wait = Event()
    resolved = []

    def exact_resolver(choice):
        resolved.append(choice)
        original_wait.set()
        return True

    assert runtime.register_patch_interaction(*args)
    assert runtime.start_runtime_interaction_listener(secret)
    descriptor = runtime.arm_patch_interaction_descriptor(*args, exact_resolver)
    assert descriptor is not None
    status, response = post(
        descriptor["resolve_url"], secret, callback_body(descriptor)
    )

    assert original_wait.wait(timeout=0.1), "original wait must wake without poll/claim"
    assert resolved == ["approve"]
    assert (status, response) == (200, {"ok": True, "status": "resolved"})
    assert runtime.claim_patch_interaction(*args) == "approve"
    assert runtime.claim_patch_interaction(*args) is None
    runtime.close()


def test_descriptor_is_exact_opaque_deep_copied_stable_and_stores_only_digest():
    secret = b"i" * 32
    runtime = active_runtime()
    handle = object()
    args = interaction_args(handle)
    resolver = lambda _choice: True
    assert runtime.register_patch_interaction(*args)
    assert runtime.start_runtime_interaction_listener(secret)
    first = runtime.arm_patch_interaction_descriptor(*args, resolver)
    second = runtime.arm_patch_interaction_descriptor(*args, resolver)

    assert first == second and first is not second
    assert set(first) == {
        "protocol", "runtime_id", "resolve_url", "interaction_key", "token",
        "expires_at",
    }
    assert first["protocol"] == "hfc-runtime-interaction-v1"
    assert first["resolve_url"].startswith("http://127.0.0.1:")
    assert first["resolve_url"].endswith(RUNTIME_INTERACTION_PATH)
    assert all(len(first[name]) == 64 for name in (
        "runtime_id", "interaction_key", "token"
    ))
    first["runtime_id"] = "0" * 64
    assert runtime.arm_patch_interaction_descriptor(*args, resolver) == second
    state = next(iter(runtime._patch_interactions.values()))
    assert not hasattr(state, "token")
    assert second["token"] not in repr(runtime)
    assert "gateway-session-1" not in repr(second)
    assert "turn-1" not in repr(second)
    assert runtime.arm_patch_interaction_descriptor(
        *interaction_args(object()), resolver
    ) is None
    runtime.close()


def test_callback_rejects_wrong_binding_expiry_conflict_and_consumed_reopen():
    now = [100.0]
    secret = b"i" * 32
    runtime = active_runtime(now=lambda: now[0])
    args = interaction_args(object())
    calls = []
    resolver = lambda choice: calls.append(choice) or True
    assert runtime.register_patch_interaction(*args)
    assert runtime.start_runtime_interaction_listener(secret)
    descriptor = runtime.arm_patch_interaction_descriptor(*args, resolver)
    body = callback_body(descriptor)

    for index, mutation in enumerate((
        {"runtime_id": "0" * 64}, {"interaction_key": "0" * 64},
        {"token": "0" * 64}, {"protocol": "hfc-runtime-interaction-v0"},
        {"expires_at": descriptor["expires_at"] - 1}, {"choice": ""},
    )):
        status, response = post(
            descriptor["resolve_url"], secret, dict(body, **mutation),
            nonce=f"runtime-callback-wrong-{index:04d}",
        )
        assert status == 409
        assert response == {"ok": False, "status": "rejected"}
    assert calls == []

    assert post(descriptor["resolve_url"], secret, body,
                nonce="runtime-callback-correct-0001")[0] == 200
    assert post(descriptor["resolve_url"], secret, body,
                nonce="runtime-callback-correct-0002")[0] == 200
    assert calls == ["approve"]
    assert post(descriptor["resolve_url"], secret, dict(body, choice="deny"),
                nonce="runtime-callback-conflict-001")[0] == 409
    assert runtime.claim_patch_interaction(*args) == "approve"
    assert runtime.register_patch_interaction(*args) is False
    assert post(descriptor["resolve_url"], secret, body,
                nonce="runtime-callback-consumed-001")[0] == 409

    other = interaction_args(object(), interaction_id="expired")
    assert runtime.register_patch_interaction(*other)
    expired = runtime.arm_patch_interaction_descriptor(*other, resolver)
    now[0] = expired["expires_at"]
    assert post(expired["resolve_url"], secret, callback_body(expired),
                nonce="runtime-callback-expired-001")[0] == 409
    runtime.close()


def test_replay_and_resolver_failure_are_sanitized_and_do_not_mutate():
    secret = b"i" * 32
    runtime = active_runtime()
    args = interaction_args(object())
    calls = []

    def failing(choice):
        calls.append(choice)
        raise RuntimeError("PRIVATE-CANARY")

    assert runtime.register_patch_interaction(*args)
    assert runtime.start_runtime_interaction_listener(secret)
    descriptor = runtime.arm_patch_interaction_descriptor(*args, failing)
    body = callback_body(descriptor)
    first = post(descriptor["resolve_url"], secret, body)
    replay = post(descriptor["resolve_url"], secret, body)
    fresh = post(descriptor["resolve_url"], secret, body,
                 nonce="runtime-callback-fresh-0001")
    assert first == (409, {"ok": False, "status": "rejected"})
    assert replay == (401, {"ok": False, "status": "rejected"})
    assert fresh == (409, {"ok": False, "status": "rejected"})
    assert calls == ["approve", "approve"]
    assert runtime.claim_patch_interaction(*args) is None
    runtime.close()


def test_blocking_resolver_holds_no_runtime_lock_and_concurrent_same_choice_is_bounded():
    secret = b"i" * 32
    runtime = active_runtime()
    args = interaction_args(object())
    entered = Event()
    release = Event()

    def blocking(_choice):
        entered.set()
        assert release.wait(timeout=1.0)
        return True

    assert runtime.register_patch_interaction(*args)
    assert runtime.start_runtime_interaction_listener(secret)
    descriptor = runtime.arm_patch_interaction_descriptor(*args, blocking)
    results = []
    first = Thread(target=lambda: results.append(post(
        descriptor["resolve_url"], secret, callback_body(descriptor)
    )))
    first.start()
    assert entered.wait(timeout=0.5)
    assert runtime.runtime_activity_snapshot() == (1, True)
    second = post(descriptor["resolve_url"], secret, callback_body(descriptor),
                  nonce="runtime-callback-concurrent-001")
    assert second == (409, {"ok": False, "status": "rejected"})
    release.set()
    first.join(timeout=1.0)
    assert results == [(200, {"ok": True, "status": "resolved"})]
    assert runtime.claim_patch_interaction(*args) == "approve"
    runtime.close()


@pytest.mark.parametrize("cleanup", ("reset", "finalize", "close"))
def test_cleanup_waits_for_inflight_resolver_then_preserves_success(cleanup):
    secret = b"i" * 32
    runtime = active_runtime()
    args = interaction_args(object())
    entered = Event()
    release = Event()

    def blocking(_choice):
        entered.set()
        assert release.wait(timeout=1.0)
        return True

    assert runtime.register_patch_interaction(*args)
    assert runtime.start_runtime_interaction_listener(secret)
    descriptor = runtime.arm_patch_interaction_descriptor(*args, blocking)
    results = []
    callback = Thread(target=lambda: results.append(post(
        descriptor["resolve_url"], secret, callback_body(descriptor)
    )))
    callback.start()
    assert entered.wait(timeout=0.5)
    if cleanup == "reset":
        cleanup_call = lambda: runtime.handle_on_session_reset(
            old_session_id="session-1"
        )
    elif cleanup == "finalize":
        cleanup_call = lambda: runtime.handle_on_session_finalize(
            session_id="session-1"
        )
    else:
        cleanup_call = runtime.close
    cleaned = Event()
    cleanup_thread = Thread(target=lambda: (cleanup_call(), cleaned.set()))
    cleanup_thread.start()
    assert cleaned.wait(timeout=0.05) is False
    release.set()
    callback.join(timeout=1.0)
    cleanup_thread.join(timeout=1.0)
    assert results == [(200, {"ok": True, "status": "resolved"})]
    assert cleaned.is_set()
    assert runtime.claim_patch_interaction(*args) is None
    if cleanup != "close":
        assert runtime.runtime_interaction_listener_snapshot()["accepting"] is True
        runtime.close()
    else:
        assert runtime.runtime_interaction_listener_snapshot()["accepting"] is False


def test_http_surface_rejects_nonexact_targets_framing_and_oversize():
    secret = b"i" * 32
    runtime = active_runtime()
    args = interaction_args(object())
    assert runtime.register_patch_interaction(*args)
    assert runtime.start_runtime_interaction_listener(secret)
    descriptor = runtime.arm_patch_interaction_descriptor(*args, lambda _c: True)
    port = int(descriptor["resolve_url"].split(":")[2].split("/")[0])
    body = canonical(callback_body(descriptor))
    signed = event_auth.sign_runtime_interaction_request(
        secret, RUNTIME_INTERACTION_PATH, body,
        nonce="runtime-callback-framing-001",
    )
    for method, target in (
        ("GET", RUNTIME_INTERACTION_PATH),
        ("POST", RUNTIME_INTERACTION_PATH + "?x=1"),
        ("POST", RUNTIME_INTERACTION_PATH + "/"),
        ("POST", "//example.invalid/runtime/interactions/resolve"),
    ):
        connection = http.client.HTTPConnection("127.0.0.1", port, timeout=1.0)
        connection.request(method, target, body=body, headers=signed)
        response = connection.getresponse()
        assert response.status in {404, 405}
        assert json.loads(response.read()) == {"ok": False, "status": "rejected"}
        connection.close()

    for raw in (
        b"POST " + RUNTIME_INTERACTION_PATH.encode() + b" HTTP/1.1\r\nHost: 127.0.0.1\r\nTransfer-Encoding: chunked\r\n\r\n0\r\n\r\n",
        b"POST " + RUNTIME_INTERACTION_PATH.encode() + b" HTTP/1.1\r\nHost: 127.0.0.1\r\nContent-Length: 2\r\nContent-Length: 2\r\n\r\n{}",
        b"POST " + RUNTIME_INTERACTION_PATH.encode() + b" HTTP/1.1\r\nHost: 127.0.0.1\r\nContent-Length: +2\r\n\r\n{}",
    ):
        with socket.create_connection(("127.0.0.1", port), timeout=1.0) as sock:
            sock.sendall(raw)
            response = sock.recv(2048)
        assert b" 400 " in response

    for host in ("localhost", "0.0.0.0", "[::1]"):
        raw = (
            f"POST {RUNTIME_INTERACTION_PATH} HTTP/1.1\r\n"
            f"Host: {host}:{port}\r\n"
            "Content-Type: application/json\r\n"
            f"Content-Length: {len(body)}\r\n"
            + "".join(f"{key}: {value}\r\n" for key, value in signed.items())
            + "\r\n"
        ).encode("ascii") + body
        with socket.create_connection(("127.0.0.1", port), timeout=1.0) as sock:
            sock.sendall(raw)
            response = sock.recv(2048)
        assert b" 400 " in response

    oversized = b"{" + b" " * MAX_RUNTIME_INTERACTION_BODY_BYTES + b"}"
    headers = event_auth.sign_runtime_interaction_request(
        secret, RUNTIME_INTERACTION_PATH, oversized,
        nonce="runtime-callback-oversize-001",
    )
    headers["Content-Type"] = "application/json"
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=1.0)
    connection.request("POST", RUNTIME_INTERACTION_PATH, oversized, headers)
    assert connection.getresponse().status == 413
    connection.close()
    runtime.close()


@pytest.mark.parametrize("raw", (
    b'{"choice":"approve", "expires_at":130.0}',
    b'{"choice":NaN}',
    b'{"choice":"approve"} trailing',
    (b'{"x":' * 20) + b"0" + (b"}" * 20),
    b"\xff",
))
def test_http_surface_rejects_noncanonical_or_malformed_json(raw):
    secret = b"i" * 32
    runtime = active_runtime()
    args = interaction_args(object())
    assert runtime.register_patch_interaction(*args)
    assert runtime.start_runtime_interaction_listener(secret)
    descriptor = runtime.arm_patch_interaction_descriptor(*args, lambda _c: True)
    headers = event_auth.sign_runtime_interaction_request(
        secret, RUNTIME_INTERACTION_PATH, raw, nonce="runtime-callback-json-0001",
    )
    req = request.Request(descriptor["resolve_url"], raw, headers, method="POST")
    with pytest.raises(error.HTTPError) as caught:
        request.urlopen(req, timeout=1.0)
    assert caught.value.code == 400
    assert json.loads(caught.value.read()) == {"ok": False, "status": "rejected"}
    runtime.close()


def test_python_boundary_rejects_subclasses_and_extra_keys():
    class DictSubclass(dict):
        pass
    class StringSubclass(str):
        pass

    secret = b"i" * 32
    runtime = active_runtime()
    args = interaction_args(object())
    assert runtime.register_patch_interaction(*args)
    assert runtime.start_runtime_interaction_listener(secret)
    descriptor = runtime.arm_patch_interaction_descriptor(*args, lambda _c: True)
    body = callback_body(descriptor)
    assert runtime.resolve_runtime_interaction_payload(DictSubclass(body)) is False
    assert runtime.resolve_runtime_interaction_payload(
        dict(body, choice=StringSubclass("approve"))
    ) is False
    assert runtime.resolve_runtime_interaction_payload(dict(body, extra=1)) is False
    runtime.close()


def test_close_is_concurrent_exact_and_leaves_no_listener_thread():
    runtime = active_runtime()
    assert runtime.start_runtime_interaction_listener(b"i" * 32)
    worker_name = runtime.runtime_interaction_listener_snapshot()["worker_name"]
    start = Barrier(8)
    with ThreadPoolExecutor(max_workers=8) as executor:
        results = list(executor.map(
            lambda _i: (start.wait(), runtime.close())[1], range(8)
        ))
    assert results == [None] * 8
    deadline = time.monotonic() + 1.0
    while time.monotonic() < deadline:
        if not any(t.name == worker_name and t.is_alive()
                   for t in __import__("threading").enumerate()):
            break
        time.sleep(0.01)
    assert not any(t.name == worker_name and t.is_alive()
                   for t in __import__("threading").enumerate())
    assert runtime.runtime_interaction_listener_snapshot()["accepting"] is False


def test_capacity_rejects_without_eviction_and_session_cleanup_keeps_listener():
    runtime = active_runtime()
    runtime._MAX_PATCH_INTERACTIONS = 1
    first = interaction_args(object(), interaction_id="first")
    second = interaction_args(object(), interaction_id="second")
    assert runtime.register_patch_interaction(*first)
    assert runtime.start_runtime_interaction_listener(b"i" * 32)
    assert runtime.arm_patch_interaction_descriptor(*first, lambda _c: True)
    assert runtime.register_patch_interaction(*second) is False
    runtime.handle_on_session_finalize(session_id="session-1")
    assert runtime.runtime_interaction_listener_snapshot()["accepting"] is True
    runtime.close()


def test_disconnect_after_canonical_request_keeps_resolution_but_partial_body_does_not():
    secret = b"i" * 32
    runtime = active_runtime()
    args = interaction_args(object())
    resolved = Event()
    assert runtime.register_patch_interaction(*args)
    assert runtime.start_runtime_interaction_listener(secret)
    descriptor = runtime.arm_patch_interaction_descriptor(
        *args, lambda _choice: resolved.set() or True
    )
    body = canonical(callback_body(descriptor))
    headers = event_auth.sign_runtime_interaction_request(
        secret, RUNTIME_INTERACTION_PATH, body,
        nonce="runtime-callback-disconnect-001",
    )
    port = int(descriptor["resolve_url"].split(":")[2].split("/")[0])
    raw_headers = (
        f"POST {RUNTIME_INTERACTION_PATH} HTTP/1.1\r\n"
        f"Host: 127.0.0.1:{port}\r\n"
        "Content-Type: application/json\r\n"
        f"Content-Length: {len(body)}\r\n"
        + "".join(f"{key}: {value}\r\n" for key, value in headers.items())
        + "\r\n"
    ).encode("ascii")
    sock = socket.create_connection(("127.0.0.1", port), timeout=1.0)
    sock.sendall(raw_headers + body)
    sock.close()
    assert resolved.wait(timeout=0.5)
    assert runtime.claim_patch_interaction(*args) == "approve"

    other = interaction_args(object(), interaction_id="partial")
    partial_called = Event()
    assert runtime.register_patch_interaction(*other)
    descriptor = runtime.arm_patch_interaction_descriptor(
        *other, lambda _choice: partial_called.set() or True
    )
    body = canonical(callback_body(descriptor))
    headers = event_auth.sign_runtime_interaction_request(
        secret, RUNTIME_INTERACTION_PATH, body,
        nonce="runtime-callback-partial-0001",
    )
    raw_headers = (
        f"POST {RUNTIME_INTERACTION_PATH} HTTP/1.1\r\n"
        f"Host: 127.0.0.1:{port}\r\n"
        "Content-Type: application/json\r\n"
        f"Content-Length: {len(body)}\r\n"
        + "".join(f"{key}: {value}\r\n" for key, value in headers.items())
        + "\r\n"
    ).encode("ascii")
    sock = socket.create_connection(("127.0.0.1", port), timeout=1.0)
    sock.sendall(raw_headers + body[: len(body) // 2])
    sock.close()
    assert partial_called.wait(timeout=0.15) is False
    assert runtime.claim_patch_interaction(*other) is None
    runtime.close()


def test_unbounded_resolver_marks_poisoned_and_retains_authoritative_owner():
    secret = b"i" * 32
    runtime = active_runtime()
    args = interaction_args(object())
    entered = Event()
    release = Event()

    def blocking(_choice):
        entered.set()
        assert release.wait(timeout=1.0)
        return True

    assert runtime.register_patch_interaction(*args)
    assert runtime.start_runtime_interaction_listener(secret)
    listener = runtime._runtime_interaction_listener
    listener._JOIN_SECONDS = 0.05
    descriptor = runtime.arm_patch_interaction_descriptor(*args, blocking)
    results = []
    callback = Thread(target=lambda: results.append(post(
        descriptor["resolve_url"], secret, callback_body(descriptor)
    )))
    callback.start()
    assert entered.wait(timeout=0.5)

    started = time.monotonic()
    runtime.close()
    elapsed = time.monotonic() - started
    snapshot = runtime.runtime_interaction_listener_snapshot()
    assert elapsed < 0.3
    assert snapshot["accepting"] is False
    assert snapshot["poisoned"] is True
    assert runtime._patch_interactions
    assert runtime.start_runtime_interaction_listener(secret) is False

    release.set()
    callback.join(timeout=1.0)
    assert results == [(200, {"ok": True, "status": "resolved"})]
    assert runtime._patch_interactions


def test_descriptor_expiring_while_body_read_is_blocked_never_calls_resolver():
    now = [100.0]
    secret = b"i" * 32
    runtime = active_runtime(now=lambda: now[0])
    args = interaction_args(object())
    called = Event()
    assert runtime.register_patch_interaction(*args)
    assert runtime.start_runtime_interaction_listener(secret)
    descriptor = runtime.arm_patch_interaction_descriptor(
        *args, lambda _choice: called.set() or True
    )
    body = canonical(callback_body(descriptor))
    headers = event_auth.sign_runtime_interaction_request(
        secret, RUNTIME_INTERACTION_PATH, body,
        nonce="runtime-callback-blocked-read-001",
    )
    port = int(descriptor["resolve_url"].split(":")[2].split("/")[0])
    raw_headers = (
        f"POST {RUNTIME_INTERACTION_PATH} HTTP/1.1\r\n"
        f"Host: 127.0.0.1:{port}\r\n"
        "Content-Type: application/json\r\n"
        f"Content-Length: {len(body)}\r\n"
        + "".join(f"{key}: {value}\r\n" for key, value in headers.items())
        + "\r\n"
    ).encode("ascii")
    with socket.create_connection(("127.0.0.1", port), timeout=1.0) as sock:
        midpoint = len(body) // 2
        sock.sendall(raw_headers + body[:midpoint])
        time.sleep(0.05)
        now[0] = descriptor["expires_at"]
        sock.sendall(body[midpoint:])
        response = sock.recv(2048)
    assert b" 409 " in response
    assert called.is_set() is False
    runtime.close()


def test_partial_request_line_threads_are_capacity_bounded_and_close_is_truthful():
    runtime = active_runtime()
    assert runtime.start_runtime_interaction_listener(b"i" * 32)
    listener = runtime._runtime_interaction_listener
    listener._JOIN_SECONDS = 0.05
    listener._MAX_ACTIVE_REQUESTS = 2
    port = int(listener.resolve_url.split(":")[2].split("/")[0])
    before = {
        thread.ident
        for thread in __import__("threading").enumerate()
        if "process_request_thread" in thread.name
    }
    sockets = []
    for _index in range(5):
        sock = socket.create_connection(("127.0.0.1", port), timeout=1.0)
        sock.sendall(b"POST /runtime/interactions")
        sockets.append(sock)
    deadline = time.monotonic() + 0.5
    while time.monotonic() < deadline:
        spawned = [
            thread
            for thread in __import__("threading").enumerate()
            if "process_request_thread" in thread.name
            and thread.ident not in before
            and thread.is_alive()
        ]
        if len(spawned) >= 2:
            break
        time.sleep(0.01)
    assert len(spawned) <= 2

    started = time.monotonic()
    runtime.close()
    assert time.monotonic() - started < 0.3
    snapshot = runtime.runtime_interaction_listener_snapshot()
    still_alive = [thread for thread in spawned if thread.is_alive()]
    assert snapshot["poisoned"] is bool(still_alive)
    assert snapshot["accepting"] is False

    for sock in sockets:
        sock.close()
    deadline = time.monotonic() + 1.0
    while time.monotonic() < deadline and any(
        thread.is_alive() for thread in spawned
    ):
        time.sleep(0.01)
    assert not any(thread.is_alive() for thread in spawned)


@pytest.mark.parametrize("cleanup", ("reset", "finalize"))
def test_timed_out_session_cleanup_is_deferred_without_reopening_admission(
    cleanup, monkeypatch
):
    runtime = active_runtime()
    runtime._MAX_ENTRIES = 1
    args = interaction_args(object())
    entered = Event()
    release = Event()

    def blocking(_choice):
        entered.set()
        assert release.wait(timeout=1.0)
        return True

    assert runtime.register_patch_interaction(*args)
    assert runtime.start_runtime_interaction_listener(b"i" * 32)
    descriptor = runtime.arm_patch_interaction_descriptor(*args, blocking)
    result = []
    callback = Thread(target=lambda: result.append(post(
        descriptor["resolve_url"], b"i" * 32, callback_body(descriptor)
    )))
    callback.start()
    assert entered.wait(timeout=0.5)
    monkeypatch.setattr(runtime, "_wait_interaction_resolutions", lambda _events: False)
    if cleanup == "reset":
        runtime.handle_on_session_reset(old_session_id="session-1")
    else:
        runtime.handle_on_session_finalize(session_id="session-1")
    assert runtime.resolve_runtime_interaction_payload(callback_body(descriptor)) is False

    release.set()
    callback.join(timeout=1.0)
    assert result == [(200, {"ok": True, "status": "resolved"})]
    deadline = time.monotonic() + 1.0
    while time.monotonic() < deadline and runtime.turn_state("turn-1") is not None:
        time.sleep(0.01)
    assert runtime.turn_state("turn-1") is None
    assert runtime._interaction_cleanup_turns == set()

    assert runtime.bind_ingress_from_values(
        "second", "fallback_default", "session-2", "gateway-session-2",
        "generation-2", "oc_2", "om_2", "om_2", "",
    )
    runtime.handle_pre_llm_call(
        session_id="session-2", turn_id="turn-2", platform="feishu"
    )
    assert runtime.turn_state("turn-2") is plugin_runtime.TurnState.CARD_ACTIVE
    runtime.close()


def test_timed_out_terminal_cleanup_clears_without_replaying_terminal(
    monkeypatch,
):
    runtime = active_runtime()
    args = interaction_args(object())
    entered = Event()
    release = Event()

    def blocking(_choice):
        entered.set()
        assert release.wait(timeout=1.0)
        return True

    assert runtime.register_patch_interaction(*args)
    assert runtime.start_runtime_interaction_listener(b"i" * 32)
    descriptor = runtime.arm_patch_interaction_descriptor(*args, blocking)
    result = []
    callback = Thread(target=lambda: result.append(post(
        descriptor["resolve_url"], b"i" * 32, callback_body(descriptor)
    )))
    callback.start()
    assert entered.wait(timeout=0.5)
    runtime.handle_post_llm_call(turn_id="turn-1", assistant_response="answer")
    monkeypatch.setattr(runtime, "_wait_interaction_resolutions", lambda _events: False)
    runtime.handle_on_session_end(
        turn_id="turn-1", completed=True, failed=False, interrupted=False
    )
    assert "turn-1" not in runtime._terminal_records

    release.set()
    callback.join(timeout=1.0)
    assert result == [(200, {"ok": True, "status": "resolved"})]
    deadline = time.monotonic() + 1.0
    while time.monotonic() < deadline and runtime.turn_state("turn-1") is not None:
        time.sleep(0.01)
    assert runtime.turn_state("turn-1") is None
    assert runtime.take_terminal_record("turn-1") is None
    assert runtime._interaction_cleanup_turns == set()
    runtime.close()


def test_listener_close_exception_is_sanitized_and_preserves_authoritative_state(
    monkeypatch,
):
    runtime = active_runtime()
    args = interaction_args(object())
    assert runtime.register_patch_interaction(*args)
    assert runtime.start_runtime_interaction_listener(b"i" * 32)
    listener = runtime._runtime_interaction_listener
    real_close = listener.close
    monkeypatch.setattr(
        listener,
        "close",
        lambda: (_ for _ in ()).throw(RuntimeError("PRIVATE-CLOSE-CANARY")),
    )

    with pytest.raises(RuntimeError) as caught:
        runtime.close()
    assert str(caught.value) == "runtime interaction listener close failed"
    snapshot = runtime.runtime_interaction_listener_snapshot()
    assert snapshot["accepting"] is False
    assert snapshot["poisoned"] is True
    assert runtime.turn_state("turn-1") is plugin_runtime.TurnState.CARD_ACTIVE
    assert runtime._patch_interactions
    with pytest.raises(RuntimeError) as repeated:
        runtime.close()
    assert str(repeated.value) == "runtime interaction listener close failed"
    assert "PRIVATE-CLOSE-CANARY" not in str(repeated.value)

    monkeypatch.setattr(listener, "close", real_close)
    listener.close()


def test_concurrent_runtime_close_waiters_all_observe_listener_close_failure(
    monkeypatch,
):
    runtime = active_runtime()
    assert runtime.start_runtime_interaction_listener(b"i" * 32)
    listener = runtime._runtime_interaction_listener
    real_close = listener.close
    entered = Event()
    release = Event()

    def fail_close():
        entered.set()
        assert release.wait(timeout=1.0)
        raise RuntimeError("PRIVATE-CLOSE-CANARY")

    monkeypatch.setattr(listener, "close", fail_close)
    start = Barrier(6)

    def close_runtime(_index):
        start.wait()
        try:
            runtime.close()
        except RuntimeError as exc:
            return str(exc)
        return "clean"

    with ThreadPoolExecutor(max_workers=6) as executor:
        futures = [executor.submit(close_runtime, index) for index in range(6)]
        assert entered.wait(timeout=0.5)
        release.set()
        results = [future.result(timeout=1.0) for future in futures]
    assert results == ["runtime interaction listener close failed"] * 6
    assert runtime.runtime_interaction_listener_snapshot()["poisoned"] is True
    assert runtime.turn_state("turn-1") is plugin_runtime.TurnState.CARD_ACTIVE

    monkeypatch.setattr(listener, "close", real_close)
    listener.close()


def test_late_claim_is_rejected_while_deferred_cleanup_owns_turn(monkeypatch):
    runtime = active_runtime()
    args = interaction_args(object())
    resolver_entered = Event()
    resolver_release = Event()
    cleanup_entered = Event()
    cleanup_release = Event()

    def blocking_resolver(_choice):
        resolver_entered.set()
        assert resolver_release.wait(timeout=1.0)
        return True

    assert runtime.register_patch_interaction(*args)
    assert runtime.start_runtime_interaction_listener(b"i" * 32)
    descriptor = runtime.arm_patch_interaction_descriptor(*args, blocking_resolver)
    real_cleanup = runtime._complete_deferred_interaction_cleanup
    cleanup_calls = []

    def blocked_cleanup(turn_digest):
        cleanup_calls.append(turn_digest)
        if len(cleanup_calls) >= 2:
            cleanup_entered.set()
            assert cleanup_release.wait(timeout=1.0)
        return real_cleanup(turn_digest)

    monkeypatch.setattr(runtime, "_complete_deferred_interaction_cleanup", blocked_cleanup)
    result = []
    callback = Thread(target=lambda: result.append(post(
        descriptor["resolve_url"], b"i" * 32, callback_body(descriptor)
    )))
    callback.start()
    assert resolver_entered.wait(timeout=0.5)
    monkeypatch.setattr(runtime, "_wait_interaction_resolutions", lambda _events: False)
    runtime.handle_on_session_finalize(session_id="session-1")
    resolver_release.set()
    assert cleanup_entered.wait(timeout=0.5)

    try:
        assert runtime.claim_patch_interaction(*args) is None
        state = next(iter(runtime._patch_interactions.values()))
        assert getattr(state, "selected_value", None) == "approve"
        assert not hasattr(state, "state")
    finally:
        cleanup_release.set()
        callback.join(timeout=1.0)
    assert result == [(200, {"ok": True, "status": "resolved"})]
    assert runtime._patch_interactions == {}
    assert runtime.register_patch_interaction(*args) is False
    runtime.close()


def test_listener_daemon_thread_allows_process_exit_without_close():
    """Regression for CLI hang: the serve_forever thread must be daemon so a
    process that starts the listener without calling close() still exits
    cleanly.  Without daemon=True the non-daemon thread blocks interpreter
    shutdown, which is what caused hermes-doctor to hang after the HFC
    plugin loaded.

    The child flushes a ``started daemon=...`` marker right after start() so
    the parent can bound startup and post-start exit as two separate phases:
    a slow cold import / loopback bind must not be mistaken for a post-start
    shutdown hang, and the emitted daemon state proves the thread flag on the
    exact runner that executed the child.  Earlier ``step:...`` markers
    (interpreter start, module import, start() complete) let the parent report
    exactly how far a stuck child got before the timeout, so a macOS-specific
    startup stall is distinguishable from a shutdown hang.
    """
    child_script = (
        # Register a SIGUSR1 handler so the parent can ask a stuck child to
        # dump its thread stack to stderr before killing it (macOS diagnosis).
        "import faulthandler, signal, sys\n"
        "try:\n"
        "    faulthandler.register(signal.SIGUSR1)\n"
        "except (AttributeError, ValueError):\n"
        "    pass\n"
        "sys.stdout.write('step:start\\n')\n"
        "sys.stdout.flush()\n"
        "from hermes_feishu_card.runtime_interaction_transport "
        "import RuntimeInteractionListener\n"
        "sys.stdout.write('step:imported\\n')\n"
        "sys.stdout.flush()\n"
        "listener = RuntimeInteractionListener(b'i' * 32, lambda _p: True)\n"
        "listener.start()\n"
        "sys.stdout.write('step:started daemon=' + str(listener._thread.daemon) + '\\n')\n"
        "sys.stdout.flush()\n"
    )
    # Bound the two phases independently: give cold import / bind room, but
    # keep the post-start exit window tight so a non-daemon thread fails fast.
    startup_timeout = 30.0
    exit_timeout = 10.0

    proc = subprocess.Popen(
        [sys.executable, "-c", child_script],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    stdout_lines = queue.Queue()
    stderr_lines = queue.Queue()

    def _pump(src, dst):
        try:
            for line in src:
                dst.put(line)
        finally:
            dst.put(None)

    def _drain(dst):
        lines = []
        while True:
            try:
                item = dst.get_nowait()
            except queue.Empty:
                break
            if item is None:
                break
            lines.append(item)
        return "".join(lines)

    def _kill():
        if proc.poll() is None:
            proc.kill()
            proc.wait()

    def _dump_stack():
        # Ask a stuck child to dump its thread stack to stderr before kill.
        if hasattr(signal, "SIGUSR1"):
            try:
                proc.send_signal(signal.SIGUSR1)
            except (ProcessLookupError, PermissionError):
                pass
            time.sleep(1.0)

    out_pump = Thread(target=_pump, args=(proc.stdout, stdout_lines), daemon=True)
    err_pump = Thread(target=_pump, args=(proc.stderr, stderr_lines), daemon=True)
    out_pump.start()
    err_pump.start()

    try:
        # Phase 1: bounded startup — wait for the flushed started marker,
        # collecting every step marker so a stuck child is pinpointed.
        steps = []
        marker = None
        deadline = time.monotonic() + startup_timeout
        while marker is None and time.monotonic() < deadline:
            try:
                line = stdout_lines.get(timeout=0.5)
            except queue.Empty:
                line = None
            if line is None:
                continue
            if line.startswith("step:"):
                steps.append(line.strip())
            if line.startswith("step:started daemon="):
                marker = line.strip()
                break
        if marker is None:
            _dump_stack()
            _kill()
            stderr = _drain(stderr_lines)
            pytest.fail(
                f"child did not emit started marker within "
                f"{startup_timeout:.0f}s (exit code {proc.returncode}) — "
                f"cold import or loopback bind too slow, or start() hung\n"
                f"steps seen: {steps!r}\n"
                f"stderr: {stderr!r}"
            )
        daemon_flag = marker.split("=", 1)[1]
        assert daemon_flag == "True", (
            f"listener serve_forever thread must be daemon, got {marker!r}"
        )

        # Phase 2: post-start exit — interpreter must exit without close().
        try:
            returncode = proc.wait(timeout=exit_timeout)
        except subprocess.TimeoutExpired:
            _dump_stack()
            _kill()
            pytest.fail(
                f"process did not exit within {exit_timeout:.0f}s after "
                f"start without close() — listener thread is not daemon\n"
                f"steps seen: {steps!r}\n"
                f"stderr: {_drain(stderr_lines)!r}"
            )
        assert returncode == 0, (
            f"expected exit 0, got {returncode}\n"
            f"stderr: {_drain(stderr_lines)!r}"
        )
    finally:
        _kill()
        out_pump.join(timeout=1.0)
        err_pump.join(timeout=1.0)


def test_start_does_not_need_reverse_dns_for_loopback(monkeypatch):
    """Regression for the hosted macOS stall: HTTPServer.server_bind() calls
    socket.getfqdn() while binding, and reverse DNS on the runner can hang
    well past any reasonable startup bound.  The literal-loopback listener
    does not need a resolved hostname, so start() must not depend on it.

    We emulate the stalled resolver by sleeping in getfqdn; with the
    production path free of reverse DNS, the listener still starts in a
    few seconds, and the emitted daemon marker stays correct.
    """
    child_script = (
        "import faulthandler, signal, sys\n"
        "try:\n"
        "    faulthandler.register(signal.SIGUSR1)\n"
        "except (AttributeError, ValueError):\n"
        "    pass\n"
        "import socket\n"
        "original_getfqdn = socket.getfqdn\n"
        "def stalled_getfqdn(host=''):\n"
        "    time.sleep(300)\n"
        "    return original_getfqdn(host)\n"
        "socket.getfqdn = stalled_getfqdn\n"
        "import time\n"
        "sys.stdout.write('step:start\\n')\n"
        "sys.stdout.flush()\n"
        "from hermes_feishu_card.runtime_interaction_transport import RuntimeInteractionListener\n"
        "sys.stdout.write('step:imported\\n')\n"
        "sys.stdout.flush()\n"
        "listener = RuntimeInteractionListener(b'i' * 32, lambda _p: True)\n"
        "listener.start()\n"
        "sys.stdout.write('step:started daemon=' + str(listener._thread.daemon) + '\\n')\n"
        "sys.stdout.flush()\n"
    )
    # Same startup bound as the daemon regression: hosted runners can take a
    # while for a cold interpreter import.  The stalled resolver sleeps far
    # beyond that bound, so a reverse-DNS dependency can never slip through.
    startup_timeout = 30.0
    exit_timeout = 10.0

    proc = subprocess.Popen(
        [sys.executable, "-c", child_script],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    stdout_lines = queue.Queue()
    stderr_lines = queue.Queue()

    def _pump(src, dst):
        try:
            for line in src:
                dst.put(line)
        finally:
            dst.put(None)

    def _drain(dst):
        lines = []
        while True:
            try:
                item = dst.get_nowait()
            except queue.Empty:
                break
            if item is None:
                break
            lines.append(item)
        return "".join(lines)

    def _kill():
        if proc.poll() is None:
            proc.kill()
            proc.wait()

    out_pump = Thread(target=_pump, args=(proc.stdout, stdout_lines), daemon=True)
    err_pump = Thread(target=_pump, args=(proc.stderr, stderr_lines), daemon=True)
    out_pump.start()
    err_pump.start()

    try:
        steps = []
        marker = None
        deadline = time.monotonic() + startup_timeout
        while marker is None and time.monotonic() < deadline:
            try:
                line = stdout_lines.get(timeout=0.5)
            except queue.Empty:
                line = None
            if line is None:
                continue
            if line.startswith("step:"):
                steps.append(line.strip())
            if line.startswith("step:started daemon="):
                marker = line.strip()
                break
        if marker is None:
            _kill()
            stderr = _drain(stderr_lines)
            pytest.fail(
                f"start() still depends on reverse DNS: no started marker within "
                f"{startup_timeout:.0f}s while getfqdn sleeps 15s\n"
                f"steps seen: {steps!r}\n"
                f"stderr: {stderr!r}"
            )
        daemon_flag = marker.split("=", 1)[1]
        assert daemon_flag == "True", (
            f"listener serve_forever thread must be daemon, got {marker!r}"
        )
        try:
            returncode = proc.wait(timeout=exit_timeout)
        except subprocess.TimeoutExpired:
            _kill()
            pytest.fail(
                f"process did not exit within {exit_timeout:.0f}s after start "
                f"without close() — listener thread is not daemon\n"
                f"steps seen: {steps!r}\n"
                f"stderr: {_drain(stderr_lines)!r}"
            )
        assert returncode == 0, (
            f"expected exit 0, got {returncode}\n"
            f"stderr: {_drain(stderr_lines)!r}"
        )
    finally:
        _kill()
        out_pump.join(timeout=1.0)
        err_pump.join(timeout=1.0)
