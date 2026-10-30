import pytest

from hermes_feishu_card.integration import (
    HYBRID_REQUIRED_NATIVE_CAPABILITIES,
    HYBRID_REQUIRED_PATCH_GROUPS,
    KNOWN_PATCH_GROUPS,
    LEGACY_REQUIRED_PATCH_GROUPS,
    NATIVE_REQUIRED_CAPABILITIES,
    IntegrationMode,
    NativeHookCapabilities,
    PatchCapabilities,
    capability_fingerprint,
    select_integration_mode,
)


FIXED_TAG_NATIVE_CAPABILITIES = frozenset({
    "turn_start",
    "turn_terminal_result",
    "stable_tool_lifecycle",
    "approval_observe",
})
EXPECTED_NATIVE_REQUIRED_CAPABILITIES = frozenset({
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
OLD_HYBRID_PATCH_GROUPS = frozenset({
    "ingress_binding",
    "terminal_disposition",
    "answer_delta",
    "thinking_delta",
    "clarify_round_trip",
    "approval_round_trip",
    "status_notice",
    "slash_confirm",
    "command_card_startup",
    "command_card_adapter",
    "native_redelivery",
    "platform_notice",
    "hfc_command",
    "cron_delivery",
    "exact_base_no_text",
    "exact_base_final_delivery",
})
EXPECTED_HYBRID_PATCH_GROUPS = OLD_HYBRID_PATCH_GROUPS | frozenset({
    "subagent_parent_identity",
})
EXPECTED_LEGACY_PATCH_GROUPS = EXPECTED_HYBRID_PATCH_GROUPS | frozenset({
    "message_start",
    "message_terminal",
    "queued_terminal",
    "stable_tool_lifecycle",
    "legacy_tool_lifecycle",
})


def native(*names: str) -> NativeHookCapabilities:
    return NativeHookCapabilities.from_names(names)


def patches(*names: str) -> PatchCapabilities:
    return PatchCapabilities.from_names(names)


def test_selector_prefers_fully_verified_native_hooks():
    assert NATIVE_REQUIRED_CAPABILITIES == EXPECTED_NATIVE_REQUIRED_CAPABILITIES
    decision = select_integration_mode(
        native(*NATIVE_REQUIRED_CAPABILITIES),
        patches(*LEGACY_REQUIRED_PATCH_GROUPS),
    )
    assert decision.supported is True
    assert decision.mode is IntegrationMode.NATIVE_HOOKS
    assert decision.required_patch_groups == frozenset()


def test_fixed_tag_four_native_plus_old_sixteen_groups_is_rejected():
    decision = select_integration_mode(
        native(*FIXED_TAG_NATIVE_CAPABILITIES),
        patches(*OLD_HYBRID_PATCH_GROUPS),
    )

    assert decision.supported is False
    assert decision.mode is None
    assert "subagent_parent_identity" in decision.reason


def test_fixed_tag_four_native_plus_corrected_seventeen_groups_selects_hybrid():
    assert HYBRID_REQUIRED_NATIVE_CAPABILITIES == FIXED_TAG_NATIVE_CAPABILITIES
    assert HYBRID_REQUIRED_PATCH_GROUPS == EXPECTED_HYBRID_PATCH_GROUPS
    assert "subagent_parent_identity" in KNOWN_PATCH_GROUPS

    decision = select_integration_mode(
        native(*FIXED_TAG_NATIVE_CAPABILITIES),
        patches(*EXPECTED_HYBRID_PATCH_GROUPS),
    )

    assert decision.supported is True
    assert decision.mode is IntegrationMode.HYBRID
    assert decision.required_native_capabilities == FIXED_TAG_NATIVE_CAPABILITIES
    assert decision.required_patch_groups == EXPECTED_HYBRID_PATCH_GROUPS


def test_fixed_tag_hybrid_rejects_only_missing_parent_identity_group():
    decision = select_integration_mode(
        native(*FIXED_TAG_NATIVE_CAPABILITIES),
        patches(*(EXPECTED_HYBRID_PATCH_GROUPS - {"subagent_parent_identity"})),
    )

    assert decision.supported is False
    assert decision.mode is None
    assert "hybrid=['subagent_parent_identity']" in decision.reason


def test_selector_falls_back_to_legacy_only_with_complete_legacy_groups():
    assert LEGACY_REQUIRED_PATCH_GROUPS == EXPECTED_LEGACY_PATCH_GROUPS
    decision = select_integration_mode(native(), patches(*LEGACY_REQUIRED_PATCH_GROUPS))
    incomplete = select_integration_mode(
        native(),
        patches(*(LEGACY_REQUIRED_PATCH_GROUPS - {"subagent_parent_identity"})),
    )

    assert decision.mode is IntegrationMode.LEGACY_PATCH
    assert decision.required_patch_groups == LEGACY_REQUIRED_PATCH_GROUPS
    assert incomplete.supported is False
    assert incomplete.mode is None


def test_selector_rejects_incomplete_paths():
    decision = select_integration_mode(native(), patches("ingress_binding"))
    assert decision.supported is False
    assert decision.mode is None
    assert "missing" in decision.reason


def test_fingerprint_is_order_independent_and_domain_separated():
    left = capability_fingerprint(
        native("turn_start", "turn_terminal_result"),
        patches("answer_delta", "thinking_delta"),
    )
    right = capability_fingerprint(
        native("turn_terminal_result", "turn_start"),
        patches("thinking_delta", "answer_delta"),
    )
    changed = capability_fingerprint(
        native("turn_start"), patches("answer_delta", "thinking_delta")
    )
    assert left == right
    assert left.startswith("sha256:")
    assert left != changed


def test_fingerprint_reflects_parent_identity_patch_group_deterministically():
    corrected = capability_fingerprint(
        native(*FIXED_TAG_NATIVE_CAPABILITIES),
        patches(*EXPECTED_HYBRID_PATCH_GROUPS),
    )
    reordered = capability_fingerprint(
        native(*reversed(sorted(FIXED_TAG_NATIVE_CAPABILITIES))),
        patches(*reversed(sorted(EXPECTED_HYBRID_PATCH_GROUPS))),
    )
    old = capability_fingerprint(
        native(*FIXED_TAG_NATIVE_CAPABILITIES),
        patches(*OLD_HYBRID_PATCH_GROUPS),
    )

    assert corrected == reordered
    assert corrected == "sha256:6b9bdfd4af0971fdc13e415f306380e666efac3d1977465ad90e13435dd5ba25"
    assert corrected != old


@pytest.mark.parametrize(
    "factory", [NativeHookCapabilities.from_names, PatchCapabilities.from_names]
)
def test_capability_models_reject_unknown_names(factory):
    with pytest.raises(ValueError, match="unknown"):
        factory(["invented_capability"])


@pytest.mark.parametrize(
    ("factory", "name"),
    [
        (NativeHookCapabilities, "invented_capability"),
        (PatchCapabilities, "invented_group"),
    ],
)
def test_capability_models_reject_unknown_names_from_direct_construction(factory, name):
    with pytest.raises(ValueError, match="unknown"):
        factory(frozenset({name}))
