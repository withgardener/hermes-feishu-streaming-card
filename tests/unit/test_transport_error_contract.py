"""One shared error identity without CardKit's reverse client dependency."""
import ast
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import get_args

import pytest

from hermes_feishu_card import cardkit, delivery, feishu_client


@pytest.mark.parametrize('kwargs', [
    {},
    {'status_code': 400, 'api_code': 99991672},
    {'status_code': 503, 'api_code': 'busy', 'retryable': True,
     'outcome': 'unknown', 'retry_after_seconds': 1.5, 'retry_count': 2},
    {'status_code': 429, 'retryable': True, 'outcome': 'not_sent',
     'retry_after_seconds': 0.0, 'retry_count': 0},
])
def test_old_public_error_import_is_shared_and_retains_all_fields(kwargs):
    assert feishu_client.FeishuAPIError is delivery.FeishuAPIError
    assert cardkit.FeishuAPIError is delivery.FeishuAPIError
    assert feishu_client.DeliveryFailureOutcome is delivery.DeliveryFailureOutcome
    assert get_args(delivery.DeliveryFailureOutcome) == ('not_sent', 'unknown')
    error = delivery.FeishuAPIError('safe failure', **kwargs)
    assert isinstance(error, RuntimeError)
    assert str(error) == 'safe failure' and error.args == ('safe failure',)
    defaults = {'status_code': None, 'api_code': None, 'retryable': False,
                'outcome': 'not_sent', 'retry_after_seconds': None, 'retry_count': 0}
    assert vars(error) == {**defaults, **kwargs}
    with pytest.raises(feishu_client.FeishuAPIError) as caught:
        raise error
    assert caught.value is error


@pytest.mark.parametrize('owner', ['delivery', 'cardkit'])
def test_fresh_transport_owner_does_not_import_client_or_state(tmp_path, owner):
    root = Path(delivery.__file__).resolve().parent.parent
    code = '''
import importlib, json, pathlib, sys
sys.path.insert(0, sys.argv[1])
m=importlib.import_module('hermes_feishu_card.'+sys.argv[2])
assert pathlib.Path(m.__file__).resolve().parent.parent == pathlib.Path(sys.argv[1])
for name in ('hermes_feishu_card.feishu_client', 'hermes_feishu_card.render',
             'hermes_feishu_card.session', 'hermes_feishu_card.config', 'aiohttp'):
    assert name not in sys.modules, name
assert m.FeishuAPIError('failure').outcome == 'not_sent'
print(json.dumps({'owner':m.__name__,'closed':True}))
'''
    env = dict(os.environ, HOME=str(tmp_path), USERPROFILE=str(tmp_path),
               HERMES_FEISHU_CARD_STATE_DIR=str(tmp_path / 'state'))
    result = subprocess.run([sys.executable, '-I', '-c', code, str(root), owner],
                            cwd=tmp_path, env=env, text=True, capture_output=True, timeout=10)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)['closed'] is True


def test_cardkit_has_no_lazy_or_eager_client_dependency():
    tree = ast.parse(Path(cardkit.__file__).read_text())
    assert not any(isinstance(node, ast.ImportFrom) and node.module == 'feishu_client'
                   for node in ast.walk(tree))
    assert any(isinstance(node, ast.ImportFrom) and node.module == 'delivery'
               and any(alias.name == 'FeishuAPIError' for alias in node.names)
               for node in tree.body)


@pytest.mark.asyncio
@pytest.mark.parametrize('stage', ['create', 'im'])
async def test_cardkit_wraps_shared_failure_and_preserves_stage_outcome(stage, monkeypatch):
    client = feishu_client.FeishuClient(feishu_client.FeishuClientConfig('fixture-app', 'fixture-secret'))
    failure = delivery.FeishuAPIError('safe upstream failure', status_code=503,
                                     retryable=True, outcome='unknown', retry_count=2)
    calls = []

    async def token():
        return 'synthetic-token'

    async def request(method, path, **kwargs):
        calls.append(path)
        if path == '/cardkit/v1/cards' and stage != 'create':
            return {'code': 0, 'data': {'card_id': 'card_fixture'}}
        raise failure

    async def no_sleep(delay):
        return None

    monkeypatch.setattr(feishu_client, '_sleep', no_sleep)
    monkeypatch.setattr(client, '_tenant_token', token)
    monkeypatch.setattr(client, '_request_json', request)
    card = {'schema': '2.0', 'config': {'streaming_mode': True},
            'body': {'elements': [{'tag': 'markdown', 'content': 'synthetic body'}]}}
    with pytest.raises(feishu_client.FeishuAPIError) as caught:
        await client.send_card('oc_synthetic', card, delivery_uuid='synthetic-turn')
    assert caught.value.__cause__ is failure
    assert caught.value.outcome == ('not_sent' if stage == 'create' else 'unknown')
    assert caught.value.retry_count == (0 if stage == 'create' else 2)
    assert caught.value.retryable is True and caught.value.status_code == 503
    assert failure.outcome == 'unknown' and failure.retry_count == 2
    assert len(calls) == (1 if stage == 'create' else 4)
    assert not client.cardkit.entities
