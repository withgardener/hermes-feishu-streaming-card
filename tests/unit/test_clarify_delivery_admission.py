from __future__ import annotations

import ast
import asyncio
import copy
import json
import logging
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import ModuleType, SimpleNamespace

import pytest

from hermes_feishu_card import hermes_plugin_runtime as plugin_runtime, hook_runtime
from hermes_feishu_card.install import hybrid_renderers, patcher
from hermes_feishu_card.interaction_rules import runtime_admission_fingerprint


@pytest.fixture
def official_clarify(monkeypatch):
    root = Path(os.environ["HFC_FIXED_TAG_SOURCE_ROOT"])
    sha = "3c27eb6234bf91b8ceee9e9071591b31e9b148cb"
    assert subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip() == sha
    source = subprocess.check_output(["git", "show", f"{sha}:tools/clarify_gateway.py"], cwd=root)
    tools = ModuleType("tools")
    tools.__path__ = []
    module = ModuleType("tools.clarify_gateway")
    monkeypatch.setitem(sys.modules, "tools", tools)
    monkeypatch.setitem(sys.modules, module.__name__, module)
    exec(compile(source, "<official-clarify-gateway>", "exec"), module.__dict__)
    tools.clarify_gateway = module
    monkeypatch.setattr(module, "get_clarify_timeout", lambda: 3)
    gateway = subprocess.check_output(["git", "show", f"{sha}:gateway/run.py"], cwd=root)
    descriptor = next(d for d in patcher.HYBRID_PATCH_DESCRIPTORS if d.group == "clarify_round_trip")
    rendered = hybrid_renderers._render_clarify_round_trip(gateway, descriptor)
    callbacks = [n for n in ast.walk(ast.parse(rendered)) if isinstance(n, ast.FunctionDef) and n.name == "_clarify_callback_sync"]
    assert len(callbacks) == 1
    yield module, copy.deepcopy(callbacks[0])
    module.clear_session("synthetic-gateway")


