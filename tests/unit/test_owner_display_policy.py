"""Current-owner replacement choices keep input and receipt ownership distinct."""
from dataclasses import FrozenInstanceError, replace

import pytest

from hermes_feishu_card.owner_display_policy import OwnerRefreshState


def state(**changes):
    return replace(OwnerRefreshState(
        event_kind="answer.delta", is_terminal=False, owner_message_id="owner",
        interaction_present=True, interaction_status="pending", interaction_message_id="owner",
        has_receipt_fingerprint=False, has_legacy_owner_receipt=False,
    ), **changes)


@pytest.mark.parametrize("status", ["pending", "paused"])
@pytest.mark.parametrize("kind,terminal,expected", [
    ("answer.delta", False, True), ("tool.updated", False, True),
    ("interaction.completed", False, False), ("interaction.failed", False, False),
    ("message.completed", True, False),
])
def test_live_inputs_freeze_ordinary_replacement_with_lifecycle_and_terminal_exceptions(status, kind, terminal, expected):
    snapshot = state(interaction_status=status, event_kind=kind, is_terminal=terminal)
    assert snapshot.freezes_inputs is expected


@pytest.mark.parametrize("changes", [
    {"interaction_present": False}, {"interaction_status": "completed"},
    {"interaction_status": "failed"}, {"interaction_status": None},
])
def test_absent_or_closed_interaction_does_not_freeze_owner(changes):
    assert not state(**changes).freezes_inputs


@pytest.mark.parametrize("changes,expected", [
    ({"event_kind": "interaction.failed", "has_receipt_fingerprint": True}, True),
    ({"event_kind": "interaction.failed", "has_receipt_fingerprint": False}, False),
    ({"event_kind": "interaction.completed", "has_receipt_fingerprint": True}, False),
    ({"event_kind": "interaction.failed", "has_receipt_fingerprint": True, "interaction_present": False}, False),
])
def test_failed_receipt_refresh_is_independent_of_later_card_source(changes, expected):
    assert state(**changes).refresh_failed_receipt_first is expected


@pytest.mark.parametrize("changes,modes,expected,calls", [
    ({}, ["callback"], "current_render", 0),
    ({"event_kind": "interaction.failed", "interaction_present": False}, ["callback"], "current_render", 0),
    ({"event_kind": "interaction.failed", "interaction_message_id": "aux", "has_legacy_owner_receipt": True}, ["callback"], "separate_receipt", 0),
    ({"event_kind": "interaction.failed", "interaction_message_id": "aux"}, ["text"], "separate_receipt", 1),
    ({"event_kind": "interaction.failed", "interaction_message_id": "aux"}, ["callback"], "current_render", 1),
    ({"event_kind": "interaction.failed"}, ["callback"], "callback_owner", 1),
    ({"event_kind": "interaction.failed"}, ["text"], "current_render", 1),
    ({"event_kind": "interaction.failed", "interaction_status": "failed"}, ["text", "text"], "text_receipt_owner", 2),
    ({"event_kind": "interaction.completed", "interaction_status": "completed"}, ["other", "other"], "current_render", 2),
    ({"event_kind": "interaction.completed", "interaction_status": "completed"}, ["text", "callback"], "current_render", 2),
    ({"event_kind": "interaction.failed", "interaction_message_id": ""}, ["callback"], "current_render", 0),
    # Empty equality is deliberately kept for the old helper's permissive shape.
    ({"event_kind": "interaction.failed", "interaction_message_id": "", "owner_message_id": ""}, ["callback"], "callback_owner", 1),
])
def test_original_mode_short_circuit_count_and_owner_routing(changes, modes, expected, calls):
    snapshot = state(**changes)
    seen = []

    def mode():
        seen.append(len(seen))
        assert len(seen) <= len(modes), "unexpected mode query"
        return modes[len(seen) - 1]

    assert snapshot.card_source(mode) == expected
    assert len(seen) == calls


def test_required_mode_failure_propagates_and_legacy_separate_branch_never_queries():
    failure = RuntimeError("mode fixture failure")

    def fail():
        raise failure

    with pytest.raises(RuntimeError) as caught:
        state(event_kind="interaction.completed", interaction_status="completed").card_source(fail)
    assert caught.value is failure
    assert state(event_kind="interaction.failed", interaction_message_id="aux",
                 has_legacy_owner_receipt=True).card_source(fail) == "separate_receipt"


def test_snapshot_is_frozen_read_only_and_repr_omits_message_identifiers():
    snapshot = state(event_kind="interaction.failed", interaction_status="failed", has_receipt_fingerprint=True,
                     owner_message_id="private-message-id", interaction_message_id="private-message-id")
    before = replace(snapshot)
    assert snapshot.refresh_failed_receipt_first and not snapshot.freezes_inputs
    assert snapshot.card_source(lambda: "text") == "text_receipt_owner"
    assert snapshot == before
    with pytest.raises(FrozenInstanceError):
        snapshot.owner_message_id = "replaced"
    assert "private-message-id" not in repr(snapshot)
