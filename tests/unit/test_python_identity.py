"""Python identity preserves virtual-environment leaf paths without importing HTTP."""
from hashlib import sha256
import os
from pathlib import Path
import subprocess
import sys

import pytest

from hermes_feishu_card.runtime_ownership import python_executable_identity


def test_python_identity_is_stable_path_free_and_domain_separated(tmp_path):
    path = tmp_path / "private-runtime" / "bin" / "python"
    canonical = os.path.normcase(str(path.parent.resolve(strict=False) / path.name))
    expected = sha256(b"hermes-feishu-streaming-card:python-executable:v1\0" + os.fsencode(canonical)).hexdigest()
    identity = python_executable_identity(path)
    assert identity == "python-sha256:" + expected
    assert str(path) not in identity and "private-runtime" not in identity
    assert python_executable_identity(str(path)) == identity


@pytest.mark.skipif(os.name == "nt", reason="symlink creation may require Windows privilege")
def test_parent_aliases_match_but_different_venv_leaves_remain_distinct(tmp_path):
    env_a, env_b = tmp_path / "env-a", tmp_path / "env-b"
    for directory in (env_a, env_b):
        directory.mkdir()
        (directory / "python").symlink_to(sys.executable)
    alias = tmp_path / "env-a-alias"
    alias.symlink_to(env_a, target_is_directory=True)
    assert python_executable_identity(alias / "python") == python_executable_identity(env_a / "python")
    assert python_executable_identity(env_a / "python") != python_executable_identity(env_b / "python")


def test_identity_parent_resolution_failure_preserves_deterministic_fallback(tmp_path, monkeypatch):
    path = tmp_path / "bin/python"
    monkeypatch.setattr(Path, "resolve", lambda *args, **kwargs: (_ for _ in ()).throw(OSError("fixture resolution failure")))
    assert python_executable_identity(path) == python_executable_identity(str(path))


def test_shared_identity_import_does_not_load_http_server_and_legacy_export_matches():
    code = "from hermes_feishu_card.runtime_ownership import python_executable_identity; import sys; assert 'hermes_feishu_card.server' not in sys.modules; from hermes_feishu_card.server import python_executable_identity as old; assert old is python_executable_identity"
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
