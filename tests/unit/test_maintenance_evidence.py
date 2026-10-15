from copy import deepcopy

import pytest

from hermes_feishu_card.maintenance_evidence import (
    DrainEvidence,
    DrainProof,
    active_maintenance_sessions,
)
from hermes_feishu_card.maintenance_update import _wait_for_drain


def health(sequence=1, owner="a" * 64):
    return {
        "maintenance_active_sessions": 0,
        "gateway_active_sessions": 0,
        "maintenance_drain": {"active": True, "valid": True},
        "readiness": {
            "status": "ready",
            "runtime_id_hash": owner,
            "last_sequence": sequence,
            "last_seen_age_seconds": 0,
            "admission_draining": True,
            "active_work_count_complete": True,
            "drain_home_verified": True,
        },
    }


INVALID_FIELDS = [
    ("readiness", None, value) for value in (None, [], "ready", 1)
] + [
    ("maintenance_drain", None, value) for value in (None, [], "active", 1)
] + [
    ("readiness", "last_sequence", value)
    for value in (None, False, True, -1, 0, 1.0, "1", [])
] + [
    ("readiness", "last_seen_age_seconds", value)
    for value in (None, False, True, -1, 31, 0.0, "0", [])
] + [
    ("readiness", "runtime_id_hash", value) for value in (None, "", False, 1, [])
] + [
    ("gateway_active_sessions", None, value)
    for value in (None, False, True, -1, 0.0, "0", [])
] + [
    ("readiness", "status", value) for value in (None, "starting", "degraded", True)
] + [
    (section, key, value)
    for section, key in (
        ("maintenance_drain", "active"),
        ("maintenance_drain", "valid"),
        ("readiness", "admission_draining"),
        ("readiness", "active_work_count_complete"),
        ("readiness", "drain_home_verified"),
    )
    for value in (None, False, 1, "true", [])
]


@pytest.mark.parametrize("section,key,value", INVALID_FIELDS)
def test_invalid_evidence_is_rejected_without_mutating_health(section, key, value):
    sample = health()
    if key is None:
        sample[section] = value
    else:
        sample[section][key] = value
    before = deepcopy(sample)
    assert DrainEvidence.from_health(sample) is None
    assert sample == before


@pytest.mark.parametrize("section,key", [
    ("readiness", None), ("maintenance_drain", None),
    ("gateway_active_sessions", None),
    ("readiness", "status"), ("readiness", "runtime_id_hash"),
    ("readiness", "last_sequence"), ("readiness", "last_seen_age_seconds"),
    ("readiness", "admission_draining"),
    ("readiness", "active_work_count_complete"),
    ("readiness", "drain_home_verified"),
    ("maintenance_drain", "active"), ("maintenance_drain", "valid"),
])
def test_missing_required_evidence_is_rejected(section, key):
    sample = health()
    if key is None:
        del sample[section]
    else:
        del sample[section][key]
    assert DrainEvidence.from_health(sample) is None


@pytest.mark.parametrize("age", [0, 30])
def test_freshness_endpoints_and_input_are_preserved(age):
    sample = health(sequence=7)
    sample["readiness"]["last_seen_age_seconds"] = age
    sample["unrelated"] = {"nested": [1, 2]}
    before = deepcopy(sample)
    assert DrainEvidence.from_health(sample) == DrainEvidence("a" * 64, 7, 0)
    assert sample == before


@pytest.mark.parametrize("maintenance,gateway,expected", [
    (3, 0, 3), (0, 4, 4), (3, 4, 4),
    (False, 0, 0), (-1, 0, 0), ("bad", 0, 0), (None, 0, 0),
])
def test_active_projection_preserves_old_statistics_semantics(maintenance, gateway, expected):
    sample = health()
    sample.update(maintenance_active_sessions=maintenance, gateway_active_sessions=gateway)
    assert active_maintenance_sessions(sample) == expected
    assert DrainEvidence.from_health(sample).active_sessions == expected


def test_projection_defaults_are_not_stop_authority():
    assert active_maintenance_sessions({}) == 0
    assert DrainEvidence.from_health({}) is None
    sample = health()
    del sample["maintenance_active_sessions"]
    assert DrainEvidence.from_health(sample).active_sessions == 0


@pytest.mark.parametrize("interruption", [None, DrainEvidence("a" * 64, 2, 1)])
def test_invalid_or_busy_observation_resets_consecutive_idle_proof(interruption):
    proof = DrainProof()
    assert not proof.observe(DrainEvidence("a" * 64, 1, 0))
    assert not proof.observe(interruption)
    assert not proof.observe(DrainEvidence("a" * 64, 3, 0))
    assert proof.observe(DrainEvidence("a" * 64, 4, 0))


def test_owner_change_needs_its_own_two_samples():
    proof = DrainProof()
    assert not proof.observe(DrainEvidence("a", 10, 0))
    assert not proof.observe(DrainEvidence("b", 11, 0))
    assert proof.observe(DrainEvidence("b", 12, 0))


def test_duplicate_and_sequence_rollback_keep_previous_sample_contract():
    proof = DrainProof()
    assert not proof.observe(DrainEvidence("a", 10, 0))
    assert not proof.observe(DrainEvidence("a", 10, 0))
    assert not proof.observe(DrainEvidence("a", 5, 0))
    # The old poller replaced its previous sequence after rollback, rather than
    # retaining a historical maximum. This extraction must preserve that rule.
    assert proof.observe(DrainEvidence("a", 6, 0))


class Clock:
    def __init__(self):
        self.now = 0.0
        self.sleeps = []

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.now += seconds


def test_wait_fetch_failures_and_non_dict_reset_before_two_fresh_samples():
    clock = Clock()
    values = iter([health(1), RuntimeError("unavailable"), [], health(2), health(3)])
    calls = []

    def fetch():
        calls.append(clock.now)
        sample = next(values)
        if isinstance(sample, Exception):
            raise sample
        return sample

    assert _wait_for_drain(fetch, timeout_seconds=4, sleep=clock.sleep,
                           monotonic=lambda: clock.now)
    assert calls == [0, 1, 2, 3, 4]
    assert clock.sleeps == [1, 1, 1, 1]


@pytest.mark.parametrize("timeout", [0, -1])
def test_zero_budget_still_reads_one_sample_but_never_sleeps_or_accepts(timeout):
    clock = Clock()
    calls = []

    def fetch():
        calls.append(1)
        return health()

    assert not _wait_for_drain(fetch, timeout_seconds=timeout, sleep=clock.sleep,
                               monotonic=lambda: clock.now)
    assert calls == [1]
    assert clock.sleeps == []


def test_fractional_deadline_bounds_sleep_and_missing_health_fails_closed():
    clock = Clock()
    assert not _wait_for_drain(lambda: None, timeout_seconds=1.5, sleep=clock.sleep,
                               monotonic=lambda: clock.now)
    assert clock.now == 1.5
    assert clock.sleeps == [1, 0.5]