@pytest.mark.parametrize("mode", ["delayed-delivery-ack", "resolved-before-delivery-ack", "lost-first-ack", "lost-first-no-proof", "owned-wait-exception"])
def test_actual_clarify_callback_does_not_send_native_after_delivered_admission(monkeypatch, official_clarify, mode):
    """Exercise original register/wait/resolve, rendered callback and signed HTTP.

    HTTP represents a committed card create whose acknowledgement is delayed;
    it is not evidence of a real Feishu send or phone click.
    """
    resolve_before_ack = mode == "resolved-before-delivery-ack"
    clarify, callback = official_clarify
    if mode == "owned-wait-exception":
        def failed_wait(_id, timeout):
            raise RuntimeError("synthetic wait failed")
        monkeypatch.setattr(clarify, "wait_for_response", failed_wait)
    runtime = plugin_runtime.PluginRuntime(post=lambda _p, _t: {"ok": True, "applied": True})
    assert runtime.bind_ingress_from_values("default", "fallback_default", "synthetic-session", "synthetic-gateway", "generation", "synthetic-chat", "synthetic-input", "synthetic-input", "")
    runtime.handle_pre_llm_call(session_id="synthetic-session", turn_id="synthetic-turn", platform="feishu")
    assert runtime.turn_state("synthetic-turn") is plugin_runtime.TurnState.CARD_ACTIVE

    class Listener:
        resolve_url = "http://127.0.0.1:12345/runtime/interactions/resolve"

        @staticmethod
        def accepts():
            return True

    runtime._runtime_interaction_listener = Listener()
    monkeypatch.setattr(hook_runtime, "_plugin_runtime", lambda: runtime)
    native_sends = []
    requests = []
    resolved = []
    delivered = threading.Event()
    stop = threading.Event()

    def resolve(payload):
        descriptor = payload["data"]["_hfc_runtime_admission"]
        answer = {key: descriptor[key] for key in ("protocol", "runtime_id", "interaction_key", "token", "expires_at")}
        answer["choice"] = "A"
        resolved.append(runtime.resolve_runtime_interaction_payload(answer))

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def do_POST(self):
            payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            requests.append(payload)
            delivered.set()
            if mode.startswith("lost-first") and len(requests) == 1:
                # Create has committed but its ACK was lost. A second POST is
                # not a read-only proof of the original delivery result.
                self.close_connection = True
                return
            if resolve_before_ack:
                resolve(payload)
            # Isolate the two defects: one exceeds observer cap; the other
            # resolves before a fast ACK, even within the original 0.8s cap.
            stop.wait(0.95 if mode == "delayed-delivery-ack" else 0.15)
            body = json.dumps({"ok": True, "applied": True, "delivery": {"outcome": "delivered"}, "runtime_admission": True}).encode()
            try:
                self.send_response(200)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError):
                pass  # Baseline caller times out after 0.8s; retain red behavior.

        def do_GET(self):
            payload = requests[0]
            proof = {"ok": mode != "lost-first-no-proof", "interaction_id": payload["data"]["interaction_id"]}
            if proof["ok"]:
                proof["runtime_admission_fingerprint"] = runtime_admission_fingerprint(payload["data"]["_hfc_runtime_admission"])
            body = json.dumps(proof).encode()
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.daemon_threads = False
    worker = threading.Thread(target=server.serve_forever)
    worker.start()
    transport = plugin_runtime.SignedEventTransport(event_url=f"http://127.0.0.1:{server.server_port}/events", timeout_seconds=0.8, secret_reader=lambda: b"s" * 32)
    runtime._post = transport

    class Adapter:
        @staticmethod
        def pause_typing_for_chat(_chat):
            pass

        async def send_clarify(self, **kwargs):
            native_sends.append(kwargs)
            clarify.resolve_gateway_clarify(kwargs["clarify_id"], "A")
            return SimpleNamespace(success=True)

    def schedule(coro, *_args, **_kwargs):
        return SimpleNamespace(result=lambda timeout: asyncio.run(coro))

    ctx = SimpleNamespace(_status_adapter=Adapter(), session_key="synthetic-gateway", _status_chat_id="synthetic-chat", stream_consumer_holder=[], _status_thread_metadata={}, _loop_for_step=None)
    namespace = {"ctx": ctx, "agent": SimpleNamespace(_current_turn_id="synthetic-turn"), "safe_schedule_threadsafe": schedule, "logger": logging.getLogger(__name__)}
    exec(compile(ast.fix_missing_locations(ast.Module(body=[callback], type_ignores=[])), "<actual-rendered-clarify-callback>", "exec"), namespace)
    token = hook_runtime.publish_canonical_turn_id("synthetic-turn")

    def later_resolve():
        if delivered.wait(2) and not stop.wait(1.25):
            resolve(requests[0])

    responder = threading.Thread(target=later_resolve)
    should_respond = not resolve_before_ack and mode != "owned-wait-exception"
    if should_respond:
        responder.start()
    try:
        if mode == "owned-wait-exception":
            with pytest.raises(RuntimeError, match="synthetic wait failed"):
                namespace["_clarify_callback_sync"]("SYNTHETIC_QUESTION", ["A", "B"], False)
            assert native_sends == [], "owned wait failure must propagate without a second prompt"
            assert len(requests) == 1
            assert resolved == []
            return
        answer = namespace["_clarify_callback_sync"]("SYNTHETIC_QUESTION", ["A", "B"], False)
        assert answer == "A"
        assert requests and delivered.is_set()
        if mode == "lost-first-no-proof":
            # No proof remains fail-open. This deliberately does not claim
            # native duplicate prevention when delivery cannot be determined.
            assert len(native_sends) == 1
        else:
            assert native_sends == [], "delivered HFC prompt must not be followed by native send_clarify"
        assert resolved == [True]
        assert len(requests) == 1
    finally:
        hook_runtime.clear_canonical_turn_id(token)
        stop.set()
        if should_respond:
            responder.join(timeout=3)
        server.shutdown()
        worker.join(timeout=3)
        server.server_close()
        runtime._runtime_interaction_listener = None
        runtime.close()


