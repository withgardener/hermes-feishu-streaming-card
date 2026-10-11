"""DM card callbacks must not be run through the group-only gate (#374)."""
import asyncio
import time
from types import SimpleNamespace as NS

import pytest
from hermes_feishu_card import hook_runtime as runtime


def action(operator="ou_owner", chat="oc_dm"):
    return NS(event=NS(operator=NS(open_id=operator), context=NS(open_chat_id=chat)))


def item(chat_type="dm"):
    return dict(chat_id="oc_dm", chat_type=chat_type, operator_open_id="ou_owner",
                session_key="session", message_id="om_card", expires_at=time.time()+300,
                allowed_session_ids={"saved"}, catalog=[])


@pytest.mark.parametrize("kind", ["slash", "model", "resume", "center"])
def test_dm_owner_can_use_pending_card_when_group_policy_denies(kind):
    pending = item()
    calls = []
    adapter = NS(_loop=object(), _allow_group_message=lambda *a, **k: calls.append(a) or False)
    if kind == "slash":
        adapter._hfc_slash_confirm_state = {"id": pending}
        result = runtime._hfc_prepare_native_slash_action(adapter, action(),
                    {"hfc_confirm_id":"id", "hfc_choice":"once"}, claim=True)
        assert "id" not in adapter._hfc_slash_confirm_state
        assert runtime._hfc_prepare_native_slash_action(adapter, action(),
                    {"hfc_confirm_id":"id", "hfc_choice":"once"}, claim=True) is None
    elif kind == "model":
        adapter._hfc_model_picker_state = {"id": pending}
        result = runtime._hfc_prepare_native_model_action(adapter, action(), {"hfc_model_picker_id":"id"})
    elif kind == "resume":
        adapter._hfc_resume_picker_state = {"id": pending}
        result = runtime._hfc_prepare_native_resume_action(adapter, action(),
                    {"hfc_resume_picker_id":"id", "hfc_choice":"saved"})
    else:
        adapter._hfc_command_center_state = {"id": pending}
        result = runtime._hfc_prepare_command_center_action(adapter, action(),
                    {"hfc_command_center_id":"id", "hfc_command_center_nav":"home"})
    assert result is not None
    assert calls == []


@pytest.mark.parametrize("actor,chat", [("ou_other","oc_dm"),("ou_owner","oc_other"),("","oc_dm"),("ou_owner","")])
def test_dm_card_rejects_other_actor_or_missing_or_wrong_chat(actor, chat):
    adapter = NS(_loop=object(), _allow_group_message=lambda *a, **k: True,
                 _hfc_slash_confirm_state={"id":item()})
    assert runtime._hfc_prepare_native_slash_action(adapter, action(actor,chat),
        {"hfc_confirm_id":"id","hfc_choice":"once"},claim=True) is None
    assert "id" in adapter._hfc_slash_confirm_state


@pytest.mark.parametrize("chat_type", ["group", "", "unknown"])
def test_group_or_unknown_keeps_group_policy(chat_type):
    adapter = NS(_loop=object(), _allow_group_message=lambda *a, **k: False,
                 _hfc_slash_confirm_state={"id":item(chat_type)})
    assert runtime._hfc_prepare_native_slash_action(adapter, action(),
        {"hfc_confirm_id":"id","hfc_choice":"once"},claim=True) is None
    assert "id" in adapter._hfc_slash_confirm_state


@pytest.mark.parametrize("raw_type,admitted,expected", [("p2p", True, True), ("p2p",False,False), (None,True,False),("group",True,False)])
def test_token_actions_use_proven_platform_dm_metadata_and_native_admission(raw_type, admitted, expected):
    calls=[]
    def admit(sender, message):
        calls.append((sender.sender_id.open_id,message.chat_type))
        return None if admitted else "dm_policy_rejected"
    adapter=NS(_chat_info_cache={"oc_dm":{"type":"dm","raw_type":raw_type}},
               _admit=admit, _allow_group_message=lambda *a,**k:False)
    assert runtime._hfc_card_operator_allowed(adapter, action(), "oc_dm") is expected
    assert bool(calls) is (raw_type == "p2p")


def test_pending_dm_missing_owner_cannot_use_metadata_fallback():
    pending=item();pending.pop("operator_open_id")
    adapter=NS(_chat_info_cache={"oc_dm":{"raw_type":"p2p"}}, _admit=lambda *a:None)
    assert runtime._hfc_card_operator_allowed(adapter, action(), "oc_dm", pending=pending) is False


@pytest.mark.parametrize("kind", ["slash", "model"])
def test_real_send_captures_admitted_command_for_later_callback(monkeypatch,kind):
    async def allowed(*a,**k):return True
    async def send(**k):return NS(success=True,message_id="om_card")
    monkeypatch.setattr(runtime,"_hfc_direct_card_allowed_async",allowed)
    adapter=NS(_client=object(),_loop=object(),_feishu_send_with_retry=send,
               _allow_group_message=lambda *a,**k:False)
    token=runtime._HFC_FEISHU_COMMAND_RESULT_CONTEXT.set({**item(),"expires_at":time.monotonic()+60})
    try:
        if kind=="slash":
            asyncio.run(runtime._hfc_send_native_slash_confirm(adapter,"oc_dm","Confirm","new","session","id"))
            assert adapter._hfc_slash_confirm_state['id']['operator_open_id']=='ou_owner'
            assert runtime._hfc_prepare_native_slash_action(adapter,action(),
                {"hfc_confirm_id":"id","hfc_choice":"cancel"},claim=True)
        else:
            asyncio.run(runtime._hfc_send_native_model_picker(adapter,"oc_dm",
                [{"name":"test", "slug":"test", "models":["test-model"]}],session_key="session"))
            state=adapter._hfc_model_picker_state
            assert len(state)==1
            key=next(iter(state))
            assert state[key]['operator_open_id']=='ou_owner'
            assert runtime._hfc_prepare_native_model_action(adapter,action(),{"hfc_model_picker_id":key})
    finally:
        runtime._HFC_FEISHU_COMMAND_RESULT_CONTEXT.reset(token)


@pytest.mark.parametrize("change", [{"chat_id":"oc_other"},{"expires_at":0},{"expires_at":"bad"}])
def test_admitted_context_cannot_cross_chat_or_expiry(change):
    token=runtime._HFC_FEISHU_COMMAND_RESULT_CONTEXT.set({**item(),"expires_at":time.monotonic()+60,**change})
    try:assert runtime._hfc_pending_command_identity("oc_dm")=={}
    finally:runtime._HFC_FEISHU_COMMAND_RESULT_CONTEXT.reset(token)
