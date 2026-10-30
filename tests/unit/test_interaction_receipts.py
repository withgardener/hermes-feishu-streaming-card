from copy import deepcopy
import json

import pytest

from hermes_feishu_card.interaction_receipts import build_auxiliary_receipt
from hermes_feishu_card.legacy_owner import auxiliary_receipt_card
from hermes_feishu_card.session import CardSession, InteractionOption, InteractionState


def source(status='pending'):
    interaction = InteractionState(
        interaction_id='interaction', kind='approval', prompt='Review operation',
        description='SCOPE-BEGIN\ncommand --token scope-secret\nSCOPE-END',
        status=status, callback_token='callback-secret', feishu_message_id='aux-message',
        choice='yes', choice_label='Approved option', error='Failure detail',
        options=[InteractionOption(value='yes', label='Approve operation')],
        runtime_admission={'token': 'admission-secret'},
    )
    return CardSession(conversation_id='c', message_id='m', chat_id='chat', active_interaction=interaction)


def project(session, *, owner='main-message', dialect='legacy'):
    return build_auxiliary_receipt(session, owner, title='Review title', profile_id='default',
                                   presentation='classic', mentions_enabled=False, dialect=dialect)


@pytest.mark.parametrize('status', ['pending', 'paused', 'completed', 'failed'])
@pytest.mark.parametrize('dialect', ['legacy', '2.0'])
def test_projection_preserves_source_scope_and_original_wire_dialect(status, dialect):
    session = source(status)
    session_before = dict(vars(session))
    interaction_before = deepcopy(session.active_interaction)
    receipt = project(session, dialect=dialect)
    assert vars(session) == session_before
    assert session.active_interaction == interaction_before
    assert receipt['message_id'] == 'aux-message'
    assert receipt['template'] == ('green' if status == 'completed' else 'red')
    assert receipt['dialect'] == dialect
    card = auxiliary_receipt_card(receipt)
    body = card['body']['elements'] if dialect == '2.0' else card['elements']
    assert (card.get('schema') == '2.0') == (dialect == '2.0')
    text = json.dumps(card, ensure_ascii=False)
    for retained in ('Review operation', 'SCOPE-BEGIN', 'SCOPE-END', 'command --token', 'Approve operation'):
        assert retained in text
    for secret in ('scope-secret', 'callback-secret', 'admission-secret'):
        assert secret not in text
    assert all(set(element) <= {'tag', 'content'} for element in body)
    assert all(element['tag'] in {'markdown', 'hr'} for element in body)
    if status in {'pending', 'paused'}:
        assert '连接已重建' in text
    elif status == 'completed':
        assert 'Approved option' in text
        assert '连接已重建' not in text
    else:
        assert 'Failure detail' in text
        assert '连接已重建' not in text


@pytest.mark.parametrize('case', ['no-interaction', 'no-message', 'same-owner'])
def test_no_auxiliary_receipt_without_distinct_delivered_message(case):
    session = source()
    owner = 'main-message'
    if case == 'no-interaction':
        session.active_interaction = None
    elif case == 'no-message':
        session.active_interaction.feishu_message_id = ''
    else:
        owner = 'aux-message'
    assert project(session, owner=owner) is None


@pytest.mark.parametrize('dialect', ['legacy', '2.0'])
def test_oversized_scope_is_rejected_without_trimming_source(dialect):
    session = source('completed')
    session.active_interaction.description = 'BEGIN\n' + 'full-scope-line\n' * 20000 + 'END'
    original = deepcopy(session.active_interaction)
    with pytest.raises(ValueError, match='exceeds bounds'):
        project(session, dialect=dialect)
    assert session.active_interaction == original


@pytest.mark.parametrize('dialect', ['legacy', '2.0'])
def test_projector_rejects_oversized_renderer_output(monkeypatch, dialect):
    from hermes_feishu_card import interaction_receipts
    session = source('completed')
    original = deepcopy(session.active_interaction)

    def oversized(*args, **kwargs):
        return {'header': {'title': {'content': 'Title'}},
                'elements': [{'tag': 'markdown', 'content': 'x' * 40000}]}

    monkeypatch.setattr(interaction_receipts, 'render_legacy_interaction_callback_card', oversized)
    with pytest.raises(ValueError, match='exceeds bounds'):
        project(session, dialect=dialect)
    assert session.active_interaction == original
