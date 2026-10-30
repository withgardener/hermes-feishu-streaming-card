from __future__ import annotations

import json
import secrets

import pytest
from aiohttp.test_utils import TestClient, TestServer

from hermes_feishu_card import server as sidecar_server
from hermes_feishu_card.runtime_control import (
    RUNTIME_HOOK_GENERATION,
    RuntimeIntegrityFenceBinding,
    sign_runtime_request,
)
from hermes_feishu_card.server import create_app


ROOT_SECRET = b"r" * 32


class NeverCalledFeishuClient:
    async def send_card(self, *_args, **_kwargs):
        raise AssertionError("runtime control must not send a card")

    async def update_card_message(self, *_args, **_kwargs):
        raise AssertionError("runtime control must not update a card")


@pytest.fixture(autouse=True)
def isolated_runtime_integrity_state(tmp_path, monkeypatch):
    state_directory = tmp_path / "private-state"
    monkeypatch.setenv(
        "HERMES_FEISHU_CARD_STATE_DIR",
        str(state_directory),
    )
    return state_directory


def _payload(**changes):
    payload = {
        "schema_version": "3", "runtime_role": "gateway", "target_identity": "a" * 64,
        "active_sessions": 0, "admission_draining": False,
        "active_work_count_complete": True, "drain_home_verified": True,
        "event": "runtime.hello",
        "runtime_id": "runtime-1234567890",
        "sequence": 1,
        "created_at": 100.0,
        "hook_generation": RUNTIME_HOOK_GENERATION,
        "package_version": "4.1.0",
    }
    payload.update(changes)
    return payload


def _signed_body(payload):
    body = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    headers = {
        "Content-Type": "application/json",
        **sign_runtime_request(
            ROOT_SECRET,
            body,
            nonce=secrets.token_urlsafe(18),
        ),
    }
    return body, headers


async def test_runtime_endpoint_requires_proof_and_never_echoes_it():
    app = create_app(
        NeverCalledFeishuClient(),
        operations_transport_root_secret=ROOT_SECRET,
        integrity_mode="notify",
        expected_runtime_package_version="4.1.0",
    )
    client = TestClient(TestServer(app))
    await client.start_server()
    try:
        response = await client.post("/runtime/events", json=_payload())
        body = await response.json()
        health = await (await client.get("/health")).json()
    finally:
        await client.close()

    assert response.status == 401
    assert body == {"ok": False, "error": "runtime authentication failed"}
    assert "signature" not in json.dumps(body).lower()
    assert health["status"] == "healthy"
    assert health["readiness"]["status"] == "starting"
    assert health["metrics"]["runtime_control_auth_rejections"] == 1


async def test_runtime_endpoint_accepts_signed_hello_and_health_becomes_ready():
    app = create_app(
        NeverCalledFeishuClient(),
        operations_transport_root_secret=ROOT_SECRET,
        integrity_mode="notify",
        expected_runtime_package_version="4.1.0",
    )
    client = TestClient(TestServer(app))
    await client.start_server()
    body, headers = _signed_body(_payload())
    try:
        response = await client.post("/runtime/events", data=body, headers=headers)
        response_body = await response.json()
        health = await (await client.get("/health")).json()
        replay = await client.post("/runtime/events", data=body, headers=headers)
    finally:
        await client.close()

    assert response.status == 200
    assert response_body == {"ok": True, "accepted": True}
    assert health["status"] == "healthy"
    assert health["readiness"] == {
        "status": "ready",
        "reason": "runtime_ready",
        "integrity_mode": "notify",
        "runtime_seen": True,
        "generation_match": True,
        "restart_required": False,
        "last_seen_age_seconds": 0,
        "runtime_id_hash": "bc48bbf1d754a75633bd24699a81443cc84efba9580957897f6769f8414639fa",
        "last_sequence": 1,
        "active_sessions": 0,
        "admission_draining": False,
        "active_work_count_complete": True,
        "drain_home_verified": True,
        "owner_conflict": False, "owner_capacity_exceeded": False,
        "observer_count": 0, "observer_active_sessions": 0, "observer_unknown_count": 0,
    }
    assert replay.status == 401


