"""A paused-card retry cannot overwrite a renewed approval or replaced owner."""
import asyncio
import copy
import time

import pytest

from hermes_feishu_card import server
from hermes_feishu_card.session import CardSession, InteractionState


@pytest.mark.parametrize("invalidate", ["reopened", "generation", "owner", "interaction", "terminal"])
async def test_paused_approval_patch_rechecks_owner_before_retry(monkeypatch, invalidate):
    session = CardSession("fixture-chat", "fixture-turn", "fixture-chat")
    interaction = InteractionState(
        interaction_id="fixture-approval", kind="approval", prompt="Review exact scope",
        status="paused", pause_on_timeout=True, pause_generation=1,
        callback_token="fixture-old-token", feishu_message_id="fixture-approval-card",
    )
    session.active_interaction = interaction
    entered, release = asyncio.Event(), asyncio.Event()
    writes = []

    class FailingClient:
        async def update_card_message(self, message_id, card):
            writes.append((message_id, copy.deepcopy(card)))
            if len(writes) == 1:
                entered.set()
                await release.wait()
            raise OSError("synthetic PATCH failure")

    app = {
        server.SESSIONS_KEY: {"fixture-turn": session}, server.MESSAGE_BOT_IDS_KEY: {},
        server.PAUSED_APPROVAL_TASKS_KEY: set(), server.METRICS_KEY: server.SidecarMetrics(),
        server.DIAGNOSTICS_KEY: {},
    }
    monkeypatch.setattr(server, "_client_for_bot", lambda *args: FailingClient())
    monkeypatch.setattr(server, "_restart_scope_for_message", lambda *args: None)
    monkeypatch.setattr(server, "_restart_notice_snapshot", lambda *args: None)
    monkeypatch.setattr(server, "_render_interaction_callback_card_for_app", lambda *args, **kwargs: {"paused_generation": 1})
    server._schedule_paused_approval_card(app, "fixture-turn", session, interaction)
    tasks = tuple(app[server.PAUSED_APPROVAL_TASKS_KEY])
    assert tasks
    await asyncio.wait_for(entered.wait(), 1)
    if invalidate == "reopened":
        interaction.status = "pending"
        interaction.callback_token = "fixture-fresh-token"
    elif invalidate == "generation":
        interaction.pause_generation = 2
        interaction.pause_notified_generation = 2
    elif invalidate == "owner":
        replacement = CardSession("fixture-chat", "fixture-turn", "fixture-chat")
        replacement.active_interaction = copy.deepcopy(interaction)
        app[server.SESSIONS_KEY]["fixture-turn"] = replacement
    elif invalidate == "interaction":
        session.active_interaction = copy.deepcopy(interaction)
    else:
        session.status = "completed"
    observed = copy.deepcopy(interaction)
    current = app[server.SESSIONS_KEY]["fixture-turn"]
    current_interaction = copy.deepcopy(current.active_interaction)
    release.set()
    await asyncio.wait_for(asyncio.gather(*tasks), 1)
    assert len(writes) == 1, "renewed owner received an obsolete paused-card retry"
    assert interaction == observed, "obsolete delivery changed old retry state"
    assert current.active_interaction == current_interaction, "obsolete delivery changed current consent"


@pytest.mark.parametrize("first_outage", [False, True])
async def test_current_paused_owner_recovers_in_place_without_new_card_or_consent(monkeypatch, first_outage):
    session = CardSession("fixture-chat", "fixture-turn", "fixture-chat")
    interaction = InteractionState(
        interaction_id="fixture-approval", kind="approval", prompt="Review exact scope",
        status="paused", pause_on_timeout=True, pause_generation=1,
        callback_token="fixture-existing-token", feishu_message_id="fixture-approval-card",
    )
    session.active_interaction = interaction
    writes = []
    remaining_failures = server.UPDATE_MAX_ATTEMPTS if first_outage else 0

    class RecoveringClient:
        async def update_card_message(self, message_id, card):
            nonlocal remaining_failures
            writes.append(message_id)
            if remaining_failures:
                remaining_failures -= 1
                raise OSError("synthetic outage")

    app = {
        server.SESSIONS_KEY: {"fixture-turn": session}, server.MESSAGE_BOT_IDS_KEY: {},
        server.PAUSED_APPROVAL_TASKS_KEY: set(), server.METRICS_KEY: server.SidecarMetrics(),
        server.DIAGNOSTICS_KEY: {},
    }
    monkeypatch.setattr(server, "_client_for_bot", lambda *args: RecoveringClient())
    monkeypatch.setattr(server, "_restart_scope_for_message", lambda *args: None)
    monkeypatch.setattr(server, "_restart_notice_snapshot", lambda *args: None)
    monkeypatch.setattr(server, "_retire_restart_notices", lambda *args: None)
    monkeypatch.setattr(server, "_render_interaction_callback_card_for_app", lambda *args, **kwargs: {"paused_generation": 1})
    monkeypatch.setattr(server, "_send_card_for_app", lambda *args, **kwargs: pytest.fail("existing approval was duplicated"))
    server._schedule_paused_approval_card(app, "fixture-turn", session, interaction)
    await asyncio.gather(*tuple(app[server.PAUSED_APPROVAL_TASKS_KEY]))
    if first_outage:
        assert interaction.pause_notified_generation == 0
        assert interaction.pause_retry_after > time.time()
        assert len(writes) == server.UPDATE_MAX_ATTEMPTS
        server._schedule_paused_approval_card(app, "fixture-turn", session, interaction)
        assert not app[server.PAUSED_APPROVAL_TASKS_KEY]
        interaction.pause_retry_after = 0
        server._schedule_paused_approval_card(app, "fixture-turn", session, interaction)
        await asyncio.gather(*tuple(app[server.PAUSED_APPROVAL_TASKS_KEY]))
    assert len(writes) == (server.UPDATE_MAX_ATTEMPTS + 1 if first_outage else 1)
    assert set(writes) == {"fixture-approval-card"}
    assert interaction.pause_notified_generation == interaction.pause_generation == 1
    assert interaction.callback_token == "fixture-existing-token"
    assert interaction.status == "paused"
