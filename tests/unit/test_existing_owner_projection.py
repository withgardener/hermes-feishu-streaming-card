"""Original legacy-owner projection, laziness and full overflow evidence."""
import ast
import copy
from dataclasses import asdict
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from hermes_feishu_card.card_limits import inspect_card_limits
from hermes_feishu_card.existing_owner_projection import project_existing_owner
from hermes_feishu_card.render import CardRenderResult
from hermes_feishu_card.text import TableOverflowResult

FROZEN = json.loads((Path(__file__).parents[1] / 'fixtures' / 'existing_owner_projection_193bf60.json').read_text())


@pytest.mark.parametrize('case', FROZEN['cases'], ids=[c['name'] for c in FROZEN['cases']])
def test_projection_matches_original_owner_card_and_overflow_evidence(case):
    counts = {'live': 0, 'title': 0}

    def live():
        counts['live'] += 1
        return copy.deepcopy(case['live_card'])

    def title():
        counts['title'] += 1
        return case['title']

    receipt, card = copy.deepcopy(case['receipt']), copy.deepcopy(case['card'])
    before = copy.deepcopy((receipt, card))
    result = CardRenderResult(card, case['disposition'], inspect_card_limits(card),
                              TableOverflowResult('canonical table', 1),
                              limit_reason='original_reason', primary_text=case['primary_text'])
    actual = project_existing_owner(result, receipt=receipt, terminal=case['terminal'],
                                    live_card=live, title=title)
    assert json.loads(json.dumps(asdict(actual))) == case['expected']
    assert (actual is result) is case['returned_original_result']
    assert (receipt, card) == before
    assert actual.table_overflow is result.table_overflow
    assert actual.primary_text == result.primary_text
    gated = not receipt or card.get('schema') != '2.0'
    assert counts['live'] == (0 if gated else 1)
    assert counts['title'] == case['old_external_call_counts']['title_context']
    if case['name'] == 'receipt-original-fallback':
        assert actual.card == receipt and actual.card is not receipt
        assert inspect_card_limits(actual.card).safe and not actual.inspection.safe


def test_zero_suppliers_are_called_for_an_ordinary_owner():
    result = CardRenderResult({'schema': '2.0', 'body': {'elements': []}}, 'card',
                             inspect_card_limits({}), TableOverflowResult('', 0))

    def forbidden():
        pytest.fail('ordinary owner consulted a projection supplier')

    assert project_existing_owner(result, receipt={}, terminal=False,
                                  live_card=forbidden, title=forbidden) is result


def test_live_owner_does_not_consult_title_and_propagates_supplier_failure():
    result = CardRenderResult({'schema': '2.0', 'body': {'elements': []}}, 'native',
                             inspect_card_limits({}), TableOverflowResult('', 0))
    receipt = {'elements': [{'tag': 'markdown', 'content': 'original scope'}]}
    live = {'elements': [{'tag': 'input', 'name': 'synthetic-input'}]}

    def forbidden():
        pytest.fail('safe live owner consulted fallback title')

    actual = project_existing_owner(result, receipt=receipt, terminal=False,
                                    live_card=lambda: live, title=forbidden)
    assert actual.card is live and actual.disposition == 'card'
    failure = RuntimeError('synthetic render failed')

    def failed():
        raise failure

    with pytest.raises(RuntimeError) as caught:
        project_existing_owner(result, receipt=receipt, terminal=False,
                               live_card=failed, title=forbidden)
    assert caught.value is failure


def test_fresh_projection_import_does_not_initialize_server_or_io(tmp_path):
    import hermes_feishu_card.existing_owner_projection as projection

    root = Path(projection.__file__).resolve().parent.parent
    code = '''
import pathlib,sys
sys.path.insert(0, sys.argv[1])
import hermes_feishu_card.existing_owner_projection as m
assert pathlib.Path(m.__file__).resolve().parent.parent == pathlib.Path(sys.argv[1])
for name in ('server','feishu_client','session_store','process'):
    assert 'hermes_feishu_card.'+name not in sys.modules, name
print('projection does not initialize coordinator or external I/O')
'''
    env = dict(os.environ, HOME=str(tmp_path), USERPROFILE=str(tmp_path),
               HERMES_FEISHU_CARD_STATE_DIR=str(tmp_path / 'state'))
    result = subprocess.run([sys.executable, '-I', '-c', code, str(root)], env=env,
                            cwd=tmp_path, capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stderr
    tree = ast.parse(Path(projection.__file__).read_text())
    assert not any(isinstance(n, ast.ImportFrom) and n.module == 'server' for n in ast.walk(tree))


@pytest.mark.parametrize('session_key', [None, 'resolved'])
@pytest.mark.parametrize('status,interaction_status,matching', [
    ('running', 'pending', True), ('running', 'paused', True),
    ('completed', 'pending', True), ('failed', 'paused', True),
    ('running', 'pending', False), ('running', 'completed', True),
    ('running', None, True),
])
def test_server_adapters_keep_owner_and_original_title_selector(monkeypatch, session_key, status, interaction_status, matching):
    from types import SimpleNamespace
    from hermes_feishu_card import server

    calls = []
    receipt = {'elements': [{'tag': 'markdown', 'content': 'ORIGINAL_SCOPE'}]}
    live = {'elements': [{'tag': 'input', 'name': 'synthetic-live-input'}]}
    interaction = None if interaction_status is None else SimpleNamespace(
        status=interaction_status, feishu_message_id='current' if matching else 'retired')
    session = SimpleNamespace(status=status, active_interaction=interaction,
                              legacy_owner_receipt=receipt)
    app = {server.FEISHU_MESSAGE_IDS_KEY: {'resolved': 'current'}}
    card = {'schema': '2.0', 'body': {'elements': []}}
    result = CardRenderResult(card, 'card', inspect_card_limits(card), TableOverflowResult('', 0))

    def resolve(*args):
        calls.append(('resolve',))
        return 'resolved'

    def render(*args, **kwargs):
        calls.append(('render', kwargs['session_key']))
        return live

    def title(*args, **kwargs):
        calls.append(('title', kwargs['session_key']))
        return ('resolved', {}, 'Synthetic title', {})

    monkeypatch.setattr(server, '_session_key_for_session', resolve)
    monkeypatch.setattr(server, '_render_interaction_callback_card_for_app', render)
    monkeypatch.setattr(server, '_session_card_render_context', title)
    actual = server._existing_owner_render_result(app, session, result, session_key=session_key)
    eligible = status not in {'completed', 'failed'} and interaction_status in {'pending', 'paused'} and matching
    assert ('resolve',) in calls if session_key is None else ('resolve',) not in calls
    assert ('render', 'resolved') in calls if eligible else ('render', 'resolved') not in calls
    assert ('title', session_key) not in calls if eligible else ('title', session_key) in calls
    assert (actual.card is live) is eligible