@pytest.mark.parametrize("same_owner", [False, True], ids=["same-id-new-owner", "same-id-new-descriptor"])
async def test_actual_server_delivery_proof_is_commit_bound_and_read_only(monkeypatch, tmp_path, same_owner):
    from aiohttp.test_utils import TestClient, TestServer
    from hermes_feishu_card import server as server_module
    from hermes_feishu_card.event_auth import sign_sidecar_request
    from hermes_feishu_card.runtime_interaction_transport import RuntimeInteractionListener
    from tests.integration.test_server import FakeFeishuClient, create_app, event_payload, runtime_descriptor, runtime_interaction_payload, interaction_buttons, TRANSPORT_ROOT_SECRET

    monkeypatch.setenv("HERMES_FEISHU_CARD_STATE_DIR", str(tmp_path / "state"))
    feishu = FakeFeishuClient()
    app = create_app(feishu, session_store_directory=tmp_path / "sessions", event_auth_required=True)
    client = TestClient(TestServer(app))
    await client.start_server()
    listener = RuntimeInteractionListener(TRANSPORT_ROOT_SECRET, lambda _payload: True)
    listener.start()
    transport = plugin_runtime.SignedEventTransport(event_url=str(client.make_url("/events")), timeout_seconds=0.8, secret_reader=lambda: TRANSPORT_ROOT_SECRET)
    blocked, release = asyncio.Event(), asyncio.Event()
    original_send = feishu.send_card

    async def delayed_send(*args, **kwargs):
        blocked.set()
        await release.wait()
        return await original_send(*args, **kwargs)

    async def get_proof(interaction_id):
        path = f"/interactions/{interaction_id}/delivery"
        response = await client.get(path, headers=sign_sidecar_request(TRANSPORT_ROOT_SECRET, "GET", path, b""))
        return response.status, await response.json()

    try:
        started = event_payload("message.started", 0, turn_id="turn-runtime", created_at=time.time())
        assert (await asyncio.to_thread(transport, started, 3.0))["ok"] is True
        payload = runtime_interaction_payload(runtime_descriptor(listener))
        monkeypatch.setattr(feishu, "send_card", delayed_send)
        pending = asyncio.create_task(asyncio.to_thread(transport, payload, 3.0))
        await asyncio.wait_for(blocked.wait(), 2)
        _, before = await get_proof("runtime-approval-1")
        assert not before.get("runtime_admission_fingerprint")
        release.set()
        assert (await pending)["runtime_admission"] is True
        status, proof = await get_proof("runtime-approval-1")
        assert status == 200
        unsigned = await client.get("/interactions/runtime-approval-1/delivery")
        assert unsigned.status == 401
        assert proof["runtime_admission_fingerprint"] == runtime_admission_fingerprint(payload["data"]["_hfc_runtime_admission"])
        assert "token" not in proof
        assert await asyncio.to_thread(transport.confirm_interaction_delivery, payload, 0.2) is True

        owner = app[server_module.SESSIONS_KEY]["turn-runtime"]
        timestamps = (owner.updated_at, owner.active_interaction.last_waiter_poll_at)
        update_count = len(feishu.updated)
        await get_proof("runtime-approval-1")
        assert (owner.updated_at, owner.active_interaction.last_waiter_poll_at) == timestamps
        assert len(feishu.updated) == update_count

        value = interaction_buttons(feishu.sent[-1][1])[0]["value"]
        body = json.dumps({"event": {"operator": {"open_id": "ou_synthetic"}, "context": {"open_chat_id": "oc_abc", "profile_id": "default"}, "action": {"value": value}}}).encode()
        headers = {"Content-Type": "application/json", **sign_sidecar_request(TRANSPORT_ROOT_SECRET, "POST", "/card/actions", body)}
        response = await client.post("/card/actions", data=body, headers=headers)
        assert response.status == 200
        assert owner.active_interaction.status == "completed"
        assert (await get_proof("runtime-approval-1"))[1]["runtime_admission_fingerprint"] == proof["runtime_admission_fingerprint"]

        changed = copy.deepcopy(payload)
        changed["event_id"] = "patch:new-delivery"
        changed["sequence"] = 10
        changed["created_at"] = time.time()
        changed["data"]["_hfc_runtime_admission"]["interaction_key"] = "d" * 64
        if not same_owner:
            changed["turn_id"] = "turn-other"
            started = event_payload("message.started", 0, turn_id="turn-other", created_at=time.time())
            assert (await asyncio.to_thread(transport, started, 3.0))["ok"] is True
        release.clear()
        blocked.clear()
        pending = asyncio.create_task(asyncio.to_thread(transport, changed, 3.0))
        await asyncio.wait_for(blocked.wait(), 2)
        assert await asyncio.to_thread(transport.confirm_interaction_delivery, changed, 0.1) is False
        release.set()
        assert (await pending)["runtime_admission"] is True
        assert await asyncio.to_thread(transport.confirm_interaction_delivery, changed, 0.2) is True
        assert await asyncio.to_thread(transport.confirm_interaction_delivery, payload, 0.1) is False
    finally:
        release.set()
        listener.close()
        await client.close()


