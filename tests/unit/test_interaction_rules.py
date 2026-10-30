"""Approval renewal eligibility preserves the live-waiter cutoff without consent."""
from dataclasses import replace

import pytest

from hermes_feishu_card.interaction_rules import ApprovalWindowState, approval_window_can_reopen


def window(**changes):
    return replace(ApprovalWindowState("thinking", "paused", True, False, 90.0), **changes)


@pytest.mark.parametrize("last_poll,expected", [(85.001, True), (85.0, True), (84.999, False), (0.0, False), (101.0, True)])
def test_waiter_freshness_keeps_inclusive_15_second_boundary(last_poll, expected):
    # A future timestamp retains the established behavior of the old predicate;
    # this source move must not silently add a separate clock policy.
    state = window(last_waiter_poll_at=last_poll)
    assert approval_window_can_reopen(state, now=100.0) is expected
    assert state.last_waiter_poll_at == last_poll


@pytest.mark.parametrize("changes", [
    {"session_status": "completed"}, {"session_status": "failed"},
    {"interaction_status": "pending"}, {"interaction_status": "completed"},
    {"interaction_status": "failed"}, {"pause_on_timeout": False},
    {"has_runtime_admission": True},
])
def test_other_owners_or_closed_windows_cannot_be_reopened_even_with_fresh_waiter(changes):
    assert not approval_window_can_reopen(window(**changes), now=100.0)


def test_reopen_eligibility_is_only_a_read_only_decision_for_the_same_window():
    state = window(session_status="tool_running")
    before = replace(state)
    assert approval_window_can_reopen(state, now=100.0)
    assert state == before


def callback_window():
    from hermes_feishu_card.interaction_rules import RuntimeCallbackSnapshot, runtime_admission_fingerprint
    from hermes_feishu_card.session import CardSession, InteractionState

    descriptor = {'token': 'secret-token', 'expires_at': 100.0, 'runtime_id': 'runtime'}
    interaction = InteractionState(interaction_id='interaction', kind='approval', prompt='approve',
                                   callback_token='callback-secret', runtime_admission=dict(descriptor))
    session = CardSession(conversation_id='session', message_id='message', chat_id='chat', active_interaction=interaction)
    snapshot = RuntimeCallbackSnapshot(session, interaction, 'interaction', 'callback-secret',
                                       'chat', runtime_admission_fingerprint(descriptor),
                                       descriptor, 'yes', 'turn')
    return session, interaction, snapshot


def test_callback_snapshot_uses_object_identity_not_equal_fields():
    session, interaction, snapshot = callback_window()
    assert snapshot.is_current(session)
    assert not snapshot.is_current(None)
    equal_session = replace(session)
    assert equal_session == session
    assert not snapshot.is_current(equal_session)
    session.active_interaction = replace(interaction)
    assert session.active_interaction == interaction
    assert not snapshot.is_current(session)
    session.active_interaction = None
    assert not snapshot.is_current(session)


@pytest.mark.parametrize('field,value', [
    ('interaction_id', 'other'), ('callback_token', 'other'),
    ('status', 'resolved'), ('status', 'paused'), ('status', 'failed'),
    ('runtime_admission', None),
    ('runtime_admission', {'token': 'changed', 'expires_at': 100.0, 'runtime_id': 'runtime'}),
])
def test_callback_snapshot_rejects_changed_interaction_field(field, value):
    session, interaction, snapshot = callback_window()
    setattr(interaction, field, value)
    assert not snapshot.is_current(session)


def test_callback_snapshot_rechecks_chat_and_in_place_descriptor_drift():
    session, interaction, snapshot = callback_window()
    session.chat_id = 'other'
    assert not snapshot.is_current(session)
    session.chat_id = 'chat'
    interaction.runtime_admission['expires_at'] = 101.0
    assert not snapshot.is_current(session)
    assert snapshot.descriptor['expires_at'] == 100.0


def test_callback_snapshot_has_no_expiry_mutation_claim_or_sequence_policy():
    from copy import deepcopy
    session, interaction, snapshot = callback_window()
    # Currentness is deliberately only one gate. The coordinator still owns
    # expiry after I/O and assigns the then-current sequence under its lock.
    session.last_sequence = 99
    interaction.requested_at = 0
    interaction.timeout_seconds = 0
    before = dict(vars(session))
    interaction_before = deepcopy(interaction)
    assert snapshot.is_current(session)
    assert vars(session) == before
    assert interaction == interaction_before
    assert interaction.runtime_admission is not None


def test_callback_snapshot_fields_are_frozen_and_repr_does_not_expose_tokens():
    from dataclasses import FrozenInstanceError
    _, _, snapshot = callback_window()
    with pytest.raises(FrozenInstanceError):
        snapshot.callback_token = 'replacement'
    assert 'secret-token' not in repr(snapshot)
    assert 'callback-secret' not in repr(snapshot)


