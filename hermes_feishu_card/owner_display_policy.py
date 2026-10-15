"""Replacement policy for the current display owner; no delivery authority.

The coordinator checks owner identity/generation first and retains rendering,
I/O and mutations. Failed-receipt rendering must precede card-source selection.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Literal


OwnerCardSource = Literal["current_render", "separate_receipt", "callback_owner", "text_receipt_owner"]


@dataclass(frozen=True, repr=False)
class OwnerRefreshState:
    event_kind: str
    is_terminal: bool
    owner_message_id: str
    interaction_present: bool
    interaction_status: str | None
    interaction_message_id: str
    has_receipt_fingerprint: bool
    has_legacy_owner_receipt: bool

    @property
    def freezes_inputs(self) -> bool:
        return (
            self.interaction_present
            and self.interaction_status in {"pending", "paused"}
            and not self.is_terminal
            and not str(self.event_kind or "").startswith("interaction.")
        )

    @property
    def refresh_failed_receipt_first(self) -> bool:
        return (
            self.event_kind == "interaction.failed"
            and self.interaction_present
            and self.has_receipt_fingerprint
        )

    def card_source(self, mode: Callable[[], str]) -> OwnerCardSource:
        """Resolve mode lazily, at the same branches as the original policy.

        A separate receipt means that update was handled elsewhere, not that
        this decision performed or proved a new delivery.
        """
        if not str(self.event_kind).startswith("interaction.") or not self.interaction_present:
            return "current_render"
        if (
            self.interaction_message_id
            and self.interaction_message_id != self.owner_message_id
            and (self.has_legacy_owner_receipt or mode() == "text")
        ):
            return "separate_receipt"
        if self.interaction_message_id == self.owner_message_id and mode() == "callback":
            return "callback_owner"
        if (
            self.interaction_status not in {"pending", "paused"}
            and self.interaction_message_id == self.owner_message_id
            and mode() == "text"
        ):
            return "text_receipt_owner"
        return "current_render"


def collapsed_transfer_elements(elements: list[dict[str, Any]]) -> list[dict[str, Any]] | None:
    """Collapse a retired display copy; retain content without nested panels.

    Called only after a continuation send was confirmed. No execution state or
    source session is changed; budget failure leaves the original card intact.
    """
    children: list[dict[str, Any]] = []
    def append(items: list[dict[str, Any]]) -> None:
        for item in items:
            if item.get("tag") == "collapsible_panel":
                append(item.get("elements", []))
            elif item.get("tag") in {"markdown", "hr"}:
                children.append(item)
            else:
                raise ValueError("unsupported transfer panel child")
    try:
        append(elements)
    except (ValueError, TypeError, AttributeError):
        return None
    if not children:
        return []
    return [{
        "tag": "collapsible_panel",
        "element_id": "previous_content",
        "expanded": False,
        "header": {"title": {"tag": "plain_text", "content": "此前内容（点按展开/收起）"}},
        "border": {"color": "grey", "corner_radius": "8px"},
        "padding": "8px 8px 8px 8px",
        "elements": children,
    }]
