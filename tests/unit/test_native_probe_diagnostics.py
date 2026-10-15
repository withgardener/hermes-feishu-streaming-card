"""Source refusal diagnostics identify failures without exposing subprocess data."""
from __future__ import annotations

import subprocess
import tarfile

import pytest

from hermes_feishu_card.install import native_hooks


@pytest.mark.parametrize("failure,kind", [
    (subprocess.TimeoutExpired("PRIVATE_COMMAND", 3, output=b"PRIVATE_OUTPUT"), "timeout"),
    (subprocess.CalledProcessError(1, "PRIVATE_COMMAND", stderr=b"PRIVATE_SECRET"), "command_failed"),
    (FileNotFoundError("PRIVATE_PATH"), "unavailable"),
], ids=["timeout", "command", "missing"])
def test_git_head_failure_retains_closed_result_and_redacted_cause(tmp_path, monkeypatch, caplog, failure, kind):
    def fail(*args, **kwargs):
        raise failure
    monkeypatch.setattr(native_hooks, "_run_trusted_git", fail)
    assert native_hooks._git_head(tmp_path) == ""
    assert f"stage=git_head kind={kind}" in caplog.text
    assert "PRIVATE_" not in caplog.text


def test_git_status_failure_is_not_confused_with_commit_lookup(tmp_path, monkeypatch, caplog):
    monkeypatch.setattr(native_hooks, "_git_head", lambda root: native_hooks.FIXED_TAG_COMMIT)
    def fail(*args, **kwargs):
        raise subprocess.TimeoutExpired("PRIVATE_COMMAND", 5)
    monkeypatch.setattr(native_hooks, "_run_trusted_git", fail)
    assert native_hooks._git_source_state(tmp_path) == (native_hooks.FIXED_TAG_COMMIT, False)
    assert "stage=git_status kind=timeout" in caplog.text
    assert "PRIVATE_" not in caplog.text


@pytest.mark.parametrize("failure,kind", [
    (subprocess.TimeoutExpired("PRIVATE_COMMAND", 30), "timeout"),
    (tarfile.ReadError("PRIVATE_ARCHIVE"), "invalid_archive"),
    (ValueError("PRIVATE_EVIDENCE"), "invalid_evidence"),
], ids=["timeout", "archive", "evidence"])
def test_snapshot_failure_keeps_public_contract_and_all_capabilities_closed(tmp_path, monkeypatch, caplog, failure, kind):
    monkeypatch.setattr(native_hooks, "_git_source_state", lambda root: (native_hooks.FIXED_TAG_COMMIT, True))
    monkeypatch.setattr(native_hooks, "verify_provenance_slices", lambda *args, **kwargs: True)
    def fail(*args, **kwargs):
        raise failure
    monkeypatch.setattr(native_hooks, "_build_trusted_source_snapshot", fail)
    result = native_hooks.probe_native_hook_capabilities(
        tmp_path, expected_commit=native_hooks.FIXED_TAG_COMMIT,
        runtime_python=tmp_path / "never-executed-python",
    )
    assert result.reason_code == "source_commit_mismatch"
    assert not result.capabilities.available
    assert result.source_commit == native_hooks.FIXED_TAG_COMMIT
    assert f"stage=snapshot kind={kind}" in caplog.text
    assert "PRIVATE_" not in caplog.text


def test_unknown_diagnostic_input_cannot_be_logged(caplog):
    native_hooks._log_source_probe_failure("PRIVATE_STAGE", ValueError("PRIVATE_BODY"))
    assert "stage=unknown kind=invalid_evidence" in caplog.text
    assert "PRIVATE_" not in caplog.text


def test_head_budget_reaches_trusted_git_once_without_retry(tmp_path, monkeypatch):
    calls = []

    def fail(root, arguments, **kwargs):
        calls.append((root, arguments, kwargs))
        raise subprocess.TimeoutExpired("PRIVATE_COMMAND", kwargs["timeout"])

    monkeypatch.setattr(native_hooks, "_run_trusted_git", fail)
    assert native_hooks._git_head(tmp_path) == ""
    assert calls == [(tmp_path, ["rev-parse", "--verify", "HEAD"], {"timeout": 5.0})]


