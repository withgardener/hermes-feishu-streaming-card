"""Read-only maintenance evidence and bounded consecutive-heartbeat proof.

These rules grant no process authority. The maintenance executor still owns
leases, polling, deadlines and all mutation after a successful drain.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import cast


def active_maintenance_sessions(health: dict[str, object]) -> int:
    values = (
        health.get("maintenance_active_sessions", 0),
        health.get("gateway_active_sessions", 0),
    )
    counts = [
        value
        for value in values
        if isinstance(value, int) and not isinstance(value, bool) and value >= 0
    ]
    return max(counts, default=0)



@dataclass(frozen=True)
class DrainEvidence:
    owner: str
    sequence: int
    active_sessions: int

    @classmethod
    def from_health(cls, health: dict[str, object]) -> DrainEvidence | None:
        readiness = health.get("readiness")
        drain = health.get("maintenance_drain")
        sequence = readiness.get("last_sequence") if isinstance(readiness, dict) else None
        heartbeat_age = (
            readiness.get("last_seen_age_seconds")
            if isinstance(readiness, dict)
            else None
        )
        owner = readiness.get("runtime_id_hash") if isinstance(readiness, dict) else None
        gateway_active = health.get("gateway_active_sessions")
        evidence_ready = (
            isinstance(drain, dict)
            and drain.get("active") is True
            and drain.get("valid") is True
            and isinstance(readiness, dict)
            and readiness.get("status") == "ready"
            and isinstance(owner, str) and bool(owner)
            and isinstance(sequence, int)
            and not isinstance(sequence, bool)
            and sequence >= 1
            and isinstance(heartbeat_age, int)
            and not isinstance(heartbeat_age, bool)
            and 0 <= heartbeat_age <= 30
            and isinstance(gateway_active, int)
            and not isinstance(gateway_active, bool)
            and gateway_active >= 0
            and readiness.get("admission_draining") is True
            and readiness.get("active_work_count_complete") is True
            and readiness.get("drain_home_verified") is True
        )
        if not evidence_ready:
            return None
        return cls(cast(str, owner), cast(int, sequence), active_maintenance_sessions(health))


@dataclass
class DrainProof:
    """Retain only the previous valid idle sample, never an owner registry."""

    _zero_sequence: int | None = None
    _zero_owner: str | None = None

    def observe(self, evidence: DrainEvidence | None) -> bool:
        if evidence is not None and evidence.active_sessions == 0:
            if (
                self._zero_sequence is not None
                and evidence.owner == self._zero_owner
                and evidence.sequence > self._zero_sequence
            ):
                return True
            self._zero_sequence = evidence.sequence
            self._zero_owner = evidence.owner
        else:
            self._zero_sequence = None
            self._zero_owner = None
        return False