@pytest.mark.parametrize("mode", ["exact", "wrong-id", "wrong-fingerprint", "failed", "missing-proof", "oversize", "slow-headers", "slow-body"])
def test_signed_delivery_query_identity_size_and_total_deadline(mode):
    from hermes_feishu_card.event_auth import SidecarRequestProofVerifier

    secret = b"q" * 32
    descriptor = {"protocol": "hfc-runtime-interaction-v1", "runtime_id": "a" * 64, "interaction_key": "b" * 64, "token": "c" * 64, "resolve_url": "http://127.0.0.1:12345/runtime/interactions/resolve", "expires_at": time.time() + 30}
    payload = {"data": {"interaction_id": "synthetic-id", "_hfc_runtime_admission": descriptor}}
    verified = []
    stop = threading.Event()
    verifier = SidecarRequestProofVerifier(secret)

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def do_GET(self):
            verifier.verify(self.headers, "GET", self.path, b"")
            verified.append(self.path)
            value = {"ok": True, "interaction_id": "synthetic-id", "runtime_admission_fingerprint": runtime_admission_fingerprint(descriptor)}
            if mode == "wrong-id":
                value["interaction_id"] = "other-id"
            elif mode == "wrong-fingerprint":
                value["runtime_admission_fingerprint"] = "0" * 64
            elif mode == "failed":
                value["ok"] = False
            elif mode == "missing-proof":
                value.pop("runtime_admission_fingerprint")
            body = json.dumps(value).encode()
            if mode == "oversize":
                body += b" " * plugin_runtime.MAX_EVENT_RESPONSE_BYTES
            if mode == "slow-headers":
                stop.wait(0.4)
            try:
                self.send_response(200)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                if mode == "slow-body":
                    # Each read receives data, but the complete body exceeds
                    # budget: total deadline must defeat a healthy trickle.
                    for byte in body:
                        self.wfile.write(bytes([byte]))
                        self.wfile.flush()
                        if stop.wait(0.02):
                            break
                else:
                    self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError):
                pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    worker = threading.Thread(target=server.serve_forever)
    worker.start()
    transport = plugin_runtime.SignedEventTransport(event_url=f"http://127.0.0.1:{server.server_port}/events", timeout_seconds=0.8, secret_reader=lambda: secret)
    try:
        start = time.monotonic()
        assert transport.confirm_interaction_delivery(payload, 0.18) is (mode == "exact")
        elapsed = time.monotonic() - start
        assert elapsed < 0.65, (mode, elapsed)
        assert verified and set(verified) == {"/interactions/synthetic-id/delivery"}
    finally:
        stop.set()
        server.shutdown()
        worker.join(timeout=3)
        server.server_close()
