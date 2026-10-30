"""Optional navigation from verified IM link/position metadata, never guessed IDs."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import re
from typing import Any, Mapping
from urllib.parse import parse_qs, urlencode, urlsplit

from .card_limits import inspect_card_limits

_BRANDS = {"open.feishu.cn": "applink.feishu.cn", "open.larksuite.com": "applink.larksuite.com"}
_POSITION = re.compile(r"[0-9]{1,20}\Z")


@dataclass(frozen=True, repr=False)
class MessageNavigation:
    message_id: str
    chat_id: str
    url: str


def _matches(query: dict[str, list[str]], names: tuple[str, ...], expected: str) -> bool:
    present = [query[name] for name in names if name in query]
    return bool(expected and present) and all(value == [expected] for value in present)


def _link_from_position(
    data: Mapping[str, Any], host: str | None, *,
    thread_id: str | None, reply_in_thread: bool,
) -> str | None:
    """Use same-receipt position metadata; never derive positions from IDs."""
    if host is None:
        return None
    response_thread = data.get("thread_id")
    if type(response_thread) not in (str, type(None)):
        return None
    if thread_id or reply_in_thread or response_thread:
        if (not response_thread or (thread_id and thread_id != response_thread)):
            return None
        position = data.get("thread_message_position")
        path = "/client/thread/open"
        query = {
            "openthreadid": response_thread, "openchatid": data["chat_id"],
            "open_thread_id": response_thread, "open_chat_id": data["chat_id"],
        }
        position_key = "thread_position"
    else:
        position = data.get("message_position")
        path = "/client/chat/open"
        query = {"openChatId": data["chat_id"]}
        position_key = "position"
    if type(position) not in (str, int) or _POSITION.fullmatch(str(position)) is None:
        return None
    query[position_key] = str(position)
    return "https://" + host + path + "?" + urlencode(query)


def navigation_from_response(
    data: Mapping[str, Any], *, api_base_url: str, chat_id: str,
    thread_id: str | None = None, reply_in_thread: bool = False,
) -> MessageNavigation | None:
    """Accept an exact link or verified position metadata from this receipt.

    Missing metadata or unfamiliar links omit the optional control. No history
    lookup, guessed positions or navigation to a card-container ID is allowed.
    """
    message_id = data.get("message_id")
    url = data.get("message_app_link")
    if (not isinstance(message_id, str) or not message_id.startswith("om_")
            or not chat_id or data.get("chat_id") != chat_id):
        return None
    try:
        expected_host = _BRANDS.get(urlsplit(api_base_url).hostname or "")
        if url is None or url == "":
            url = _link_from_position(
                data, expected_host, thread_id=thread_id, reply_in_thread=reply_in_thread,
            )
        if (not isinstance(url, str) or not url or len(url) > 2048
                or any(char.isspace() or ord(char) < 32 or ord(char) == 127 for char in url)):
            return None
        link = urlsplit(url)
        if (not expected_host or link.scheme != "https" or link.hostname != expected_host
                or link.username or link.password or link.port not in {None, 443} or link.fragment):
            return None
        query = parse_qs(link.query, keep_blank_values=True, strict_parsing=True, max_num_fields=16)
    except (TypeError, ValueError):
        return None
    response_thread = data.get("thread_id")
    if link.path == "/client/chat/open":
        if thread_id or reply_in_thread or response_thread:
            return None
        if set(query) - {"openChatId", "position"} or not _matches(query, ("openChatId",), chat_id):
            return None
        positions = query.get("position", [])
        response_position = data.get("message_position")
    elif link.path == "/client/thread/open":
        if not isinstance(response_thread, str) or not response_thread or (thread_id and thread_id != response_thread):
            return None
        if set(query) - {"openthreadid", "openchatid", "open_thread_id", "open_chat_id", "thread_position"}:
            return None
        if (not _matches(query, ("openchatid", "open_chat_id"), chat_id)
                or not _matches(query, ("openthreadid", "open_thread_id"), response_thread)):
            return None
        positions = query.get("thread_position", [])
        response_position = data.get("thread_message_position")
    else:
        return None
    if len(positions) != 1 or _POSITION.fullmatch(positions[0]) is None:
        return None
    # If supplied separately, the receipt's position must agree with its link.
    if response_position is not None and (
        type(response_position) not in {str, int}
        or str(response_position) != positions[0]
    ):
        return None
    return MessageNavigation(message_id, chat_id, url)


def with_continuation_navigation(
    card: dict[str, Any], navigation: MessageNavigation | None, *,
    message_id: str, chat_id: str,
) -> dict[str, Any]:
    """Add one optional URL control without trimming content or mutating input."""
    if (navigation is None or navigation.message_id != message_id
            or navigation.chat_id != chat_id or card.get("schema") != "2.0"):
        return card
    body = card.get("body")
    if not isinstance(body, dict) or not isinstance(body.get("elements"), list):
        return card
    if any(isinstance(element, dict) and element.get("element_id") == "continuation_link"
           for element in body["elements"]):
        return card
    result = deepcopy(card)
    result["body"]["elements"].append({
        "tag": "button", "element_id": "continuation_link", "type": "default",
        "text": {"tag": "plain_text", "content": "查看续答"},
        "behaviors": [{"type": "open_url", "default_url": navigation.url}],
    })
    return result if inspect_card_limits(result).safe else card
