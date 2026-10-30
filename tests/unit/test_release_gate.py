from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from scripts.verify_release import (
    ReleaseGateError,
    parse_release_tag,
    read_release_markers,
    resolve_annotated_tag_commit,
    verify_release_metadata,
    verify_release_tag,
)


def _git(root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(root), *args],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def _write_markers(root: Path, version: str = "4.2.4") -> None:
    (root / "hermes_feishu_card").mkdir(parents=True, exist_ok=True)
    (root / ".github" / "workflows").mkdir(parents=True, exist_ok=True)
    (root / "pyproject.toml").write_text(
        f'[project]\nversion = "{version}"\n', encoding="utf-8"
    )
    (root / "hermes_feishu_card" / "__init__.py").write_text(
        f'__version__ = "{version}"\n', encoding="utf-8"
    )
    (root / "config.yaml.example").write_text(
        f"# Hermes Feishu Streaming Card V{version} sidecar configuration\n",
        encoding="utf-8",
    )
    (root / "docker-compose.example.yml").write_text(
        f'    HFC_VERSION: "${{HFC_VERSION:-v{version}}}"\n',
        encoding="utf-8",
    )
    (root / ".github" / "workflows" / "tests.yml").write_text(
        f"          HFC_VERSION: v{version}\n",
        encoding="utf-8",
    )


def _release_repo(tmp_path: Path, *, annotated: bool = True):
    root = tmp_path / "repo"
    root.mkdir()
    _write_markers(root)
    _git(root, "init", "-q")
    _git(root, "config", "user.name", "Release Gate Test")
    _git(root, "config", "user.email", "release-gate@example.invalid")
    _git(root, "add", ".")
    _git(root, "commit", "-qm", "release candidate")
    commit = _git(root, "rev-parse", "HEAD")
    if annotated:
        _git(root, "tag", "-a", "v4.2.4", "-m", "Release v4.2.4")
    else:
        _git(root, "tag", "v4.2.4")
    _git(root, "update-ref", "refs/remotes/origin/main", commit)
    return root, commit


def test_release_gate_accepts_matching_annotated_tag(tmp_path):
    root, commit = _release_repo(tmp_path)

    assert parse_release_tag("v4.2.4") == "4.2.4"
    assert read_release_markers(root) == {
        "pyproject": "4.2.4",
        "package": "4.2.4",
        "config": "4.2.4",
        "compose": "4.2.4",
        "ci": "4.2.4",
    }
    assert resolve_annotated_tag_commit(root, "v4.2.4") == commit
    verify_release_tag(root, "v4.2.4", commit, True)


def test_release_gate_rejects_lightweight_tag(tmp_path):
    root, _commit = _release_repo(tmp_path, annotated=False)

    with pytest.raises(ReleaseGateError, match="tag_not_annotated"):
        resolve_annotated_tag_commit(root, "v4.2.4")


def test_release_gate_rejects_tag_version_mismatch(tmp_path):
    root, _commit = _release_repo(tmp_path)

    with pytest.raises(ReleaseGateError, match="metadata_mismatch"):
        verify_release_metadata(root, "v4.2.5")


def test_release_gate_rejects_tag_commit_different_from_head(tmp_path):
    root, tagged_commit = _release_repo(tmp_path)
    (root / "next.txt").write_text("next\n", encoding="utf-8")
    _git(root, "add", "next.txt")
    _git(root, "commit", "-qm", "next")

    with pytest.raises(ReleaseGateError, match="head_mismatch"):
        verify_release_tag(root, "v4.2.4", tagged_commit, False)


def test_release_gate_rejects_tag_outside_origin_main(tmp_path):
    root, commit = _release_repo(tmp_path)
    _git(root, "checkout", "--orphan", "unrelated")
    _git(root, "rm", "-rf", ".")
    (root / "main.txt").write_text("main\n", encoding="utf-8")
    _git(root, "add", "main.txt")
    _git(root, "commit", "-qm", "unrelated main")
    _git(root, "update-ref", "refs/remotes/origin/main", "HEAD")
    _git(root, "checkout", "--detach", commit)

    with pytest.raises(ReleaseGateError, match="tag_not_on_main"):
        verify_release_tag(root, "v4.2.4", commit, True)


def test_release_gate_rejects_stale_config_template_version(tmp_path):
    _write_markers(tmp_path)
    (tmp_path / "config.yaml.example").write_text(
        "# Hermes Feishu Streaming Card V4.1.4 sidecar configuration\n",
        encoding="utf-8",
    )

    with pytest.raises(ReleaseGateError, match="metadata_mismatch"):
        verify_release_metadata(tmp_path, "v4.2.4")


@pytest.mark.parametrize(
    "value",
    ["main", "4.2.4", "refs/tags/v4.2.4", "v4.2", "v4.2.4-rc1"],
)
def test_release_gate_rejects_branch_or_malformed_dispatch_input(value):
    with pytest.raises(ReleaseGateError, match="invalid_tag"):
        parse_release_tag(value)