def test_create_app_recovers_persisted_gateway_restart_fence(
    isolated_runtime_integrity_state,
):
    first = create_app(
        NeverCalledFeishuClient(),
        operations_transport_root_secret=ROOT_SECRET,
        integrity_mode="safe",
        expected_runtime_package_version="4.1.0",
        runtime_integrity_state_directory=isolated_runtime_integrity_state,
    )
    first_supervisor = first[sidecar_server.RUNTIME_INTEGRITY_SUPERVISOR_KEY]
    assert first_supervisor.record(
        sidecar_server.RuntimeControlEvent.from_dict(_payload())
    )
    first_supervisor.mark_restart_required(
        binding=RuntimeIntegrityFenceBinding(
            target_identity="a" * 64,
            plan_fingerprint="b" * 64,
        )
    )

    restarted = create_app(
        NeverCalledFeishuClient(),
        operations_transport_root_secret=ROOT_SECRET,
        integrity_mode="safe",
        expected_runtime_package_version="4.1.0",
        runtime_integrity_state_directory=isolated_runtime_integrity_state,
    )

    assert restarted[
        sidecar_server.RUNTIME_INTEGRITY_SUPERVISOR_KEY
    ].snapshot()["reason"] == "gateway_restart_required"


async def test_runtime_generation_mismatch_degrades_readiness_not_liveness():
    app = create_app(
        NeverCalledFeishuClient(),
        operations_transport_root_secret=ROOT_SECRET,
        integrity_mode="safe",
        expected_runtime_package_version="4.1.0",
    )
    client = TestClient(TestServer(app))
    await client.start_server()
    body, headers = _signed_body(
        _payload(hook_generation="old-hook", package_version="4.0.21")
    )
    try:
        assert (await client.post("/runtime/events", data=body, headers=headers)).status == 200
        health_response = await client.get("/health")
        health = await health_response.json()
    finally:
        await client.close()

    assert health_response.status == 200
    assert health["status"] == "healthy"
    assert health["readiness"]["status"] == "degraded"
    assert health["readiness"]["reason"] == "gateway_restart_required"
    assert health["readiness"]["restart_required"] is True
    assert "runtime_id" not in health["readiness"]
    assert len(health["readiness"]["runtime_id_hash"]) == 64


async def test_missing_private_root_degrades_readiness_and_refuses_runtime_control():
    app = create_app(
        NeverCalledFeishuClient(),
        operations_transport_root_secret=None,
        integrity_mode="notify",
        expected_runtime_package_version="4.1.0",
    )
    client = TestClient(TestServer(app))
    await client.start_server()
    try:
        response = await client.post("/runtime/events", json=_payload())
        health = await (await client.get("/health")).json()
    finally:
        await client.close()

    assert response.status == 503
    assert health["status"] == "healthy"
    assert health["readiness"]["reason"] == "control_auth_unavailable"


async def test_integrity_off_reports_disabled_but_still_authenticates_endpoint():
    app = create_app(
        NeverCalledFeishuClient(),
        operations_transport_root_secret=ROOT_SECRET,
        integrity_mode="off",
        expected_runtime_package_version="4.1.0",
    )
    client = TestClient(TestServer(app))
    await client.start_server()
    body, headers = _signed_body(_payload())
    try:
        response = await client.post("/runtime/events", data=body, headers=headers)
        response_body = await response.json()
        health = await (await client.get("/health")).json()
    finally:
        await client.close()

    assert response.status == 200
    assert response_body == {"ok": True, "accepted": False}
    assert health["readiness"]["status"] == "disabled"


