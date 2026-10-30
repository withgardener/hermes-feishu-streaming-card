import json
import os
from pathlib import Path
import stat

import pytest

from hermes_feishu_card.maintenance_process import (
    LaunchResult,
    MaintenanceRuntimeStatus,
    inspect_runtime,
    launch_job,
    provision_runtime,
)
from hermes_feishu_card.maintenance_store import (
    ArtifactMetadata,
    UpdateJob,
    maintenance_paths,
    stage_job_credentials,
)
from hermes_feishu_card.maintenance_update import CommandResult


@pytest.fixture
def artifact(tmp_path):
    wheel = tmp_path / "hermes_feishu_streaming_card-4.2.0-py3-none-any.whl"
    wheel.write_bytes(b"wheel")
    return ArtifactMetadata(
        schema_version=1,
        distribution="hermes-feishu-streaming-card",
        version="4.2.0",
        sha256="a" * 64,
        wheel_path=wheel,
        metadata_path=tmp_path / "artifact.json",
        source_kind="installer_spec",
        created_at=100.0,
    )


class ProvisionHarness:
    def __init__(self, paths):
        self.paths = paths
        self.commands = []
        self.pip_argv = ()
        self.python_path = (
            paths.runtime / "venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        )
        self.package_location = (
            paths.runtime
            / "venv"
            / "lib"
            / "python3.12"
            / "site-packages"
            / "hermes_feishu_card"
            / "__init__.py"
        )

    def __call__(self, argv, timeout):
        normalized = tuple(str(value) for value in argv)
        self.commands.append(normalized)
        if normalized[1:3] == ("-m", "venv"):
            self.python_path.parent.mkdir(parents=True, exist_ok=True)
            if self.python_path.is_symlink():
                self.python_path.unlink()
            self.python_path.write_text("#!python\n", encoding="utf-8")
            self.python_path.chmod(0o700)
            return CommandResult(normalized, 0, "", "")
        if normalized[1:4] == ("-I", "-m", "pip"):
            self.pip_argv = normalized
            self.package_location.parent.mkdir(parents=True, exist_ok=True)
            self.package_location.write_text("__version__='4.2.0'\n", encoding="utf-8")
            return CommandResult(normalized, 0, "", "")
        if normalized[1:3] == ("-I", "-c"):
            return CommandResult(
                normalized,
                0,
                json.dumps(
                    {
                        "version": "4.2.0",
                        "location": str(self.package_location),
                    }
                ),
                "",
            )
        raise AssertionError(f"unexpected command: {normalized}")


def test_provision_runtime_uses_private_venv_and_exact_wheel(
    tmp_path, artifact
):
    paths = maintenance_paths(tmp_path / "state")
    paths.root.mkdir(parents=True)
    paths.runtime.mkdir()
    harness = ProvisionHarness(paths)

    status = provision_runtime(
        paths,
        artifact,
        hermes_root=tmp_path / "hermes",
        run=harness,
        host_python=Path("/usr/bin/python3"),
        now=lambda: 200.0,
    )

    assert status.available is True
    assert status.package_version == artifact.version
    assert status.python_path == harness.python_path.absolute()
    assert status.package_location == harness.package_location.resolve(strict=False)
    assert "--clear" in harness.commands[0]
    assert "--no-deps" not in harness.pip_argv
    assert "--force-reinstall" in harness.pip_argv
    assert str(artifact.wheel_path) in harness.pip_argv
    metadata = paths.runtime / "runtime.json"
    assert json.loads(metadata.read_text())["artifact_sha256"] == "a" * 64
    if os.name != "nt":
        assert stat.S_IMODE(metadata.stat().st_mode) == 0o600


def test_inspect_runtime_accepts_standard_venv_python_symlink_outside_hermes(
    tmp_path, artifact
):
    paths = maintenance_paths(tmp_path / "state")
    paths.runtime.mkdir(parents=True)
    harness = ProvisionHarness(paths)
    harness.python_path.parent.mkdir(parents=True, exist_ok=True)
    host_python = tmp_path / "host-python"
    host_python.write_text("#!python\n", encoding="utf-8")
    harness.python_path.symlink_to(host_python)
    harness.package_location.parent.mkdir(parents=True, exist_ok=True)
    harness.package_location.write_text("__version__='4.2.0'\n", encoding="utf-8")

    status = inspect_runtime(
        paths,
        artifact,
        hermes_root=tmp_path / "hermes",
        python_path=harness.python_path,
        run=harness,
    )

    assert status.available is True
    assert status.python_path == harness.python_path.absolute()
    assert harness.python_path.is_symlink()


def test_inspect_runtime_rejects_python_inside_hermes(tmp_path, artifact):
    paths = maintenance_paths(tmp_path / "state")
    hermes_root = tmp_path / "hermes"
    python_path = hermes_root / "venv" / "bin" / "python"
    python_path.parent.mkdir(parents=True)
    python_path.write_text("#!python\n", encoding="utf-8")

    status = inspect_runtime(
        paths,
        artifact,
        hermes_root=hermes_root,
        python_path=python_path,
        run=lambda argv, timeout: pytest.fail("probe must not run"),
    )

    assert status.available is False
    assert status.reason_code == "runtime_not_independent"


def test_inspect_runtime_rejects_wrong_version_or_import_origin(tmp_path, artifact):
    paths = maintenance_paths(tmp_path / "state")
    python_path = paths.runtime / "venv" / "bin" / "python"
    python_path.parent.mkdir(parents=True)
    python_path.write_text("#!python\n", encoding="utf-8")

    def wrong_version(argv, timeout):
        return CommandResult(
            tuple(argv),
            0,
            json.dumps(
                {
                    "version": "4.1.4",
                    "location": str(
                        paths.runtime / "venv/lib/python3.12/site-packages/pkg.py"
                    ),
                }
            ),
            "",
        )

    assert (
        inspect_runtime(
            paths,
            artifact,
            hermes_root=tmp_path / "hermes",
            python_path=python_path,
            run=wrong_version,
        ).reason_code
        == "runtime_version_mismatch"
    )

    def wrong_origin(argv, timeout):
        return CommandResult(
            tuple(argv),
            0,
            json.dumps(
                {
                    "version": "4.2.0",
                    "location": str(tmp_path / "checkout/hermes_feishu_card/__init__.py"),
                }
            ),
            "",
        )

    assert (
        inspect_runtime(
            paths,
            artifact,
            hermes_root=tmp_path / "hermes",
            python_path=python_path,
            run=wrong_origin,
        ).reason_code
        == "runtime_import_origin_invalid"
    )


@pytest.fixture
def status(tmp_path):
    python_path = tmp_path / "state" / "runtime" / "venv" / "bin" / "python"
    python_path.parent.mkdir(parents=True)
    python_path.write_text("#!python\n", encoding="utf-8")
    return MaintenanceRuntimeStatus(
        available=True,
        reason_code="ready",
        python_path=python_path.resolve(strict=False),
        package_version="4.2.0",
        package_location=(
            python_path.parent.parent
            / "lib/python3.12/site-packages/hermes_feishu_card/__init__.py"
        ).resolve(strict=False),
        manager="independent",
        artifact_sha256="a" * 64,
    )


@pytest.fixture
def job(tmp_path):
    path = tmp_path / "state" / "jobs" / "job-1.json"
    path.parent.mkdir(parents=True)
    path.write_text("{}\n", encoding="utf-8")
    path.chmod(0o600)
    return UpdateJob(
        schema_version=1,
        job_id="job-1",
        path=path,
        phase="locking",
        hermes_root=tmp_path / "hermes",
        config_path=tmp_path / "config.yaml",
        env_file=None,
        profile_id="default",
        chat_id="oc_private",
        card_message_id="om_card",
        operator_hash="sha256:operator",
        pre_update_version="0.19.1",
        pre_update_head="b" * 40,
        target_fingerprint="c" * 64,
        artifact_version="4.2.0",
        artifact_sha256="a" * 64,
        artifact_path=tmp_path / "artifact.whl",
        attempts={},
        created_at=100.0,
        updated_at=100.0,
        result={},
    )


def test_launch_job_uses_systemd_user_when_available(status, job):
    calls = []

    def runner(argv, timeout):
        calls.append(tuple(argv))
        return CommandResult(tuple(argv), 0, "", "")

    launch = launch_job(
        status,
        job,
        run=runner,
        systemd_user_available=lambda: True,
    )

    assert isinstance(launch, LaunchResult)
    assert launch.started is True
    assert launch.manager == "systemd-user"
    assert launch.argv[:3] == ("systemd-run", "--user", "--unit")
    assert launch.argv[-6:] == (
        str(status.python_path),
        "-I",
        "-m",
        "hermes_feishu_card.maintenance_runner",
        "--job",
        str(job.path),
    )
    assert calls == [launch.argv]


def test_systemd_launch_never_places_proxy_value_in_argv(status, job):
    proxy_value = "http://127.0.0.1:7897"
    paths = maintenance_paths(job.path.parent.parent)
    staged = stage_job_credentials(
        paths,
        job_id=job.job_id,
        environment={"HTTPS_PROXY": proxy_value},
    )
    assert staged is not None

    launch = launch_job(
        status,
        job,
        run=lambda argv, timeout: CommandResult(tuple(argv), 0, "", ""),
        systemd_user_available=lambda: True,
    )

    assert all(proxy_value not in value for value in launch.argv)
    assert proxy_value not in job.path.read_text(encoding="utf-8")


class FakeProcess:
    pid = 4321


class PopenHarness:
    def __init__(self):
        self.argv = ()
        self.kwargs = {}

    def __call__(self, argv, **kwargs):
        self.argv = tuple(argv)
        self.kwargs = kwargs
        return FakeProcess()


def test_launch_job_detaches_without_shell(status, job):
    popen = PopenHarness()

    launch = launch_job(
        status,
        job,
        systemd_user_available=lambda: False,
        detached_lifecycle_safe=lambda: True,
        popen=popen,
    )

    assert launch.started is True
    assert launch.manager == "detached"
    assert launch.pid == 4321
    assert popen.kwargs["shell"] is False
    assert popen.kwargs["stdin"] is not None
    assert popen.kwargs["stdout"] is not None
    assert popen.kwargs["stderr"] is not None
    if os.name != "nt":
        assert popen.kwargs["start_new_session"] is True


def test_launch_job_refuses_unsafe_linux_detach(status, job, monkeypatch):
    monkeypatch.setattr("hermes_feishu_card.maintenance_process.sys.platform", "linux")
    popen = PopenHarness()

    launch = launch_job(
        status,
        job,
        systemd_user_available=lambda: False,
        popen=popen,
    )

    assert launch.started is False
    assert launch.manager == "unavailable"
    assert launch.reason_code == "independent_manager_unavailable"
    assert popen.argv == ()


def test_runtime_probe_imports_actual_maintenance_runner(tmp_path, artifact):
    paths = maintenance_paths(tmp_path / "state")
    python_path = paths.runtime / "venv" / "bin" / "python"
    python_path.parent.mkdir(parents=True)
    python_path.write_text("#!python\n", encoding="utf-8")
    package_location = (
        paths.runtime
        / "venv/lib/python3.12/site-packages/hermes_feishu_card/__init__.py"
    )

    def runner(argv, timeout):
        assert "hermes_feishu_card.maintenance_runner" in argv[-1]
        return CommandResult(
            tuple(argv),
            0,
            json.dumps({"version": "4.2.0", "location": str(package_location)}),
            "",
        )

    assert inspect_runtime(
        paths,
        artifact,
        hermes_root=tmp_path / "hermes",
        python_path=python_path,
        run=runner,
    ).available is True


def test_launch_job_refuses_unavailable_or_version_mismatched_runtime(status, job):
    unavailable = MaintenanceRuntimeStatus(
        **{**status.__dict__, "available": False, "reason_code": "missing"}
    )
    with pytest.raises(ValueError, match="maintenance runtime is unavailable"):
        launch_job(unavailable, job)

    mismatched = UpdateJob(
        **{**job.__dict__, "artifact_version": "4.1.4"}
    )
    with pytest.raises(ValueError, match="maintenance runtime version mismatch"):
        launch_job(status, mismatched)
