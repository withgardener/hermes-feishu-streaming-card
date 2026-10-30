import hashlib
import json

import pytest

from hermes_feishu_card.install.manifest import (
    CRON_INSTALL_MANIFEST_FIELDS,
    ManifestStructureError,
    ManifestVersionError,
    file_sha256,
    render_install_manifest_v3,
    validate_install_manifest,
    validate_install_manifest_version,
)
from hermes_feishu_card.install.patcher import HYBRID_PATCH_REGISTRY
from hermes_feishu_card.integration import HYBRID_REQUIRED_PATCH_GROUPS


def test_file_sha256_returns_stable_digest(tmp_path):
    path = tmp_path / "run.py"
    path.write_text("hello hermes\n", encoding="utf-8")

    assert file_sha256(path) == hashlib.sha256(b"hello hermes\n").hexdigest()


@pytest.mark.parametrize("manifest", [{}, {"manifest_version": 1}])
def test_validate_install_manifest_version_accepts_legacy_read_compatibility(manifest):
    assert validate_install_manifest_version(manifest) == 1


def test_validate_install_manifest_version_accepts_current_version():
    assert validate_install_manifest_version({"manifest_version": 3}) == 3


def test_validate_install_manifest_version_keeps_v2_read_compatibility():
    assert validate_install_manifest_version({"manifest_version": 2}) == 2


@pytest.mark.parametrize("version", [0, 4, 999, "3", True, None])
def test_validate_install_manifest_version_refuses_unknown_semantics(version):
    with pytest.raises(ManifestVersionError, match="newer installer required"):
        validate_install_manifest_version({"manifest_version": version})


@pytest.mark.parametrize("field", sorted(CRON_INSTALL_MANIFEST_FIELDS))
def test_validate_install_manifest_refuses_every_partial_cron_field(field):
    with pytest.raises(ManifestStructureError, match="cron ownership fields"):
        validate_install_manifest({"manifest_version": 2, field: "owned"})


def test_validate_install_manifest_accepts_complete_cron_field_group():
    manifest = {"manifest_version": 2}
    manifest.update({field: "owned" for field in CRON_INSTALL_MANIFEST_FIELDS})

    assert validate_install_manifest(manifest) == 2


def _valid_v3_manifest():
    patch_targets = {
        target: sorted(groups)
        for target, groups in HYBRID_PATCH_REGISTRY.target_groups(
            HYBRID_REQUIRED_PATCH_GROUPS
        ).items()
    }
    targets = {
        target: {
            "path": target,
            "patched_sha256": "a" * 64,
            "backup": target + ".hermes-feishu-card.bak",
            "backup_sha256": "b" * 64,
        }
        for target in patch_targets
    }
    return {
        "manifest_version": 3,
        "phase": "installed",
        "targets": targets,
        "integration": {
            "mode": "hybrid",
            "capability_fingerprint": "sha256:" + "c" * 64,
            "patch_groups": sorted(HYBRID_REQUIRED_PATCH_GROUPS),
            "patch_targets": patch_targets,
            "plugin": {
                "key": "hermes-feishu-card",
                "entry_point": "hermes_feishu_card.hermes_plugin",
                "distribution": "hermes-feishu-streaming-card",
                "version": "4.3.0",
                "python_identity": "sha256:" + "d" * 64,
            },
            "plugin_config": {
                "enabled_before": False,
                "added_by_hfc": True,
                "pre_sha256": "e" * 64,
                "post_sha256": "f" * 64,
                "config_backup_id": "hfc-config-preimage-" + "1" * 32,
                "backup_sha256": "e" * 64,
            },
        },
    }


def test_validate_v3_manifest_accepts_exact_seven_target_hybrid_ownership():
    assert validate_install_manifest(_valid_v3_manifest()) == 3


@pytest.mark.parametrize("value", ["future", "prepared-again", ""])
def test_validate_v3_manifest_rejects_unknown_phase(value):
    manifest = _valid_v3_manifest()
    manifest["phase"] = value
    with pytest.raises(ManifestVersionError, match="newer installer required"):
        validate_install_manifest(manifest)


def test_validate_v3_manifest_rejects_partial_target_or_group_union():
    manifest = _valid_v3_manifest()
    manifest["targets"].pop("tools/approval.py")
    with pytest.raises(ManifestStructureError, match="targets"):
        validate_install_manifest(manifest)

    manifest = _valid_v3_manifest()
    manifest["integration"]["patch_targets"]["tools/approval.py"] = []
    with pytest.raises(ManifestStructureError, match="patch target"):
        validate_install_manifest(manifest)


def test_validate_v3_manifest_rejects_absolute_paths_and_secret_fields():
    manifest = _valid_v3_manifest()
    manifest["targets"]["gateway/run.py"]["path"] = "/private/run.py"
    with pytest.raises(ManifestStructureError, match="portable"):
        validate_install_manifest(manifest)

    manifest = _valid_v3_manifest()
    manifest["integration"]["plugin_config"]["config_path"] = "/secret/config.yaml"
    with pytest.raises(ManifestStructureError, match="fields"):
        validate_install_manifest(manifest)


def test_render_v3_manifest_is_portable_closed_and_round_trips_validation():
    patch_targets = HYBRID_PATCH_REGISTRY.target_groups(
        HYBRID_REQUIRED_PATCH_GROUPS
    )
    target_contents = {
        target: (f"patched:{target}\n".encode(), f"original:{target}\n".encode())
        for target in patch_targets
    }
    rendered = render_install_manifest_v3(
        phase="installed",
        target_contents=target_contents,
        mode="hybrid",
        capability_fingerprint="sha256:" + "c" * 64,
        patch_groups=HYBRID_REQUIRED_PATCH_GROUPS,
        patch_targets=patch_targets,
        plugin_version="4.3.0",
        python_identity="sha256:" + "d" * 64,
        plugin_config={
            "enabled_before": False,
            "added_by_hfc": True,
            "pre_sha256": "e" * 64,
            "post_sha256": "f" * 64,
            "config_backup_id": "hfc-config-preimage-" + "1" * 32,
            "backup_sha256": "e" * 64,
        },
    )
    manifest = json.loads(rendered)

    assert validate_install_manifest(manifest) == 3
    assert manifest["targets"]["gateway/run.py"]["path"] == "gateway/run.py"
    assert manifest["targets"]["gateway/run.py"]["backup"].endswith(
        ".hermes_feishu_card.bak"
    )
    assert "/private/" not in rendered
