"""Navigation is optional platform evidence, never inferred message identity."""
from copy import deepcopy
from dataclasses import FrozenInstanceError

import pytest

from hermes_feishu_card.card_limits import inspect_card_limits, serialize_card_json
from hermes_feishu_card.delivery import CardDeliveryResult
from hermes_feishu_card.feishu_client import FeishuSendResult
from hermes_feishu_card.message_navigation import (
    MessageNavigation, navigation_from_response, with_continuation_navigation,
)

CHAT = "oc_navigation_fixture"
MESSAGE = "om_navigation_fixture"
THREAD = "omt_navigation_fixture"
API = "https://open.feishu.cn/open-apis"
LINK = f"https://applink.feishu.cn/client/chat/open?openChatId={CHAT}&position=12"


def response(**kwargs):
    return {"message_id": MESSAGE, "chat_id": CHAT, "message_app_link": LINK, **kwargs}


def parsed(data=None, **kwargs):
    return navigation_from_response(response() if data is None else data,
                                    api_base_url=API, chat_id=CHAT, **kwargs)


@pytest.mark.parametrize("api,host", [(API, "applink.feishu.cn"),
    ("https://open.larksuite.com/open-apis", "applink.larksuite.com")])
def test_same_response_brand_and_identity_are_retained(api, host):
    link = LINK.replace("applink.feishu.cn", host)
    data = response(message_app_link=link, message_position="12")
    before = deepcopy(data)
    nav = navigation_from_response(data, api_base_url=api, chat_id=CHAT)
    assert nav == MessageNavigation(MESSAGE, CHAT, link)
    assert data == before
    assert nav.url == link
    with pytest.raises(FrozenInstanceError):
        nav.url = "must-not-change"


@pytest.mark.parametrize("patch", [
    {"message_app_link": None}, {"message_app_link": ""}, {"message_app_link": 1},
    {"message_app_link": True}, {"message_app_link": []}, {"message_app_link": {}},
    {"chat_id": "oc_wrong"}, {"chat_id": None}, {"chat_id": []},
    {"message_id": "card_wrong"}, {"message_id": None}, {"message_id": 12},
    {"message_position": True}, {"message_position": 12.0}, {"message_position": float("nan")},
    {"message_position": "13"}, {"message_position": []}, {"message_position": {}},
], ids=["no-link", "empty-link", "int-link", "bool-link", "list-link", "dict-link",
    "wrong-chat", "null-chat", "list-chat", "card-id", "null-id", "int-id",
    "bool-position", "float-position", "nan-position", "different-position", "list-position", "dict-position"])
def test_unusable_optional_json_metadata_omits_navigation(patch):
    assert parsed(response(**patch)) is None


def test_same_receipt_position_can_supply_missing_optional_link():
    data = response(message_position="12")
    data.pop("message_app_link")
    assert parsed(data) == MessageNavigation(MESSAGE, CHAT, LINK)


@pytest.mark.parametrize("link", [
    LINK.replace("https:", "http:"), LINK.replace("applink.feishu.cn", "applink.larksuite.com"),
    LINK.replace("applink.feishu.cn", "applink.feishu.cn.evil.test"),
    LINK.replace("applink.feishu.cn", "evil@applink.feishu.cn"),
    LINK.replace("applink.feishu.cn", "applink.feishu.cn:444"),
    LINK.replace("applink.feishu.cn", "applink.feishu.cn:bad"),
    LINK.replace("applink.feishu.cn", "[invalid"), LINK + "#fragment",
    LINK.replace("/client/chat/open", "/client/message/link/open"),
    LINK + "&position=12", LINK + "&unexpected=value",
    LINK.replace(f"openChatId={CHAT}", "openChatId=oc_wrong"),
    LINK.replace("position=12", "position="), LINK.replace("position=12", "position=-1"),
    LINK.replace("position=12", "position=12.5"), LINK.replace("position=12", "position=%00"),
    LINK.replace("position=12", "position=" + "1" * 21), LINK + "\n",
    LINK + "\x7f", LINK + " ", LINK + "x" * 2048,
    LINK + "&" + "&".join(f"extra{i}=x" for i in range(17)),
], ids=["http", "cross-brand", "suffix-host", "userinfo", "wrong-port", "bad-port", "invalid-host",
    "fragment", "unsupported-path", "duplicate-position", "unexpected-key", "wrong-query-chat",
    "empty-position", "negative", "fraction", "encoded-control", "long-position", "newline",
    "delete-control", "space", "long-url", "query-budget"])
