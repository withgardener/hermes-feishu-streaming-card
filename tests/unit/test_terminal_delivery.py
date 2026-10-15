"""Terminal ordering and outcomes can be verified without aiohttp or a runtime."""
from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from hermes_feishu_card.delivery import CardDeliveryResult
from hermes_feishu_card.terminal_delivery import (
    TerminalDeliveryPlan, TerminalTarget, deliver_terminal,
)


def plan(disposition="card"):
    return TerminalDeliveryPlan(
        TerminalTarget(
            "original-turn", "om_original", "oc_original", "original-bot",
            "omt_original", "om_anchor", True, "original-profile",
            "message.completed", 7,
        ),
        disposition,
        {"answer": "complete answer with final marker"},
    )


class Transport:
    def __init__(self, *, patch=False, retry=False, recovery="delivered"):
        self.patch_result = patch
        self.retry_result = retry
        self.recovery = recovery
        self.calls = []

    async def patch(self, plan, *, is_current):
        self.calls.append(("patch", plan))
        return self.patch_result

    async def retry(self, plan, *, is_current):
        self.calls.append(("retry", plan))
        return self.retry_result

    async def recover(self, plan):
        self.calls.append(("recover", plan))
        return CardDeliveryResult(
            "om_recovery" if self.recovery == "delivered" else None,
            self.recovery,
            error_kind="" if self.recovery == "delivered" else "transport",
        )


@pytest.mark.parametrize("patch,retry,expected", [
    (True, False, ["patch"]),
    (False, True, ["patch", "retry"]),
    (False, False, ["patch", "retry", "recover"]),
])
async def test_order_and_full_original_delivery_identity(patch, retry, expected):
    accepted = plan()
    owner = SimpleNamespace(terminal_delivery_state="pending")
    transport = Transport(patch=patch, retry=retry)
    outcome = await deliver_terminal(accepted, owner, transport, is_current=lambda: True)
    assert [call[0] for call in transport.calls] == expected
    assert all(call[1] is accepted for call in transport.calls)
    assert accepted.target.recovery_key == "original-turn:om_original:7"
    assert accepted.card["answer"].endswith("final marker")
    assert owner.terminal_delivery_state == ("recovered" if len(expected) == 3 else "delivered")
    assert outcome.updated and not outcome.commit_native


@pytest.mark.parametrize("recovery", ["unknown", "not_sent"])
async def test_failed_recovery_keeps_its_exact_outcome_without_native_fallback(recovery):
    owner = SimpleNamespace(terminal_delivery_state="pending")
    transport = Transport(recovery=recovery)
    outcome = await deliver_terminal(plan(), owner, transport, is_current=lambda: True)
    assert not outcome.updated and not outcome.commit_native
    assert outcome.recovery.outcome == owner.terminal_delivery_state == recovery
    assert [call[0] for call in transport.calls] == ["patch", "retry", "recover"]


@pytest.mark.parametrize("state", ["recovering", "recovered", "unknown", "not_sent"])
async def test_recovery_claim_is_not_repeated(state):
    owner = SimpleNamespace(terminal_delivery_state=state)
    transport = Transport()
    outcome = await deliver_terminal(plan(), owner, transport, is_current=lambda: True)
    assert [call[0] for call in transport.calls] == ["patch", "retry"]
    assert owner.terminal_delivery_state == state
    assert outcome.updated is (state == "recovered")


@pytest.mark.parametrize("updated", [False, True])
async def test_native_handoff_never_recovers_an_answer_card(updated):
    owner = SimpleNamespace(terminal_delivery_state="pending")
    transport = Transport(retry=updated)
    outcome = await deliver_terminal(plan("native"), owner, transport, is_current=lambda: True)
    assert [call[0] for call in transport.calls] == ["patch", "retry"]
    assert outcome.commit_native is updated
    assert owner.terminal_delivery_state == "pending"


async def test_cancelled_recovery_does_not_claim_delivery_or_retry():
    class CancelledTransport(Transport):
        async def recover(self, plan):
            raise asyncio.CancelledError

    owner = SimpleNamespace(terminal_delivery_state="pending")
    with pytest.raises(asyncio.CancelledError):
        await deliver_terminal(plan(), owner, CancelledTransport(), is_current=lambda: True)
    assert owner.terminal_delivery_state == "recovering"


