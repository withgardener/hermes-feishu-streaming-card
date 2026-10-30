from __future__ import annotations

import hashlib
import os
from pathlib import Path

import pytest

from hermes_feishu_card.install import v3
from hermes_feishu_card.integration import (
    HYBRID_REQUIRED_NATIVE_CAPABILITIES,
    HYBRID_REQUIRED_PATCH_GROUPS,
    NativeHookCapabilities,
    PatchCapabilities,
    select_integration_mode,
)


FIXED_SOURCE_ROOT = Path(
    os.environ.get(
        "HFC_FIXED_TAG_SOURCE_ROOT",
        "/private/tmp/hermes-agent-v2026.8.3-v430-audit",
    )
)


def _decision():
    return select_integration_mode(
        NativeHookCapabilities.from_names(HYBRID_REQUIRED_NATIVE_CAPABILITIES),
        PatchCapabilities.from_names(HYBRID_REQUIRED_PATCH_GROUPS),
    )


def test_build_fixed_tag_plan_verifies_renders_detects_and_restores_all_targets():
    plan = v3.build_fixed_tag_hybrid_plan(
        FIXED_SOURCE_ROOT,
        decision=_decision(),
        source_commit=v3.FIXED_TAG_COMMIT,
        plugin_evidence_sha256="sha256:" + "a" * 64,
    )

    assert set(plan.originals) == set(plan.rendered)
    assert len(plan.originals) == 7
    assert plan.patch_groups == HYBRID_REQUIRED_PATCH_GROUPS
    assert all(plan.rendered[target] != plan.originals[target] for target in plan.originals)
    assert plan.restore(plan.rendered) == plan.originals


def test_build_fixed_tag_plan_rejects_source_drift_before_render(tmp_path):
    root = tmp_path / "hermes"
    for target in v3.HYBRID_PATCH_TARGET_ORDER:
        path = root / target
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes((FIXED_SOURCE_ROOT / target).read_bytes())
    (root / "gateway" / "run.py").write_bytes(b"drift\n")

    with pytest.raises(v3.FixedTagInstallRefused, match="digest"):
        v3.build_fixed_tag_hybrid_plan(
            root,
            decision=_decision(),
            source_commit=v3.FIXED_TAG_COMMIT,
            plugin_evidence_sha256="sha256:" + "a" * 64,
        )


@pytest.mark.parametrize(
    ("commit", "attestation"),
    (
        ("0" * 40, "sha256:" + "a" * 64),
        (v3.FIXED_TAG_COMMIT, ""),
        (v3.FIXED_TAG_COMMIT, "sha256:" + "A" * 64),
    ),
)
def test_build_fixed_tag_plan_requires_exact_probe_evidence(commit, attestation):
    with pytest.raises(v3.FixedTagInstallRefused, match="probe evidence"):
        v3.build_fixed_tag_hybrid_plan(
            FIXED_SOURCE_ROOT,
            decision=_decision(),
            source_commit=commit,
            plugin_evidence_sha256=attestation,
        )


def test_plan_hashes_are_external_canonical_provenance_not_self_attested():
    plan = v3.build_fixed_tag_hybrid_plan(
        FIXED_SOURCE_ROOT,
        decision=_decision(),
        source_commit=v3.FIXED_TAG_COMMIT,
        plugin_evidence_sha256="sha256:" + "a" * 64,
    )
    assert plan.verified_original_sha256 == {
        target: hashlib.sha256(plan.originals[target]).hexdigest()
        for target in plan.originals
    }