def test_unsafe_or_ambiguous_link_is_omitted(link):
    assert parsed(response(message_app_link=link)) is None


@pytest.mark.parametrize("api", ["https://custom-api.test/open-apis", "https://open.feishu.cn.evil.test/open-apis"])
def test_unknown_brand_does_not_default_to_feishu(api):
    assert navigation_from_response(response(), api_base_url=api, chat_id=CHAT) is None


@pytest.mark.parametrize("intent", [{"thread_id": THREAD}, {"reply_in_thread": True}])
def test_thread_intention_never_accepts_chat_only_link(intent):
    assert parsed(**intent) is None


@pytest.mark.parametrize("aliases", ["legacy", "snake", "both"])
def test_thread_link_requires_same_response_thread_and_position(aliases):
    query = []
    if aliases in {"legacy", "both"}:
        query += [f"openthreadid={THREAD}", f"openchatid={CHAT}"]
    if aliases in {"snake", "both"}:
        query += [f"open_thread_id={THREAD}", f"open_chat_id={CHAT}"]
    link = "https://applink.feishu.cn/client/thread/open?" + "&".join(query + ["thread_position=12"])
    data = response(message_app_link=link, thread_id=THREAD, thread_message_position="12")
    assert parsed(data, thread_id=THREAD, reply_in_thread=True) == MessageNavigation(MESSAGE, CHAT, link)
    assert parsed({**data, "thread_id": "omt_wrong"}, thread_id=THREAD) is None
    assert parsed({**data, "thread_message_position": "13"}, thread_id=THREAD) is None
    assert parsed({**data, "message_app_link": link + "&openthreadid=omt_wrong"}, thread_id=THREAD) is None
    assert parsed({**data, "thread_id": None}, reply_in_thread=True) is None


def card(text="KEEP_BODY"):
    return {"schema": "2.0", "body": {"elements": [{"tag": "markdown", "content": text}]}}


def test_button_is_schema2_url_only_and_preserves_input():
    original = card()
    before = deepcopy(original)
    nav = parsed()
    result = with_continuation_navigation(original, nav, message_id=MESSAGE, chat_id=CHAT)
    assert original == before
    assert result is not original
    button = result["body"]["elements"][-1]
    assert button == {"tag": "button", "element_id": "continuation_link", "type": "default",
        "text": {"tag": "plain_text", "content": "查看续答"},
        "behaviors": [{"type": "open_url", "default_url": LINK}]}
    assert result["body"]["elements"][0] == original["body"]["elements"][0]
    assert with_continuation_navigation(result, nav, message_id=MESSAGE, chat_id=CHAT) is result


@pytest.mark.parametrize("kind", ["missing", "wrong-message", "wrong-chat", "legacy", "missing-body"])
def test_unproven_identity_and_legacy_cards_are_unchanged(kind):
    original = card()
    nav = parsed()
    mid, chat = MESSAGE, CHAT
    if kind == "missing": nav = None
    elif kind == "wrong-message": mid = "om_wrong"
    elif kind == "wrong-chat": chat = "oc_wrong"
    elif kind == "legacy": original.pop("schema")
    else: original.pop("body")
    assert with_continuation_navigation(original, nav, message_id=mid, chat_id=chat) is original


@pytest.mark.parametrize("budget", ["bytes", "elements"])
def test_optional_button_overflow_preserves_entire_original_content(budget):
    if budget == "bytes":
        original = card("")
        capacity = 28000 - len(serialize_card_json(original).encode())
        original = card("X" * capacity)
    else:
        original = card()
        original["body"]["elements"] *= 199
    before = deepcopy(original)
    assert inspect_card_limits(original).safe
    result = with_continuation_navigation(original, parsed(), message_id=MESSAGE, chat_id=CHAT)
    assert result is original and result == before
    assert inspect_card_limits(result).safe