@pytest.mark.parametrize("disposition", ["card", "native"])
async def test_superseded_owner_never_starts_transport(disposition):
    owner = SimpleNamespace(terminal_delivery_state="pending")
    transport = Transport()
    outcome = await deliver_terminal(plan(disposition), owner, transport, is_current=lambda: False)
    assert transport.calls == []
    assert owner.terminal_delivery_state == "pending"
    assert outcome.superseded and not outcome.updated and not outcome.commit_native
    assert outcome.recovery is None


@pytest.mark.parametrize("disposition", ["card", "native"])
@pytest.mark.parametrize("phase", ["patch", "retry"])
@pytest.mark.parametrize("transport_result", [False, True])
async def test_generation_change_during_update_does_not_commit(disposition, phase, transport_result):
    entered, release = asyncio.Event(), asyncio.Event()
    owner = SimpleNamespace(terminal_delivery_state="pending", generation=1)
    accepted_generation = owner.generation
    current = lambda: owner.generation == accepted_generation

    class PausedTransport(Transport):
        async def patch(self, plan, *, is_current):
            self.calls.append(("patch", plan))
            assert is_current is current
            if phase == "patch":
                entered.set()
                await release.wait()
                return transport_result
            return False

        async def retry(self, plan, *, is_current):
            self.calls.append(("retry", plan))
            assert is_current is current
            entered.set()
            await release.wait()
            return transport_result

    transport = PausedTransport()
    task = asyncio.create_task(deliver_terminal(plan(disposition), owner, transport, is_current=current))
    await asyncio.wait_for(entered.wait(), 1)
    owner.generation += 1
    release.set()
    outcome = await task
    assert [call[0] for call in transport.calls] == (["patch"] if phase == "patch" else ["patch", "retry"])
    assert owner.terminal_delivery_state == "pending"
    assert outcome.superseded and not outcome.updated and not outcome.commit_native
    assert outcome.recovery is None


@pytest.mark.parametrize("recovery_result", ["delivered", "unknown", "not_sent"])
async def test_generation_change_during_recovery_keeps_claim_without_committing(recovery_result):
    entered, release = asyncio.Event(), asyncio.Event()
    owner = SimpleNamespace(terminal_delivery_state="pending", generation=1)
    accepted_generation = owner.generation

    class PausedRecovery(Transport):
        async def recover(self, accepted):
            entered.set()
            await release.wait()
            return await super().recover(accepted)

    transport = PausedRecovery(recovery=recovery_result)
    task = asyncio.create_task(deliver_terminal(
        plan(), owner, transport, is_current=lambda: owner.generation == accepted_generation,
    ))
    await asyncio.wait_for(entered.wait(), 1)
    assert owner.terminal_delivery_state == "recovering"
    owner.generation += 1
    release.set()
    outcome = await task
    assert [call[0] for call in transport.calls] == ["patch", "retry", "recover"]
    assert owner.terminal_delivery_state == "recovering"
    assert outcome.recovery.outcome == recovery_result
    assert outcome.superseded and not outcome.updated and not outcome.commit_native


async def test_reused_session_key_preserves_accepted_old_turn_delivery():
    entered, release = asyncio.Event(), asyncio.Event()
    accepted = plan()
    owner = SimpleNamespace(terminal_delivery_state="pending", generation=1)
    accepted_generation = owner.generation
    owners = {accepted.target.session_key: owner}

    class PausedPatch(Transport):
        async def patch(self, plan, *, is_current):
            self.calls.append(("patch", plan))
            entered.set()
            await release.wait()
            return is_current()

    transport = PausedPatch()
    task = asyncio.create_task(deliver_terminal(
        accepted, owner, transport, is_current=lambda: owner.generation == accepted_generation,
    ))
    await asyncio.wait_for(entered.wait(), 1)
    replacement = SimpleNamespace(terminal_delivery_state="pending", generation=1)
    owners[accepted.target.session_key] = replacement
    release.set()
    outcome = await task
    assert transport.calls == [("patch", accepted)]
    assert owner.terminal_delivery_state == "delivered"
    assert owners[accepted.target.session_key] is replacement
    assert replacement.terminal_delivery_state == "pending"
    assert outcome.updated and not outcome.superseded and not outcome.commit_native