def test_runtime_admission_fingerprint_is_canonical_and_rejects_non_json():
    from hermes_feishu_card.interaction_rules import runtime_admission_fingerprint
    original = {'token': 'secret', 'expires_at': 100.0}
    assert runtime_admission_fingerprint(original) == runtime_admission_fingerprint(dict(reversed(list(original.items()))))
    assert runtime_admission_fingerprint(original) != runtime_admission_fingerprint({**original, 'expires_at': 101.0})
    for invalid in ({'expires_at': float('nan')}, {'unsupported': object()}, {'text': '\ud800'}):
        assert runtime_admission_fingerprint(invalid) == ''


@pytest.mark.parametrize('change', ['none', 'equal-session', 'missing-session', 'missing-interaction', 'id', 'token', 'chat'])
@pytest.mark.parametrize('pending', [False, True])
def test_callback_rejection_keeps_identity_before_reservation(change, pending):
    from hermes_feishu_card.interaction_rules import callback_rejection
    session, interaction, _ = callback_window()
    current = session
    if change == 'equal-session': current = replace(session)
    elif change == 'missing-session': current = None
    elif change == 'missing-interaction': session.active_interaction = None
    elif change == 'id': interaction.interaction_id = 'other'
    elif change == 'token': interaction.callback_token = 'other'
    elif change == 'chat': session.chat_id = 'other'
    result = callback_rejection(session, current, interaction_id='interaction',
                                callback_token='callback-secret', chat_id='chat', delivery_pending=pending)
    assert result == ('not_found' if change != 'none' else 'delivery_pending' if pending else None)


@pytest.mark.parametrize('deadline,window_expired,expected,window_calls', [
    (100, False, True, 0), (100.0, False, True, 0), (101, False, False, 1),
    (101, True, True, 1), (True, False, False, 1), ('99', False, False, 1),
    (None, True, True, 1), (float('nan'), False, False, 1),
])
def test_runtime_deadline_exact_types_inclusive_boundary_and_short_circuit(deadline, window_expired, expected, window_calls):
    from hermes_feishu_card.interaction_rules import runtime_admission_has_expired
    _, interaction, _ = callback_window()
    interaction.runtime_admission = {'expires_at': deadline}
    calls = []
    interaction.is_expired = lambda now: calls.append(now) or window_expired
    before = dict(vars(interaction))
    assert runtime_admission_has_expired(interaction, now=100.0) is expected
    assert len(calls) == window_calls
    assert vars(interaction) == before


@pytest.mark.parametrize('status,admission', [('completed', {'expires_at': 0}), ('paused', {'expires_at': 0}), ('pending', None)])
def test_runtime_deadline_does_not_touch_unowned_or_closed_windows(status, admission):
    from hermes_feishu_card.interaction_rules import runtime_admission_has_expired
    _, interaction, _ = callback_window()
    interaction.status, interaction.runtime_admission = status, admission
    def forbidden(now):
        pytest.fail('closed/unowned window deadline queried')
    interaction.is_expired = forbidden
    assert not runtime_admission_has_expired(interaction, now=100)


@pytest.mark.parametrize('kind,data,native,runtime', [
    ('interaction.requested', {'fallback_policy': ' NATIVE_TEXT '}, True, False),
    ('interaction.requested', {'_hfc_runtime_admission': {}}, False, True),
    ('message.started', {'fallback_policy': 'native_text', '_hfc_runtime_admission': {}}, False, False),
    ('interaction.requested', None, False, False),
    ('interaction.requested', {'_hfc_runtime_admission': []}, False, False),
])
def test_text_request_predicates_keep_original_input_shape(kind, data, native, runtime):
    from types import SimpleNamespace
    from hermes_feishu_card.interaction_rules import native_text_fallback_requested, runtime_text_decline_requested
    event = SimpleNamespace(event=kind, data=data)
    assert native_text_fallback_requested(event) is native
    assert runtime_text_decline_requested(event) is runtime


def test_text_request_dict_subclass_distinction_and_mode_short_circuit(monkeypatch):
    from types import SimpleNamespace
    from hermes_feishu_card import server
    from hermes_feishu_card.interaction_rules import native_text_fallback_requested, runtime_text_decline_requested
    class Subdict(dict): pass
    event = SimpleNamespace(event='interaction.requested', data=Subdict(fallback_policy='native_text', _hfc_runtime_admission={}))
    assert native_text_fallback_requested(event)
    assert not runtime_text_decline_requested(event)
    event.data = {'_hfc_runtime_admission': Subdict()}
    assert not runtime_text_decline_requested(event)
    def forbidden(*args): pytest.fail('irrelevant event consulted app mode')
    monkeypatch.setattr(server, '_interaction_mode_for_session_key', forbidden)
    event = SimpleNamespace(event='message.started', data={})
    assert not server._skip_native_text_fallback_interaction({}, event)
    assert not server._decline_runtime_interaction_in_text_mode({}, event)
