from __future__ import annotations

from pathlib import Path
import re

TRUSTED_PROFILE_SOURCES = frozenset(
    {"env", "locals", "hermes_home", "fallback_default"}
)
SANITIZED_PROFILE_SOURCES = frozenset(
    {"sanitized_env", "sanitized_locals", "sanitized_hermes_home"}
)
PROFILE_SOURCES = TRUSTED_PROFILE_SOURCES | SANITIZED_PROFILE_SOURCES

PROFILE_SOURCE_FALLBACK = "fallback_default"
PROFILE_ID_PATTERN = re.compile(r"^[A-Za-z0-9_.-]{1,64}$")


def resolve_authenticated_profile_identity(
    *,
    explicit_env_profile: object = None,
    authenticated_session_profile: object = None,
    hermes_home_profile: object = None,
    hermes_home_membership_verified: object = False,
    no_named_profile: object = False,
) -> tuple[str, str] | None:
    """Resolve explicit authenticated profile facts without scanning objects."""
    if (
        type(hermes_home_membership_verified) is not bool
        or type(no_named_profile) is not bool
    ):
        return None
    if hermes_home_profile is None:
        if hermes_home_membership_verified:
            return None
    elif not hermes_home_membership_verified:
        return None

    candidates = (
        (explicit_env_profile, "env"),
        (authenticated_session_profile, "locals"),
        (hermes_home_profile, "hermes_home"),
    )
    facts: list[tuple[str, str]] = []
    for profile_id, source in candidates:
        if profile_id is None:
            continue
        if not _is_exact_safe_profile_id(profile_id):
            return None
        facts.append((profile_id, source))
    if no_named_profile:
        if facts:
            return None
        return "default", PROFILE_SOURCE_FALLBACK
    if not facts:
        return None
    if any(profile_id != facts[0][0] for profile_id, _source in facts[1:]):
        return None
    return facts[0]


def validate_trusted_profile_identity(
    profile_id: object,
    profile_source: object,
    *,
    hermes_home_membership_verified: object = False,
) -> tuple[str, str] | None:
    """Validate one already-selected ingress profile and its explicit evidence."""
    if (
        not _is_exact_safe_profile_id(profile_id)
        or type(profile_source) is not str
        or profile_source not in TRUSTED_PROFILE_SOURCES
        or type(hermes_home_membership_verified) is not bool
    ):
        return None
    if profile_source == "hermes_home":
        if not hermes_home_membership_verified:
            return None
    elif hermes_home_membership_verified:
        return None
    if profile_source == PROFILE_SOURCE_FALLBACK and profile_id != "default":
        return None
    return profile_id, profile_source


def legacy_safe_profile_id(value: str) -> str:
    candidate = value.strip()
    if PROFILE_ID_PATTERN.fullmatch(candidate):
        return candidate
    return "default"


def legacy_profile_identity(value: str, source: str) -> tuple[str, str]:
    profile_id = legacy_safe_profile_id(value)
    if profile_id == "default" and value.strip() != "default":
        return profile_id, f"sanitized_{source}"
    return profile_id, source


def profile_from_hermes_home_path(path: str) -> str | None:
    if not path:
        return None
    normalized = str(Path(path).expanduser()).replace("\\", "/")
    parts = tuple(part for part in normalized.split("/") if part)
    for index in range(len(parts) - 2):
        if parts[index] in {".hermes", "hermes"} and parts[index + 1] == "profiles":
            if index + 3 != len(parts):
                return None
            candidate = parts[index + 2].strip()
            if candidate:
                return candidate
    return None


def _is_exact_safe_profile_id(value: object) -> bool:
    return type(value) is str and PROFILE_ID_PATTERN.fullmatch(value) is not None