async def test_signed_observer_preserves_gateway_owner_and_restart_fence(tmp_path):
    from hermes_feishu_card.runtime_ownership import runtime_target_identity
    app = create_app(NeverCalledFeishuClient(), operations_transport_root_secret=ROOT_SECRET,
        integrity_mode="notify", expected_runtime_package_version="4.1.0",
        operations_hermes_root=tmp_path)
    async with TestClient(TestServer(app)) as client:
        async def send(**changes):
            body, headers = _signed_body(_payload(**changes))
            response = await client.post('/runtime/events', data=body, headers=headers)
            return await response.json()
        target = runtime_target_identity(tmp_path)
        await send(target_identity=target)
        before = (await (await client.get('/health')).json())['readiness']
        assert before['status'] == 'ready'
        await send(runtime_id='desktop-runtime-001', runtime_role='observer',
            target_identity='', drain_home_verified=False, active_sessions=2)
        after = (await (await client.get('/health')).json())['readiness']
        assert after['runtime_id_hash'] == before['runtime_id_hash']
        assert after['active_sessions'] == 2
        assert after['active_work_count_complete'] is True
        await send(runtime_id='wrong-target-runtime', target_identity='b'*64)
        final = (await (await client.get('/health')).json())['readiness']
        assert final['runtime_id_hash'] == before['runtime_id_hash']
        assert final['observer_count'] == 1


async def test_shared_source_separate_homes_require_exact_authenticated_owner(tmp_path):
    from hermes_feishu_card.runtime_ownership import runtime_target_identity
    root=tmp_path/'source'; root.mkdir()
    homes=[tmp_path/'profile-a',tmp_path/'profile-b']
    for home in homes:
        home.mkdir(); (home/'config.yaml').write_text('{}')
    # Reusing a secret deliberately: routing alone must not confer HOME ownership.
    for own_home in homes:
        for restart in range(2):
            app=create_app(NeverCalledFeishuClient(),operations_hermes_root=root,
                operations_hermes_home=own_home,operations_transport_root_secret=ROOT_SECRET,
                expected_runtime_package_version='4.1.0')
            client=TestClient(TestServer(app)); await client.start_server()
            try:
                other=next(h for h in homes if h!=own_home)
                for bad_target in [runtime_target_identity(root,home=other),runtime_target_identity(root)]:
                    body,headers=_signed_body(_payload(target_identity=bad_target))
                    result=await (await client.post('/runtime/events',data=body,headers=headers)).json()
                    assert result=={'ok':True,'accepted':False}
                    health=await (await client.get('/health')).json()
                    assert health['readiness']['status']!='ready'
                body,headers=_signed_body(_payload(target_identity=runtime_target_identity(root,home=own_home)))
                result=await (await client.post('/runtime/events',data=body,headers=headers)).json()
                assert result['accepted']
                health=await (await client.get('/health')).json()
                assert health['readiness']['status']=='ready'
                assert health['readiness']['drain_home_verified'] is True
                assert str(own_home) not in json.dumps(health)
                replay=await client.post('/runtime/events',data=body,headers=headers)
                assert replay.status==401
            finally:
                await client.close()


async def test_owner_diagnostic_is_preserved_in_health_integrity():
    app=create_app(NeverCalledFeishuClient(),operations_transport_root_secret=ROOT_SECRET)
    client=TestClient(TestServer(app)); await client.start_server()
    try:
        body,headers=_signed_body(_payload(runtime_role='unknown',target_identity='',drain_home_verified=False))
        response=await client.post('/runtime/events',data=body,headers=headers)
        assert (await response.json())['accepted']
        app[sidecar_server.RUNTIME_INTEGRITY_COORDINATOR_KEY].check_once()
        health=await (await client.get('/health')).json()
        assert health['readiness']['reason']=='runtime_owner_unverified'
        assert health['integrity']['last_reason']=='runtime_owner_unverified'
    finally:
        await client.close()
