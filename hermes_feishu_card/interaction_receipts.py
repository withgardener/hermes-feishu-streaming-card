"""Bounded, token-free interaction display checkpoints; never live consent.

The projection copies interaction state before masking or expiring its display.
It does not mutate the owner, write a checkpoint, send a card or call a resolver.
"""
from __future__ import annotations

import copy
from typing import Any

from .card_limits import inspect_card_limits
from .legacy_owner import static_legacy_receipt, valid_auxiliary_receipt
from .render import mask_approval_scope, render_legacy_interaction_callback_card
from .session import CardSession


def build_auxiliary_receipt(
    session: CardSession,
    owner_id: str | None,
    *,
    title: str,
    profile_id: str,
    presentation: str,
    mentions_enabled: bool,
    dialect: str,
) -> dict[str, Any] | None:
    interaction = session.active_interaction
    if (interaction is None or not interaction.feishu_message_id
            or interaction.feishu_message_id == owner_id):
        return None
    snapshot = copy.copy(session)
    snapshot.active_interaction = projected = copy.deepcopy(interaction)
    if interaction.status in {"pending", "paused"}:
        projected.status = "failed"
        projected.error = "连接已重建，原交互已失效，请重新发起请求。"
    for name in ("prompt", "choice", "choice_label", "user_name", "error"):
        setattr(projected, name,
                mask_approval_scope(getattr(projected, name)))
    for option in projected.options:
        option.label = mask_approval_scope(option.label)
    # The renderer masks scope secrets; the static receipt then removes every
    # callback/control field. No waiter identity or runtime admission is saved.
    card = static_legacy_receipt(
        render_legacy_interaction_callback_card(
            snapshot, title=title, interaction_profile_id=profile_id,
            presentation=presentation, mentions_enabled=mentions_enabled,
        ))
    if not inspect_card_limits(card).safe:
        raise ValueError("auxiliary display receipt exceeds bounds")
    receipt = {"message_id": interaction.feishu_message_id, "card": card,
               "template": "green" if projected.status == "completed" else "red",
               "dialect": dialect}
    if not valid_auxiliary_receipt(receipt):
        # Never trim authorization scope to make its checkpoint fit. Delivery
        # remains accepted while the existing diagnostics report unavailable.
        raise ValueError("auxiliary display receipt exceeds bounds")
    return receipt

