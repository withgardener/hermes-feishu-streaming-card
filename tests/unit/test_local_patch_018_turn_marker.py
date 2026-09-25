"""LOCAL PATCH (PATCH-018): Hermes v0.21.5 turn-marker release inside send_final_ledgered.

Regression for upstream issue #352: the split ledger bracket must accept exactly
``if obligation_id is not None: await self._release_turn_marker(event)`` directly after the
record call, and keep rejecting any other statement or a changed ordering.
"""
import ast

import pytest

from hermes_feishu_card.install.patcher import _validate_split_ledger_bracket

HEAD = '''
async def send_final_ledgered(self, event, session_key, text_content, metadata, *, reply_to, is_ephemeral_response=False):
    """doc"""
    delivery_adapter = self._final_delivery_adapter(event.source)
    logger.info("x")
    obligation_id = await self._record_delivery_obligation(event, session_key, text_content, delivery_adapter, is_ephemeral_response)
'''
RELEASE = '''    if obligation_id is not None:
        await self._release_turn_marker(event)
'''
TAIL = '''    result = await delivery_adapter._send_with_retry(chat_id=event.source.chat_id, content=text_content, reply_to=reply_to, metadata=metadata)
    if obligation_id is not None:
        await self._finalize_delivery_obligation(obligation_id, result, event, delivery_adapter)
    return result, delivery_adapter
'''


def _fn(src):
    return ast.parse(src).body[0]


def test_accepts_v0215_turn_marker_release():
    _validate_split_ledger_bracket(_fn(HEAD + RELEASE + TAIL))


def test_still_accepts_pre_v0215_bracket():
    _validate_split_ledger_bracket(_fn(HEAD + TAIL))


@pytest.mark.parametrize("extra", [
    RELEASE + RELEASE,  # only once
    "    await self._release_turn_marker(event)\n",  # unguarded variant is not the contract
    "    await self._something_else(event)\n",
])
def test_rejects_other_statements(extra):
    with pytest.raises(ValueError):
        _validate_split_ledger_bracket(_fn(HEAD + extra + TAIL))


def test_rejects_release_after_send():
    lines = TAIL.splitlines(keepends=True)
    src = HEAD + lines[0] + RELEASE + "".join(lines[1:])
    with pytest.raises(ValueError):
        _validate_split_ledger_bracket(_fn(src))
