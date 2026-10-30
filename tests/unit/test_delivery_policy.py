from __future__ import annotations

from pathlib import Path

import pytest

from hermes_feishu_card.delivery_policy import (
    CARD_DISPOSITION,
    NATIVE_DISPOSITION,
    ChatDeliveryPolicy,
    ReloadingDeliveryPolicyProvider,
)


def test_exact_native_chat_match_rejects_near_matches():
    policy = ChatDeliveryPolicy.from_config(
        {"bindings": {"native_chats": ["chat-native-a"]}}
    )

    assert policy.decide("chat-native-a").disposition == NATIVE_DISPOSITION
    assert policy.decide("chat-native").disposition == CARD_DISPOSITION
    assert policy.decide("chat-native-a-suffix").disposition == CARD_DISPOSITION


def test_multi_profile_native_chats_are_isolated_and_top_level_is_not_inherited():
    policy = ChatDeliveryPolicy.from_config(
        {
            "bindings": {"native_chats": ["chat-top"]},
            "profiles": {
                "work": {"bindings": {"native_chats": ["chat-shared"]}},
                "personal": {"bindings": {"native_chats": []}},
            },
        }
    )

    assert policy.decide("chat-shared", profile_id="work").disposition == NATIVE_DISPOSITION
    assert policy.decide("chat-shared", profile_id="personal").disposition == CARD_DISPOSITION
    assert policy.decide("chat-top", profile_id="work").disposition == CARD_DISPOSITION
    unknown = policy.decide("chat-shared", profile_id="missing")
    assert unknown.disposition == NATIVE_DISPOSITION
    assert unknown.reason == "profile_unknown"


def test_policy_safe_diagnostics_never_exposes_chat_ids():
    policy = ChatDeliveryPolicy.from_config(
        {"bindings": {"native_chats": ["private-chat-marker"]}}
    )

    diagnostics = policy.safe_diagnostics()

    assert diagnostics == {"native_chat_count": 1, "profile_count": 0}
    assert "private-chat-marker" not in str(diagnostics)


def test_reloading_provider_applies_atomic_config_change_to_next_decision(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text("bindings:\n  native_chats: []\n", encoding="utf-8")
    provider = ReloadingDeliveryPolicyProvider(path)

    assert provider.decide("chat-later").disposition == CARD_DISPOSITION

    replacement = tmp_path / "replacement.yaml"
    replacement.write_text(
        "bindings:\n  native_chats:\n    - chat-later\n", encoding="utf-8"
    )
    replacement.replace(path)

    assert provider.decide("chat-later").disposition == NATIVE_DISPOSITION


def test_reloading_provider_fails_native_when_changed_config_is_invalid(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text("bindings:\n  native_chats: []\n", encoding="utf-8")
    provider = ReloadingDeliveryPolicyProvider(path)
    assert provider.decide("chat-a").disposition == CARD_DISPOSITION

    replacement = tmp_path / "replacement.yaml"
    replacement.write_text(
        "bindings:\n  native_chats: '*'\n", encoding="utf-8"
    )
    replacement.replace(path)

    decision = provider.decide("chat-a")
    assert decision.disposition == NATIVE_DISPOSITION
    assert decision.reason == "policy_unavailable"
    assert "chat-a" not in str(provider.safe_diagnostics())


@pytest.mark.parametrize(
    "value",
    ["*", "chat-*", "chat?", "[chat]", "re:chat", ""],
)
def test_policy_rejects_wildcard_like_or_empty_values(value):
    with pytest.raises(ValueError, match="bindings.native_chats"):
        ChatDeliveryPolicy.from_config({"bindings": {"native_chats": [value]}})


def test_provider_missing_file_is_native_without_leaking_path(tmp_path):
    path = Path(tmp_path) / "missing-config.yaml"
    provider = ReloadingDeliveryPolicyProvider(path)

    decision = provider.decide("private-chat-marker")

    assert decision.disposition == NATIVE_DISPOSITION
    assert str(path) not in str(provider.safe_diagnostics())


@pytest.mark.parametrize("value", ["chat-a", ("chat-a",), {"chat-a"}, {"a": "b"}])
def test_policy_requires_a_yaml_array(value):
    with pytest.raises(ValueError, match="must be an array"):
        ChatDeliveryPolicy.from_config({"bindings": {"native_chats": value}})
