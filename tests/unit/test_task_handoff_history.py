"""A delivered continuation can retire task history without erasing it."""
import copy
import ast
import os
import subprocess

import pytest

from hermes_feishu_card import server
from hermes_feishu_card.card_limits import inspect_card_limits
from hermes_feishu_card.session import CardSession


def nodes(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from nodes(child)
    elif isinstance(value, list):
        for child in value:
            yield from nodes(child)


@pytest.fixture(autouse=True)
def exact_old_function_for_red(monkeypatch):
    if os.environ.get('HFC_HANDOFF_BASELINE') != '35bb47f':
        return
    raw = subprocess.check_output(['git', 'show', '35bb47f:hermes_feishu_card/server.py'], text=True)
    tree = ast.parse(raw)
    node = next(n for n in tree.body if isinstance(n, ast.FunctionDef)
                and n.name == '_render_static_display_card')
    unit = ast.Module(body=[ast.ImportFrom(module='__future__', names=[ast.alias(name='annotations')], level=0), node], type_ignores=[])
    namespace = dict(vars(server))
    exec(compile(ast.fix_missing_locations(unit), 'git-35bb47f-static-display.py', 'exec'), namespace)
    monkeypatch.setattr(server, '_render_static_display_card', namespace['_render_static_display_card'])


@pytest.fixture
def handoff(tmp_path, monkeypatch):
    monkeypatch.setenv('HERMES_FEISHU_CARD_STATE_DIR', str(tmp_path / 'state'))
    app = server.create_app(object(), card_config={'reading_preset': 'task'})
    app[server.SESSION_CARD_CONFIGS_KEY]['fixture'] = {'_presentation_mode': 'task'}
    session = CardSession('fixture', 'source_fixture', 'chat_fixture')
    session.answer_text = 'PRESERVED_BODY_BEGIN\n\nPRESERVED_BODY_END'
    session.thinking_text = 'PRESERVED_THINKING_END'
    session.timeline.record_reasoning('PRESERVED_THINKING_END')
    return app, session


def render(app, session, state='display_handoff'):
    return server._render_static_display_card(
        app, copy.deepcopy(session), session_key='fixture',
        note='本段已转入续答，后续进展与结果见下方新卡', display_state=state,
    )


def test_task_handoff_blue_explicit_title_and_default_closed_history(handoff):
    app, session = handoff
    card = render(app, session)
    assert card is not None
    assert card['header']['template'] == 'blue'
    assert '已转入续答' in card['header']['title']['content']
    body = card['body']['elements']
    panels = [e for e in body if e.get('tag') == 'collapsible_panel'
              and e.get('header', {}).get('title', {}).get('content', '').startswith('此前内容（')]
    assert len(panels) == 1
    panel = panels[0]
    assert panel['expanded'] is False
    assert 'elements' in panel and 'children' not in panel
    assert 'PRESERVED_BODY_BEGIN' in str(panel['elements'])
    assert 'PRESERVED_BODY_END' in str(panel['elements'])
    assert 'PRESERVED_THINKING_END' in str(panel['elements'])
    for element in body:
        if element is not panel:
            assert 'PRESERVED_BODY_' not in str(element)
            assert 'PRESERVED_THINKING_END' not in str(element)
    ids = [n['element_id'] for n in nodes(card) if 'element_id' in n]
    assert len(ids) == len(set(ids))
    assert inspect_card_limits(card).safe
    assert '查看续答' not in str(card), 'never invent a missing navigation target'
    assert session.answer_text.endswith('PRESERVED_BODY_END')
    assert session.thinking_text == 'PRESERVED_THINKING_END'


def test_display_receipt_does_not_gain_handoff_history(handoff):
    app, session = handoff
    card = render(app, session, 'display_receipt')
    assert card is not None
    assert '此前内容（' not in str(card)
    assert 'PRESERVED_BODY_END' in str(card)


def test_classic_handoff_keeps_original_body_without_task_panel(handoff):
    app, session = handoff
    app[server.SESSION_CARD_CONFIGS_KEY]['fixture'] = {'_presentation_mode': 'classic'}
    card = render(app, session)
    assert card is not None
    assert '此前内容（' not in str(card)
    assert 'PRESERVED_BODY_END' in str(card)


def test_unsafe_static_history_is_not_replaced_with_placeholder(handoff, monkeypatch):
    app, session = handoff
    real = server._render_session_card_result_for_app
    def excessive(*args, **kwargs):
        result = real(*args, **kwargs)
        result.card['body']['elements'].append({'tag': 'markdown', 'content': 'X' * 30000})
        return result
    monkeypatch.setattr(server, '_render_session_card_result_for_app', excessive)
    assert render(app, session) is None
    assert session.answer_text.endswith('PRESERVED_BODY_END')


@pytest.mark.parametrize('tag', ['form', 'table', 'button', 'unknown'])
def test_transfer_refuses_unsupported_children_without_losing_original(tag):
    from hermes_feishu_card.owner_display_policy import collapsed_transfer_elements
    elements = [{'tag': 'markdown', 'element_id': 'old', 'content': 'KEEP_FULL_BODY'},
                {'tag': tag, 'element_id': 'unsupported'}]
    before = copy.deepcopy(elements)
    assert collapsed_transfer_elements(elements) is None
    assert elements == before


def test_transfer_flattens_existing_panel_and_preserves_markdown_ids_once():
    from hermes_feishu_card.owner_display_policy import collapsed_transfer_elements
    elements = [{'tag': 'markdown', 'element_id': 'main', 'content': 'BODY_END'},
                {'tag': 'collapsible_panel', 'element_id': 'auxiliary_timeline',
                 'expanded': True, 'elements': [{'tag': 'hr'},
                 {'tag': 'markdown', 'element_id': 'reasoning', 'content': 'THINK_END'}]}]
    before = copy.deepcopy(elements)
    result = collapsed_transfer_elements(elements)
    assert result is not None and len(result) == 1
    assert result[0]['expanded'] is False
    assert [e.get('tag') for e in result[0]['elements']] == ['markdown', 'hr', 'markdown']
    assert not any(e.get('tag') == 'collapsible_panel' for e in result[0]['elements'])
    assert elements == before


@pytest.mark.asyncio
async def test_unrenderable_handoff_does_not_patch_preserved_owner(handoff, monkeypatch):
    app, session = handoff
    app[server.FEISHU_MESSAGE_IDS_KEY]['fixture'] = 'new_confirmed'
    monkeypatch.setattr(server, '_render_static_display_card', lambda *a, **k: None)
    async def forbidden(*a, **k):
        raise AssertionError('must not replace the old preserved card')
    monkeypatch.setattr(server, '_update_card_for_app', forbidden)
    assert await server._retire_continuation_predecessor(
        app, 'fixture', 'old_preserved', copy.deepcopy(session), bot_id=None) is False
    assert app[server.FEISHU_MESSAGE_IDS_KEY]['fixture'] == 'new_confirmed'


@pytest.mark.asyncio
async def test_valid_navigation_stays_outside_closed_history(handoff, monkeypatch):
    from hermes_feishu_card.message_navigation import MessageNavigation
    app, session = handoff
    app[server.FEISHU_MESSAGE_IDS_KEY]['fixture'] = 'new_confirmed'
    captured = []
    async def update(*args, **kwargs):
        captured.append(copy.deepcopy(args[2]))
        return True
    monkeypatch.setattr(server, '_update_card_for_app', update)
    navigation = MessageNavigation('new_confirmed', 'chat_fixture',
        'https://applink.feishu.cn/client/chat/open?openChatId=chat_fixture&position=12')
    assert await server._retire_continuation_predecessor(
        app, 'fixture', 'old_preserved', copy.deepcopy(session), bot_id=None, navigation=navigation)
    card = captured[0]
    panel = next(e for e in card['body']['elements'] if e.get('tag') == 'collapsible_panel')
    assert '查看续答' not in str(panel)
    assert '查看续答' in str(card['body']['elements'])
    assert inspect_card_limits(card).safe


def test_continuation_docs_keep_full_history_and_navigation_contract():
    from pathlib import Path
    text = (Path(__file__).resolve().parents[2] / 'docs/wiki/interaction-continuation.md').read_text()
    for requirement in ('此前内容', '默认收起', '保持原旧卡', '不删除内容', '导航按钮仍在历史面板外'):
        assert requirement in text


def test_visual_docs_require_cross_card_and_denial_semantics():
    from pathlib import Path
    text = (Path(__file__).resolve().parents[2] / 'docs/wiki/card-visual-guidelines.md').read_text()
    for requirement in ('跨卡检查', '旧段、交互回执与最终回复', '明确标识并默认收起', '已拒绝的工具不能显示成功对勾'):
        assert requirement in text


@pytest.mark.asyncio
@pytest.mark.parametrize('receipt_confirmed', [True, False])
async def test_collapsed_receipt_scope_prunes_only_after_full_receipt_confirmation(
        handoff, monkeypatch, receipt_confirmed):
    from hermes_feishu_card.session import InteractionState
    app, owner = handoff
    owner.status = 'completed'
    owner.active_interaction = InteractionState(
        'approval_fixture', 'approval', 'FULL_AUTHORIZATION_SCOPE',
        status='completed', choice='deny', choice_label='拒绝',
        feishu_message_id='independent_receipt', callback_token='synthetic_old_token')
    app[server.SESSIONS_KEY]['fixture'] = owner
    app[server.FEISHU_MESSAGE_IDS_KEY]['fixture'] = 'new_confirmed'
    card = {'schema': '2.0', 'body': {'elements': [{
        'tag': 'collapsible_panel', 'element_id': 'previous_content', 'expanded': False,
        'elements': [
            {'tag': 'markdown', 'element_id': 'main_content', 'content': 'FULL_HISTORY_END'},
            {'tag': 'markdown', 'element_id': 'interaction_review_scope', 'content': 'FULL_AUTHORIZATION_SCOPE'},
            {'tag': 'markdown', 'element_id': 'interaction_result', 'content': 'DECISION_DENIED'},
        ]}]}}
    monkeypatch.setattr(server, '_render_static_display_card', lambda *a, **k: copy.deepcopy(card))
    monkeypatch.setattr(server, '_interaction_mode_for_session_key', lambda *a: 'callback')
    full_receipt = {'schema': '2.0', 'body': {'elements': [
        {'tag': 'markdown', 'content': 'FULL_AUTHORIZATION_SCOPE DECISION_DENIED'}]}}
    monkeypatch.setattr(server, '_render_interaction_callback_card_for_app', lambda *a, **k: copy.deepcopy(full_receipt))
    updates = []
    async def update(app, mid, payload, bot_id, **kwargs):
        updates.append((mid, copy.deepcopy(payload)))
        return receipt_confirmed if mid == 'independent_receipt' else True
    monkeypatch.setattr(server, '_update_card_for_app', update)
    retire = server._retire_continuation_predecessor
    if os.environ.get('HFC_RECEIPT_BASELINE') == '35bb47f':
        raw = subprocess.check_output(['git', 'show', '35bb47f:hermes_feishu_card/server.py'], text=True)
        node = next(n for n in ast.parse(raw).body if isinstance(n, ast.AsyncFunctionDef)
                    and n.name == '_retire_continuation_predecessor')
        unit = ast.Module(body=[ast.ImportFrom(module='__future__', names=[ast.alias(name='annotations')], level=0), node], type_ignores=[])
        namespace = dict(vars(server))
        exec(compile(ast.fix_missing_locations(unit), 'git-35bb47f-retire.py', 'exec'), namespace)
        retire = namespace['_retire_continuation_predecessor']
    assert await retire(app, 'fixture', 'old_preserved', copy.deepcopy(owner), bot_id=None)
    assert 'FULL_AUTHORIZATION_SCOPE' in str(updates[0][1])
    assert 'DECISION_DENIED' in str(updates[0][1])
    assert len(owner.approval_retirements) == 1
    pending = owner.approval_retirements[0]
    assert pending['interaction'].callback_token == ''
    assert 'FULL_HISTORY_END' in str(pending['card'])
    assert 'FULL_AUTHORIZATION_SCOPE' not in str(pending['card'])
    assert len(updates) == 1, 'not pruned on registration before receipt ACK'
    await server._settle_approval_displays(app, 'fixture', owner)
    assert updates[1][0] == 'independent_receipt'
    assert 'FULL_AUTHORIZATION_SCOPE' in str(updates[1][1])
    if receipt_confirmed:
        assert len(updates) == 3 and updates[2][0] == 'old_preserved'
        assert 'FULL_HISTORY_END' in str(updates[2][1])
        assert 'FULL_AUTHORIZATION_SCOPE' not in str(updates[2][1])
        assert 'DECISION_DENIED' not in str(updates[2][1])
        assert owner.approval_retirements == []
    else:
        assert len(updates) == 2
        assert len(owner.approval_retirements) == 1
        assert 'FULL_AUTHORIZATION_SCOPE' in str(updates[0][1])