@pytest.mark.parametrize("output", [b"", b"invalid", b"f" * 39, b"g" * 40, b"\xff"],
                         ids=["empty", "text", "short", "nonhex", "nonascii"])
def test_invalid_head_cannot_supply_provenance(tmp_path, monkeypatch, output):
    def run(root, arguments, **kwargs):
        return subprocess.CompletedProcess(arguments, 0, stdout=output if arguments[0] == "rev-parse" else b"")

    monkeypatch.setattr(native_hooks, "_run_trusted_git", run)
    result = native_hooks.probe_native_hook_capabilities(
        tmp_path, expected_commit=native_hooks.FIXED_TAG_COMMIT,
        runtime_python=tmp_path / "never-executed-python",
    )
    assert result.reason_code == "source_commit_mismatch"
    assert result.source_commit == ""
    assert not result.capabilities.available


@pytest.mark.parametrize("failure", [
    subprocess.TimeoutExpired("PRIVATE_COMMAND", 5),
    subprocess.CalledProcessError(1, "PRIVATE_COMMAND", stderr=b"PRIVATE_SECRET"),
], ids=["timeout", "command"])
def test_head_failure_refuses_capabilities_without_retry(tmp_path, monkeypatch, failure):
    calls = []

    def run(root, arguments, **kwargs):
        calls.append((arguments[0], kwargs["timeout"]))
        if arguments[0] == "rev-parse":
            raise failure
        return subprocess.CompletedProcess(arguments, 0, stdout=b"")

    monkeypatch.setattr(native_hooks, "_run_trusted_git", run)
    result = native_hooks.probe_native_hook_capabilities(
        tmp_path, expected_commit=native_hooks.FIXED_TAG_COMMIT,
        runtime_python=tmp_path / "never-executed-python",
    )
    assert result.reason_code == "source_commit_mismatch"
    assert not result.capabilities.available
    assert calls == [("rev-parse", 5.0), ("status", 5)]


def test_nonempty_status_refuses_even_with_matching_commit(tmp_path, monkeypatch):
    def run(root, arguments, **kwargs):
        output = native_hooks.FIXED_TAG_COMMIT.encode() if arguments[0] == "rev-parse" else b" M tracked.py\n"
        return subprocess.CompletedProcess(arguments, 0, stdout=output)

    monkeypatch.setattr(native_hooks, "_run_trusted_git", run)
    result = native_hooks.probe_native_hook_capabilities(
        tmp_path, expected_commit=native_hooks.FIXED_TAG_COMMIT,
        runtime_python=tmp_path / "never-executed-python",
    )
    assert result.reason_code == "source_dirty"
    assert result.source_commit == native_hooks.FIXED_TAG_COMMIT
    assert not result.capabilities.available


@pytest.mark.parametrize("final_state,reason", [
    (("", True), "source_commit_mismatch"),
    (("1" * 40, True), "source_commit_mismatch"),
    ((native_hooks.FIXED_TAG_COMMIT, False), "source_dirty"),
    ((native_hooks.FIXED_TAG_COMMIT, True), "verified"),
], ids=["head-unavailable", "head-mismatch", "status-uninspectable-or-dirty", "matching"])
def test_final_source_recheck_is_required_after_plugin_evidence(monkeypatch, final_state, reason):
    import os
    from pathlib import Path
    from types import SimpleNamespace

    root = Path(os.environ["HFC_FIXED_TAG_SOURCE_ROOT"])
    calls = []

    def source_state(source_root):
        assert source_root == root
        calls.append("source")
        return (native_hooks.FIXED_TAG_COMMIT, True) if len(calls) == 1 else final_state

    def plugin_evidence(snapshot, runtime_python):
        assert calls == ["source"]
        calls.append("plugin")
        return SimpleNamespace(attestation_sha256="sha256:" + "1" * 64), "verified"

    monkeypatch.setattr(native_hooks, "_git_source_state", source_state)
    monkeypatch.setattr(native_hooks, "_produce_plugin_manager_evidence", plugin_evidence)
    result = native_hooks.probe_native_hook_capabilities(
        root, expected_commit=native_hooks.FIXED_TAG_COMMIT,
        runtime_python=root / "never-executed-python",
    )
    assert calls == ["source", "plugin", "source"]
    assert result.reason_code == reason
    if reason != "verified":
        assert not result.capabilities.available
    else:
        assert result.source_commit == native_hooks.FIXED_TAG_COMMIT
        assert len(result.source_digests) == 9