def test_optional_navigation_is_excluded_from_all_result_reprs():
    nav = parsed()
    for value in (nav, FeishuSendResult(MESSAGE, navigation=nav),
                  CardDeliveryResult(MESSAGE, "delivered", navigation=nav)):
        assert LINK not in repr(value) and CHAT not in repr(value)
    assert FeishuSendResult(MESSAGE).navigation is None
    assert CardDeliveryResult(MESSAGE, "delivered").navigation is None


@pytest.mark.parametrize("missing", ["absent", None, ""])
@pytest.mark.parametrize("brand", ["feishu", "lark"])
@pytest.mark.parametrize("position", [12, "12"])
def test_verified_position_fallback_is_branded_and_does_not_mutate(missing, brand, position):
    host = "applink.feishu.cn" if brand == "feishu" else "applink.larksuite.com"
    api = API if brand == "feishu" else "https://open.larksuite.com/open-apis"
    data = {"message_id": MESSAGE, "chat_id": CHAT, "message_position": position}
    if missing != "absent":
        data["message_app_link"] = missing
    before = deepcopy(data)
    nav = navigation_from_response(data, api_base_url=api, chat_id=CHAT)
    assert nav == MessageNavigation(MESSAGE, CHAT, LINK.replace("applink.feishu.cn", host))
    assert data == before
    original = card()
    output = with_continuation_navigation(original, nav, message_id=MESSAGE, chat_id=CHAT)
    assert output["body"]["elements"][0] == original["body"]["elements"][0]
    assert output["body"]["elements"][-1]["behaviors"] == [
        {"type": "open_url", "default_url": nav.url}]


@pytest.mark.parametrize("position", [None, True, False, -1, 12.0, float("nan"),
    "", "-1", "+12", " 12", "12\n", "１２", "1" * 21, [], {}])
def test_missing_link_does_not_relax_position_validation(position):
    assert parsed(response(message_app_link=None, message_position=position)) is None


@pytest.mark.parametrize("link", [False, 0, [], {}, " ", "https://[bad", LINK + "&position=12"])
def test_present_invalid_link_cannot_be_replaced_by_valid_position(link):
    assert parsed(response(message_app_link=link, message_position="12")) is None


@pytest.mark.parametrize("patch", [{"chat_id": "oc_wrong"}, {"message_id": "card_entity"},
    {"message_id": None}, {"chat_id": None}])
def test_fallback_still_requires_same_im_message_and_chat(patch):
    assert parsed(response(message_app_link=None, message_position="12", **patch)) is None


@pytest.mark.parametrize("intent", [{"thread_id": THREAD}, {"reply_in_thread": True}, {}])
def test_thread_fallback_requires_thread_position_and_never_uses_chat_position(intent):
    data = response(message_app_link=None, thread_id=THREAD,
                    thread_message_position="23", message_position="12")
    nav = parsed(data, **intent)
    from urllib.parse import parse_qs, urlsplit
    assert nav is not None
    link = urlsplit(nav.url)
    assert link.path == "/client/thread/open"
    assert parse_qs(link.query) == {"openthreadid": [THREAD], "open_thread_id": [THREAD],
        "openchatid": [CHAT], "open_chat_id": [CHAT], "thread_position": ["23"]}
    assert parsed({**data, "thread_message_position": None}, **intent) is None
    assert parsed({**data, "thread_id": "omt_wrong"}, thread_id=THREAD) is None
    assert parsed({**data, "thread_id": None}, thread_id=THREAD) is None
    assert parsed({**data, "thread_id": None}, reply_in_thread=True) is None


@pytest.mark.parametrize("api", ["https://custom.test/open-apis", "https://open.feishu.cn.evil.test/open-apis"])
def test_position_fallback_does_not_guess_unknown_brand(api):
    data = response(message_app_link=None, message_position="12")
    assert navigation_from_response(data, api_base_url=api, chat_id=CHAT) is None
