from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
import json
from typing import Iterable


class IntegrationMode(str, Enum):
    NATIVE_HOOKS = "native-hooks"
    HYBRID = "hybrid"
    LEGACY_PATCH = "legacy-patch"


KNOWN_NATIVE_CAPABILITIES = frozenset({
    "authenticated_ingress",
    "turn_start",
    "turn_terminal_result",
    "stable_tool_lifecycle",
    "approval_observe",
    "subagent_lifecycle",
    "answer_delta",
    "thinking_delta",
    "interaction_round_trip",
    "final_delivery_disposition",
    "command_platform_notice",
    "cron_delivery",
    "exact_native_delivery",
})

KNOWN_PATCH_GROUPS = frozenset({
    "ingress_binding", "terminal_disposition", "answer_delta",
    "thinking_delta", "clarify_round_trip", "approval_round_trip",
    "status_notice", "slash_confirm", "command_card_startup",
    "command_card_adapter", "native_redelivery", "platform_notice",
    "hfc_command", "cron_delivery", "exact_base_no_text",
    "exact_base_final_delivery", "message_start", "message_terminal",
    "queued_terminal", "stable_tool_lifecycle", "legacy_tool_lifecycle",
    "subagent_parent_identity",
})

NATIVE_REQUIRED_CAPABILITIES = KNOWN_NATIVE_CAPABILITIES
HYBRID_REQUIRED_NATIVE_CAPABILITIES = frozenset({
    "turn_start",
    "turn_terminal_result",
    "stable_tool_lifecycle",
    "approval_observe",
})
HYBRID_REQUIRED_PATCH_GROUPS = frozenset({
    "ingress_binding", "terminal_disposition", "answer_delta",
    "thinking_delta", "clarify_round_trip", "approval_round_trip",
    "status_notice", "slash_confirm", "command_card_startup",
    "command_card_adapter", "native_redelivery", "platform_notice",
    "hfc_command", "cron_delivery", "exact_base_no_text",
    "exact_base_final_delivery", "subagent_parent_identity",
})
LEGACY_REQUIRED_PATCH_GROUPS = HYBRID_REQUIRED_PATCH_GROUPS | frozenset({
    "message_start",
    "message_terminal",
    "queued_terminal",
    "stable_tool_lifecycle",
    "legacy_tool_lifecycle",
})


@dataclass(frozen=True)
class NativeHookCapabilities:
    available: frozenset[str]

    def __post_init__(self) -> None:
        values = frozenset(str(name) for name in self.available)
        unknown = values - KNOWN_NATIVE_CAPABILITIES
        if unknown:
            raise ValueError(
                "unknown native capabilities: " + ", ".join(sorted(unknown))
            )
        object.__setattr__(self, "available", values)

    @classmethod
    def from_names(cls, names: Iterable[str]) -> "NativeHookCapabilities":
        return cls(names)


@dataclass(frozen=True)
class PatchCapabilities:
    available: frozenset[str]

    def __post_init__(self) -> None:
        values = frozenset(str(name) for name in self.available)
        unknown = values - KNOWN_PATCH_GROUPS
        if unknown:
            raise ValueError(
                "unknown patch groups: " + ", ".join(sorted(unknown))
            )
        object.__setattr__(self, "available", values)

    @classmethod
    def from_names(cls, names: Iterable[str]) -> "PatchCapabilities":
        return cls(names)


@dataclass(frozen=True)
class IntegrationDecision:
    supported: bool
    mode: IntegrationMode | None
    reason: str
    required_native_capabilities: frozenset[str]
    required_patch_groups: frozenset[str]
    fingerprint: str


def capability_fingerprint(
    native: NativeHookCapabilities,
    patches: PatchCapabilities,
) -> str:
    payload = {
        "domain": "hfc-integration-capabilities-v1",
        "native": sorted(native.available),
        "patches": sorted(patches.available),
    }
    canonical = json.dumps(
        payload,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(canonical).hexdigest()


def select_integration_mode(
    native: NativeHookCapabilities,
    patches: PatchCapabilities,
) -> IntegrationDecision:
    fingerprint = capability_fingerprint(native, patches)
    if NATIVE_REQUIRED_CAPABILITIES <= native.available:
        return IntegrationDecision(
            supported=True,
            mode=IntegrationMode.NATIVE_HOOKS,
            reason="all required official capabilities are verified",
            required_native_capabilities=NATIVE_REQUIRED_CAPABILITIES,
            required_patch_groups=frozenset(),
            fingerprint=fingerprint,
        )
    if (
        HYBRID_REQUIRED_NATIVE_CAPABILITIES <= native.available
        and HYBRID_REQUIRED_PATCH_GROUPS <= patches.available
    ):
        return IntegrationDecision(
            supported=True,
            mode=IntegrationMode.HYBRID,
            reason="official lifecycle and all required hybrid patch groups are verified",
            required_native_capabilities=HYBRID_REQUIRED_NATIVE_CAPABILITIES,
            required_patch_groups=HYBRID_REQUIRED_PATCH_GROUPS,
            fingerprint=fingerprint,
        )
    if LEGACY_REQUIRED_PATCH_GROUPS <= patches.available:
        return IntegrationDecision(
            supported=True,
            mode=IntegrationMode.LEGACY_PATCH,
            reason="complete legacy patch groups are verified",
            required_native_capabilities=frozenset(),
            required_patch_groups=LEGACY_REQUIRED_PATCH_GROUPS,
            fingerprint=fingerprint,
        )
    missing_native = sorted(HYBRID_REQUIRED_NATIVE_CAPABILITIES - native.available)
    missing_hybrid = sorted(HYBRID_REQUIRED_PATCH_GROUPS - patches.available)
    missing_legacy = sorted(LEGACY_REQUIRED_PATCH_GROUPS - patches.available)
    return IntegrationDecision(
        supported=False,
        mode=None,
        reason=(
            "missing verified integration capabilities: "
            f"native={missing_native}; hybrid={missing_hybrid}; "
            f"legacy={missing_legacy}"
        ),
        required_native_capabilities=HYBRID_REQUIRED_NATIVE_CAPABILITIES,
        required_patch_groups=HYBRID_REQUIRED_PATCH_GROUPS,
        fingerprint=fingerprint,
    )