@pytest.mark.parametrize("stage,failure,reason", [
    ("rev-parse", subprocess.TimeoutExpired("PRIVATE_COMMAND", 5), "source_commit_mismatch"),
    ("rev-parse", subprocess.CalledProcessError(1, "PRIVATE_COMMAND"), "source_commit_mismatch"),
    ("status", subprocess.TimeoutExpired("PRIVATE_COMMAND", 5), "source_dirty"),
    ("status", subprocess.CalledProcessError(1, "PRIVATE_COMMAND"), "source_dirty"),
], ids=["head-timeout", "head-command", "status-timeout", "status-command"])
def test_final_git_failure_cannot_reuse_initial_verified_state(monkeypatch, caplog, stage, failure, reason):
    import os
    from pathlib import Path
    from types import SimpleNamespace

    root = Path(os.environ["HFC_FIXED_TAG_SOURCE_ROOT"])
    real_run = native_hooks._run_trusted_git
    final = False
    head_calls = []
    status_calls = []

    def run(source_root, arguments, **kwargs):
        if arguments[0] == "rev-parse":
            head_calls.append(kwargs["timeout"])
        elif arguments[0] == "status":
            status_calls.append(kwargs["timeout"])
        if final and arguments[0] == stage:
            raise failure
        return real_run(source_root, arguments, **kwargs)

    def plugin_evidence(snapshot, runtime_python):
        nonlocal final
        final = True
        return SimpleNamespace(attestation_sha256="sha256:" + "1" * 64), "verified"

    monkeypatch.setattr(native_hooks, "_run_trusted_git", run)
    monkeypatch.setattr(native_hooks, "_produce_plugin_manager_evidence", plugin_evidence)
    result = native_hooks.probe_native_hook_capabilities(
        root, expected_commit=native_hooks.FIXED_TAG_COMMIT,
        runtime_python=root / "never-executed-python",
    )
    assert head_calls == [5.0, 5.0]
    assert status_calls == [5, 5]
    assert result.reason_code == reason
    assert not result.capabilities.available
    assert ("stage=git_head" if stage == "rev-parse" else "stage=git_status") in caplog.text
    assert "PRIVATE_" not in caplog.text


def test_head_budget_reaches_isolated_subprocess_once(tmp_path, monkeypatch):
    calls = []

    def run(command, **kwargs):
        calls.append((command, kwargs))
        raise subprocess.TimeoutExpired("PRIVATE_COMMAND", kwargs["timeout"])

    monkeypatch.setattr(native_hooks.subprocess, "run", run)
    assert native_hooks._git_head(tmp_path) == ""
    assert len(calls) == 1
    command, kwargs = calls[0]
    assert command[0] == "/usr/bin/git"
    assert command[-3:] == ["rev-parse", "--verify", "HEAD"]
    assert "--no-replace-objects" in command
    assert "--no-optional-locks" in command
    assert kwargs["timeout"] == 5.0
    assert kwargs["env"]["GIT_OPTIONAL_LOCKS"] == "0"
    assert kwargs["env"]["GIT_CONFIG_NOSYSTEM"] == "1"
