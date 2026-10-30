"""Disposable preflight preserves committed ownership and transport sequence."""
from copy import deepcopy
from types import SimpleNamespace

import pytest

from hermes_feishu_card import interaction_rules as rules
from hermes_feishu_card.events import SidecarEvent
from hermes_feishu_card.session import CardSession, InteractionState


def requested(*, sequence=2, **data):
    return SidecarEvent.from_dict({
        "schema_version": "1", "event": "interaction.requested",
        "conversation_id": "fixture-conversation", "message_id": "fixture-message",
        "chat_id": "fixture-chat", "platform": "feishu", "sequence": sequence,
        "created_at": 100.0,
        "data": {"interaction_id": "new", "kind": "approval", "prompt": "Review",
                 "options": [{"label": "Allow once", "value": "once"}], **data},
    })


def owner():
    session = CardSession(conversation_id="fixture-conversation", message_id="fixture-message",
                          chat_id="fixture-chat", route_profile_id="original", last_sequence=1)
    session.active_interaction = InteractionState(interaction_id="old", kind="approval", prompt="Old",
                                                 callback_token="fixture-old", runtime_admission={"nested": [1]})
    session.timeline.record_reasoning("Original reasoning")
    session.observation.last_observed = 1.0
    return session


def owner_state(session):
    # Normalizers have identity equality; compare their stored content instead.
    return deepcopy({key: vars(value) if key in {"thinking_normalizer", "answer_normalizer"}
                     else value for key, value in vars(session).items()})


def forbidden(*args, **kwargs):
    pytest.fail("irrelevant or duplicate preflight consulted a dependency")


def test_irrelevant_event_does_not_copy_apply_construct_or_render(monkeypatch):
    monkeypatch.setattr(rules, "deepcopy", forbidden)
    monkeypatch.setattr(rules, "CardSession", forbidden)
    monkeypatch.setattr(rules, "policy_profile_id", forbidden)
    assert rules.interaction_preflight_rejection(SimpleNamespace(event="message.started"), None,
        advance_sequence=True, render_disposition=forbidden) is None


@pytest.mark.parametrize("disposition", ["card", "native", "deferred_native"])
@pytest.mark.parametrize("advance", [False, True])
def test_existing_owner_is_deeply_isolated_and_sequence_policy_reaches_apply(monkeypatch, disposition, advance):
    session = owner()
    before = owner_state(session)
    old_interaction = session.active_interaction
    original_apply = CardSession.apply
    order = []
    monkeypatch.setattr(rules, "policy_profile_id", forbidden)

    def apply(preview, event, *, advance_sequence):
        assert preview is not session and preview.active_interaction is not old_interaction
        assert preview.timeline is not session.timeline and preview.observation is not session.observation
        assert preview.active_interaction.runtime_admission is not old_interaction.runtime_admission
        preview.active_interaction.runtime_admission["nested"].append(2)
        order.append(("apply", advance_sequence))
        return original_apply(preview, event, advance_sequence=advance_sequence)

    def render(preview):
        assert order == [("apply", advance)]
        assert preview.active_interaction.interaction_id == "new"
        assert preview.last_sequence == (2 if advance else 1)
        assert preview.route_profile_id == "original"
        preview.timeline.record_reasoning("Disposable rendering mutation")
        preview.observation.clock_valid = False
        preview.active_interaction.callback_token = "discarded"
        order.append(("render", None))
        return disposition

    monkeypatch.setattr(CardSession, "apply", apply)
    assert rules.interaction_preflight_rejection(requested(), session,
        advance_sequence=advance, render_disposition=render) == (
            None if disposition == "card" else "interaction_card_limit")
    assert order == [("apply", advance), ("render", None)]
    assert owner_state(session) == before and session.active_interaction is old_interaction


@pytest.mark.parametrize("profile,expected", [(None, "default"), ("", "default"), ("tenant-2", "tenant-2")])
def test_new_preview_binds_event_identity_and_profile_without_external_registration(profile, expected):
    event = requested(**({} if profile is None else {"profile_id": profile}))
    previews = []

    def render(preview):
        previews.append(preview)
        assert (preview.conversation_id, preview.message_id, preview.chat_id) == (
            event.conversation_id, event.message_id, event.chat_id)
        assert preview.route_profile_id == expected and preview.last_sequence == 2
        assert preview.active_interaction.interaction_id == "new"
        return "native"

    assert rules.interaction_preflight_rejection(event, None,
        advance_sequence=True, render_disposition=render) == "interaction_card_limit"
    assert len(previews) == 1


@pytest.mark.parametrize("sequence", [0, 1])
def test_duplicate_and_stale_request_do_not_render_or_reject(sequence):
    session = owner()
    before = owner_state(session)
    assert rules.interaction_preflight_rejection(requested(sequence=sequence), session,
        advance_sequence=False, render_disposition=forbidden) is None
    assert owner_state(session) == before


@pytest.mark.parametrize("stage", ["copy", "apply", "render"])
def test_preview_failures_propagate_original_exception_without_mutating_owner(monkeypatch, stage):
    session = owner()
    before = owner_state(session)
    failure = RuntimeError("preflight fixture failure")

    def fail(*args, **kwargs):
        raise failure

    render = lambda preview: "card"
    if stage == "copy":
        monkeypatch.setattr(rules, "deepcopy", fail)
    elif stage == "apply":
        monkeypatch.setattr(CardSession, "apply", fail)
    else:
        render = fail
    with pytest.raises(RuntimeError) as caught:
        rules.interaction_preflight_rejection(requested(), session,
            advance_sequence=True, render_disposition=render)
    assert caught.value is failure and owner_state(session) == before
