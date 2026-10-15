from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import threading
from typing import Any, Mapping

from .config_rules import normalize_native_chats as normalize_native_chats


CARD_DISPOSITION = "card"
NATIVE_DISPOSITION = "native"


@dataclass(frozen=True)
class ChatDeliveryDecision:
    disposition: str
    reason: str


class ChatDeliveryPolicy:
    def __init__(
        self,
        *,
        native_chats: tuple[str, ...] = (),
        profile_native_chats: Mapping[str, tuple[str, ...]] | None = None,
    ) -> None:
        self._native_chats = frozenset(native_chats)
        self._profile_native_chats = {
            str(profile_id): frozenset(chat_ids)
            for profile_id, chat_ids in (profile_native_chats or {}).items()
        }
        self._profiles_enabled = bool(profile_native_chats)

    @classmethod
    def from_config(cls, config: Mapping[str, Any]) -> "ChatDeliveryPolicy":
        profiles = config.get("profiles")
        if isinstance(profiles, Mapping) and profiles:
            profile_native_chats: dict[str, tuple[str, ...]] = {}
            for raw_profile_id, raw_profile in profiles.items():
                profile_id = str(raw_profile_id)
                if not isinstance(raw_profile, Mapping):
                    raise ValueError(f"profile {profile_id!r} must be a mapping")
                bindings = raw_profile.get("bindings")
                if bindings is None:
                    bindings = {}
                if not isinstance(bindings, Mapping):
                    raise ValueError(
                        f"profiles.{profile_id}.bindings must be a mapping"
                    )
                profile_native_chats[profile_id] = tuple(
                    normalize_native_chats(
                        bindings.get("native_chats", []),
                        path=f"profiles.{profile_id}.bindings.native_chats",
                    )
                )
            return cls(profile_native_chats=profile_native_chats)

        bindings = config.get("bindings")
        if bindings is None:
            bindings = {}
        if not isinstance(bindings, Mapping):
            raise ValueError("bindings must be a mapping")
        return cls(
            native_chats=tuple(
                normalize_native_chats(bindings.get("native_chats", []))
            )
        )

    def decide(self, chat_id: str, *, profile_id: str = "") -> ChatDeliveryDecision:
        normalized_chat_id = str(chat_id or "").strip()
        if not normalized_chat_id:
            return ChatDeliveryDecision(NATIVE_DISPOSITION, "chat_identity_missing")
        if self._profiles_enabled:
            selected_profile = str(profile_id or "default").strip() or "default"
            native_chats = self._profile_native_chats.get(selected_profile)
            if native_chats is None:
                return ChatDeliveryDecision(NATIVE_DISPOSITION, "profile_unknown")
        else:
            native_chats = self._native_chats
        if normalized_chat_id in native_chats:
            return ChatDeliveryDecision(
                NATIVE_DISPOSITION,
                "bindings.native_chats",
            )
        return ChatDeliveryDecision(CARD_DISPOSITION, "default_card")

    def safe_diagnostics(self) -> dict[str, int]:
        if self._profiles_enabled:
            return {
                "native_chat_count": sum(
                    len(chat_ids) for chat_ids in self._profile_native_chats.values()
                ),
                "profile_count": len(self._profile_native_chats),
            }
        return {
            "native_chat_count": len(self._native_chats),
            "profile_count": 0,
        }


class ReloadingDeliveryPolicyProvider:
    """Reload only delivery policy when an atomic config replacement is observed."""

    def __init__(
        self,
        config_path: str | Path,
        *,
        initial_config: Mapping[str, Any] | None = None,
        env_file: str | Path | None = None,
    ) -> None:
        self._config_path = Path(config_path).expanduser()
        self._env_file = Path(env_file).expanduser() if env_file is not None else None
        self._lock = threading.RLock()
        self._fingerprint: tuple[int, int, int] | None = None
        self._policy: ChatDeliveryPolicy | None = None
        self._reload_failed = False
        if initial_config is not None:
            self._policy = ChatDeliveryPolicy.from_config(initial_config)
            self._fingerprint = self._current_fingerprint()

    def decide(self, chat_id: str, *, profile_id: str = "") -> ChatDeliveryDecision:
        with self._lock:
            self._reload_if_changed()
            policy = self._policy
            if policy is None or self._reload_failed:
                return ChatDeliveryDecision(NATIVE_DISPOSITION, "policy_unavailable")
            return policy.decide(chat_id, profile_id=profile_id)

    def safe_diagnostics(self) -> dict[str, Any]:
        with self._lock:
            self._reload_if_changed()
            if self._policy is None or self._reload_failed:
                return {
                    "status": "unavailable",
                    "native_chat_count": 0,
                    "profile_count": 0,
                }
            return {"status": "ready", **self._policy.safe_diagnostics()}

    def _reload_if_changed(self) -> None:
        fingerprint = self._current_fingerprint()
        if fingerprint == self._fingerprint and (
            self._policy is not None or self._reload_failed
        ):
            return
        self._fingerprint = fingerprint
        if fingerprint is None:
            self._policy = None
            self._reload_failed = True
            return
        try:
            from .config import load_config

            config = (
                load_config(self._config_path, env_file=self._env_file)
                if self._env_file is not None
                else load_config(self._config_path)
            )
            self._policy = ChatDeliveryPolicy.from_config(config)
            self._reload_failed = False
        except Exception:
            self._policy = None
            self._reload_failed = True

    def _current_fingerprint(self) -> tuple[int, int, int] | None:
        try:
            stat = self._config_path.stat()
        except OSError:
            return None
        if not self._config_path.is_file():
            return None
        return (stat.st_mtime_ns, stat.st_size, stat.st_ino)
