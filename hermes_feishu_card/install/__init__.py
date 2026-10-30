"""Install-time safety helpers for Hermes sidecar integration."""

from importlib import import_module
from typing import Any

# Importing read-only evidence must not initialize transaction coordinators.
# Preserve the existing package names and the implementation object's identity.
_EXPORT_OWNERS = {
    "HermesDetection": "detect",
    "detect_hermes": "detect",
    "file_sha256": "manifest",
    "RecoveryClassification": "recovery",
    "RecoveryEvidence": "recovery",
    "RecoveryFinding": "recovery",
    "RecoveryPlan": "recovery",
    "plan_recovery": "recovery",
    "sanitize_recovery_plan": "recovery",
}


def __getattr__(name: str) -> Any:
    owner = _EXPORT_OWNERS.get(name)
    if owner is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    value = getattr(import_module(f".{owner}", __name__), name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(__all__))


__all__ = [
    "HermesDetection",
    "RecoveryClassification",
    "RecoveryEvidence",
    "RecoveryFinding",
    "RecoveryPlan",
    "detect_hermes",
    "file_sha256",
    "plan_recovery",
    "sanitize_recovery_plan",
]
