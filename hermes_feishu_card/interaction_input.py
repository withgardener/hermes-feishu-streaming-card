"""Feishu callback input decoding, separate from claims and task execution.

Parsing a choice grants no authority. The coordinator must still verify the
current request, operator and lifetime under the existing interaction lock.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any, Collection, Mapping

from .event_rules import safe_profile_id


@dataclass(frozen=True, repr=False)
class InteractionChoice:
    value: str
    label: str


class InteractionInputError(ValueError):
    def __init__(self, code: str, *, warning: str = "") -> None:
        super().__init__(code)
        self.code = code
        self.warning = warning

    def payload(self) -> dict[str, Any]:
        result: dict[str, Any] = {"ok": False, "error": self.code}
        if self.warning:
            result["toast"] = {"type": "warning", "content": self.warning}
        return result


def parse_choice(
    value: Mapping[str, Any],
    form_value: Mapping[str, Any],
    *,
    mode: str,
    allowed_values: Collection[str],
    allow_custom_input: bool,
) -> InteractionChoice:
    """Preserve the original single/multi/custom-answer wire representation."""
    if mode == "confirm":
        typed = str(form_value.get("hfc_other") or "").strip()
        raw = form_value.get("hfc_multi")
        if raw is None:
            raw = []
        selected = raw if isinstance(raw, list) else ([raw] if raw != "" else [])
        selected = [str(item).strip() for item in selected if str(item).strip()]
        if any(item not in allowed_values for item in selected):
            raise InteractionInputError("invalid choice")
        if typed and not allow_custom_input:
            raise InteractionInputError("custom input not allowed")
        if typed:
            if selected:
                combined = selected + [f"[自定义] {typed}"]
                return InteractionChoice(json.dumps(combined, ensure_ascii=False), ", ".join(combined))
            return InteractionChoice(typed, typed)
        return InteractionChoice(
            json.dumps(selected, ensure_ascii=False),
            ", ".join(selected) if selected else "(未选择)",
        )
    if mode == "other":
        if not allow_custom_input:
            raise InteractionInputError("custom input not allowed")
        typed = str(form_value.get("hfc_other") or "").strip()
        if not typed:
            raise InteractionInputError("empty other answer", warning="请输入内容后再提交")
        return InteractionChoice(typed, typed)
    choice = str(value.get("choice") or "").strip()
    label = str(value.get("choice_label") or choice).strip()
    if not choice:
        raise InteractionInputError("invalid action")
    if not allow_custom_input and choice not in allowed_values:
        raise InteractionInputError("invalid choice")
    return InteractionChoice(choice, label)


def parse_form_action_name(payload: dict[str, Any]) -> tuple[str, str] | None:
    """Identify a clarify form submit from the button name.

    Form-submit buttons cannot carry behaviors callbacks, so render.py
    encodes the callback token into the button name:
      hfc_confirm_<callback_token>  (multi-select confirm / combined submit)
      hfc_other_<callback_token>    (free-text Other submit)
    Returns (mode, callback_token) or None when the action isn't a clarify
    form submit.
    """
    event = payload.get("event") if isinstance(payload, dict) else None
    action = event.get("action") if isinstance(event, dict) else None
    name = str(action.get("name") or "").strip() if isinstance(action, dict) else ""
    if name.startswith("hfc_confirm_"):
        token = name[len("hfc_confirm_"):].strip()
        return ("confirm", token) if token else None
    if name.startswith("hfc_other_"):
        token = name[len("hfc_other_"):].strip()
        return ("other", token) if token else None
    return None


def extract_action_value(payload: dict[str, Any]) -> dict[str, Any]:
    event = payload.get("event") if isinstance(payload, dict) else None
    action = event.get("action") if isinstance(event, dict) else None
    value = action.get("value") if isinstance(action, dict) else None
    if isinstance(value, dict):
        return value
    action = payload.get("action") if isinstance(payload, dict) else None
    value = action.get("value") if isinstance(action, dict) else None
    return value if isinstance(value, dict) else {}


def extract_form_value(payload: dict[str, Any]) -> dict[str, Any]:
    """Extract the form container submission payload.

    When a user submits a card form (form_action_type=submit), Feishu returns
    ``action.form_value`` — a mapping of every form component's ``name`` to
    its submitted value (string for input, list for multi_select_static)."""
    event = payload.get("event") if isinstance(payload, dict) else None
    action = event.get("action") if isinstance(event, dict) else None
    form_value = action.get("form_value") if isinstance(action, dict) else None
    if isinstance(form_value, dict):
        return form_value
    action = payload.get("action") if isinstance(payload, dict) else None
    form_value = action.get("form_value") if isinstance(action, dict) else None
    return form_value if isinstance(form_value, dict) else {}


def extract_callback_chat_id(payload: dict[str, Any]) -> str:
    event = payload.get("event") if isinstance(payload, dict) else None
    context = event.get("context") if isinstance(event, dict) else None
    if isinstance(context, dict):
        return str(context.get("open_chat_id") or context.get("chat_id") or "").strip()
    return ""


def extract_callback_profile_id(payload: dict[str, Any]) -> str:
    event = payload.get("event") if isinstance(payload, dict) else None
    context = event.get("context") if isinstance(event, dict) else None
    if not isinstance(context, dict):
        return ""
    return safe_profile_id(context.get("profile_id")) if context.get("profile_id") else ""


def extract_operator_open_id(payload: dict[str, Any]) -> str:
    event = payload.get("event") if isinstance(payload, dict) else None
    operator = event.get("operator") if isinstance(event, dict) else None
    if not isinstance(operator, dict):
        return ""
    return str(operator.get("open_id") or "").strip()


def extract_operator_name(payload: dict[str, Any]) -> str:
    event = payload.get("event") if isinstance(payload, dict) else None
    operator = event.get("operator") if isinstance(event, dict) else None
    if not isinstance(operator, dict):
        return ""
    return str(
        operator.get("name")
        or operator.get("user_name")
        or operator.get("display_name")
        or ""
    ).strip()
