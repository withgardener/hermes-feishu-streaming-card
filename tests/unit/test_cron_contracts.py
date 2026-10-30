import ast

import pytest

from hermes_feishu_card.install.ast_contracts import _body_location
from hermes_feishu_card.install.cron_contracts import find_cron_deliver_body_location, find_cron_media_delivery_location
from hermes_feishu_card.install import patcher


def inputs(source):
    return ast.parse(source), source.splitlines(keepends=True)


@pytest.mark.parametrize('body,expected', [
    ('    pass\n', (1, '    ')),
    ('    "doc"\n    pass\n', (2, '    ')),
    ('    """multi\n    doc"""\n', (3, '    ')),
])
def test_body_location_preserves_docstring_and_indentation(body, expected):
    tree, lines = inputs('def _deliver_result():\n'+body)
    before = ast.dump(tree, include_attributes=True), list(lines)
    assert find_cron_deliver_body_location(tree, lines) == expected
    assert (ast.dump(tree, include_attributes=True), lines) == before


@pytest.mark.parametrize('source', ['def _deliver_result(): pass\n', 'def _deliver_result(): "doc"\n', 'async def _deliver_result():\n    pass\n'])
def test_unsafe_one_line_and_async_layouts_remain_unselected(source):
    assert find_cron_deliver_body_location(*inputs(source)) is None


def test_top_level_precedes_class_regardless_of_source_order():
    source = 'class First:\n    def _deliver_result(self):\n        pass\ndef _deliver_result():\n    pass\n'
    assert find_cron_deliver_body_location(*inputs(source)) == (4, '    ')
    assert find_cron_deliver_body_location(*inputs(source.split('def _deliver_result():')[0])) == (2, '        ')


def test_filter_priority_and_last_same_kind_assignment_are_preserved():
    source = ('def _deliver_result():\n'
              '    media_files = adapter.filter_media_delivery_paths(media_files)\n'
              '    media_files, cleaned_delivery_content = adapter.extract_media(content)\n'
              '    media_files, cleaned_delivery_content = adapter.extract_media(other)\n')
    assert find_cron_media_delivery_location(*inputs(source)) == (2, '    ')
    assert find_cron_media_delivery_location(*inputs(source.replace('    media_files = adapter.filter_media_delivery_paths(media_files)\n', ''))) == (3, '    ')


def test_nested_or_annotated_assignments_are_not_media_anchors():
    source = ('def _deliver_result():\n'
              '    if condition:\n        media_files, cleaned_delivery_content = adapter.extract_media(content)\n'
              '    media_files: list = adapter.filter_media_delivery_paths(media_files)\n')
    assert find_cron_media_delivery_location(*inputs(source)) is None
    node = ast.FunctionDef(name='empty', body=[])
    assert _body_location(node, []) is None


@pytest.mark.parametrize('newline', ['\n', '\r\n'])
def test_cron_apply_remove_preserves_exact_original_newlines(newline):
    source = ('def _deliver_result(job, content):\n'
              '    """Keep this documentation."""\n'
              '    media_files, cleaned_delivery_content = adapter.extract_media(content)\n'
              '    media_files = adapter.filter_media_delivery_paths(media_files)\n'
              '    return cleaned_delivery_content\n').replace('\n', newline)
    patched = patcher.apply_cron_patch(source)
    assert patcher.CRON_PATCH_BEGIN in patched
    assert patcher.apply_cron_patch(patched) == patched
    assert patcher.remove_cron_patch(patched) == source
