from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
from typing import Any, Callable, Sequence

from .maintenance_store import ArtifactMetadata, MaintenancePaths, UpdateJob
from .maintenance_update import CommandResult, CommandRunner, run_command


RUNTIME_METADATA_NAME = "runtime.json"
PROVISION_TIMEOUT_SECONDS = 300.0
PROBE_TIMEOUT_SECONDS = 20.0
_PROBE_CODE = (
    "import json, pathlib, hermes_feishu_card; "
    "import hermes_feishu_card.maintenance_runner; "
    "print(json.dumps({'version': hermes_feishu_card.__version__, "
    "'location': str(pathlib.Path(hermes_feishu_card.__file__).resolve())}))"
)


@dataclass(frozen=True)
class MaintenanceRuntimeStatus:
    available: bool
    reason_code: str
    python_path: Path
    package_version: str
    package_location: Path | None
    manager: str
    artifact_sha256: str


@dataclass(frozen=True)
class LaunchResult:
    started: bool
    manager: str
    argv: tuple[str, ...]
    pid: int | None
    reason_code: str


def provision_runtime(
    paths: MaintenancePaths,
    artifact: ArtifactMetadata,
    *,
    hermes_root: Path,
    run: CommandRunner | None = None,
    host_python: Path | None = None,
    now: Callable[[], float] = time.time,
) -> MaintenanceRuntimeStatus:
    runner = run or run_command
    _prepare_runtime_directory(paths)
    venv_root = paths.runtime / "venv"
    python_path = _runtime_python(venv_root)
    if not python_path.is_file():
        create = runner(
            (
                str(host_python or Path(sys.executable)),
                "-m",
                "venv",
                "--clear",
                str(venv_root),
            ),
            PROVISION_TIMEOUT_SECONDS,
        )
        if create.timed_out or create.returncode != 0 or not python_path.is_file():
            return _runtime_unavailable(
                python_path,
                artifact,
                "runtime_create_failed",
            )
    install = runner(
        (
            str(python_path),
            "-I",
            "-m",
            "pip",
            "install",
            "--force-reinstall",
            str(artifact.wheel_path),
        ),
        PROVISION_TIMEOUT_SECONDS,
    )
    if install.timed_out or install.returncode != 0:
        return _runtime_unavailable(
            python_path,
            artifact,
            "runtime_install_failed",
        )
    status = inspect_runtime(
        paths,
        artifact,
        hermes_root=hermes_root,
        python_path=python_path,
        run=runner,
    )
    if not status.available:
        return status
    _atomic_runtime_metadata(
        paths.runtime / RUNTIME_METADATA_NAME,
        {
            "schema_version": 1,
            "python": str(status.python_path),
            "package_version": status.package_version,
            "package_location": str(status.package_location or ""),
            "artifact_sha256": artifact.sha256,
            "created_at": float(now()),
        },
    )
    return status


def inspect_runtime(
    paths: MaintenancePaths,
    artifact: ArtifactMetadata,
    *,
    hermes_root: Path,
    python_path: Path | None = None,
    run: CommandRunner | None = None,
) -> MaintenanceRuntimeStatus:
    runner = run or run_command
    selected_path = (
        Path(python_path).expanduser()
        if python_path is not None
        else _runtime_python(paths.runtime / "venv")
    )
    selected_python = Path(os.path.abspath(str(selected_path)))
    resolved_runtime = paths.runtime.expanduser().resolve(strict=False)
    resolved_hermes = Path(hermes_root).expanduser().resolve(strict=False)
    if not _is_below_lexical(selected_python, resolved_runtime) or _is_below(
        selected_python, resolved_hermes
    ):
        return _runtime_unavailable(
            selected_python,
            artifact,
            "runtime_not_independent",
        )
    if not selected_python.is_file():
        return _runtime_unavailable(
            selected_python,
            artifact,
            "runtime_python_missing",
        )
    probe = runner(
        (str(selected_python), "-I", "-c", _PROBE_CODE),
        PROBE_TIMEOUT_SECONDS,
    )
    if probe.timed_out or probe.returncode != 0:
        return _runtime_unavailable(
            selected_python,
            artifact,
            "runtime_probe_failed",
        )
    try:
        payload = json.loads(str(probe.stdout or "").strip())
    except json.JSONDecodeError:
        return _runtime_unavailable(
            selected_python,
            artifact,
            "runtime_probe_invalid",
        )
    if not isinstance(payload, dict):
        return _runtime_unavailable(
            selected_python,
            artifact,
            "runtime_probe_invalid",
        )
    version = str(payload.get("version") or "").strip()
    if version != artifact.version:
        return _runtime_unavailable(
            selected_python,
            artifact,
            "runtime_version_mismatch",
            package_version=version,
        )
    location_text = str(payload.get("location") or "").strip()
    if not location_text:
        return _runtime_unavailable(
            selected_python,
            artifact,
            "runtime_import_origin_invalid",
            package_version=version,
        )
    package_location = Path(location_text).expanduser().resolve(strict=False)
    if (
        not _is_below(package_location, resolved_runtime / "venv")
        or "site-packages" not in package_location.parts
    ):
        return _runtime_unavailable(
            selected_python,
            artifact,
            "runtime_import_origin_invalid",
            package_version=version,
            package_location=package_location,
        )
    return MaintenanceRuntimeStatus(
        available=True,
        reason_code="ready",
        python_path=selected_python,
        package_version=version,
        package_location=package_location,
        manager="independent",
        artifact_sha256=artifact.sha256,
    )


def launch_job(
    status: MaintenanceRuntimeStatus,
    job: UpdateJob,
    *,
    run: CommandRunner | None = None,
    systemd_user_available: Callable[[], bool] | None = None,
    detached_lifecycle_safe: Callable[[], bool] | None = None,
    popen: Callable[..., Any] = subprocess.Popen,
) -> LaunchResult:
    if not status.available:
        raise ValueError("maintenance runtime is unavailable")
    if status.package_version != job.artifact_version or (
        status.artifact_sha256 != job.artifact_sha256
    ):
        raise ValueError("maintenance runtime version mismatch")
    _validate_job_launch_path(job.path)
    runner_command = (
        str(status.python_path),
        "-I",
        "-m",
        "hermes_feishu_card.maintenance_runner",
        "--job",
        str(job.path),
    )
    available = systemd_user_available or _systemd_user_available
    if available():
        unit_hash = hashlib.sha256(job.job_id.encode("utf-8")).hexdigest()[:12]
        unit = f"hfc-maintenance-{unit_hash}.service"
        argv = (
            "systemd-run",
            "--user",
            "--unit",
            unit,
            "--collect",
            "--",
            *runner_command,
        )
        result = (run or run_command)(argv, 20.0)
        return LaunchResult(
            started=not result.timed_out and result.returncode == 0,
            manager="systemd-user",
            argv=tuple(argv),
            pid=None,
            reason_code=(
                "started"
                if not result.timed_out and result.returncode == 0
                else "systemd_start_failed"
            ),
        )

    lifecycle_safe = detached_lifecycle_safe or _detached_lifecycle_safe
    if sys.platform.startswith("linux") and not lifecycle_safe():
        return LaunchResult(
            started=False,
            manager="unavailable",
            argv=runner_command,
            pid=None,
            reason_code="independent_manager_unavailable",
        )

    kwargs: dict[str, object] = {
        "stdin": subprocess.DEVNULL,
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
        "shell": False,
        "close_fds": True,
        "env": _maintenance_environment(),
    }
    if os.name == "nt":
        kwargs["creationflags"] = (
            subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS
        )
    else:
        kwargs["start_new_session"] = True
    try:
        process = popen(list(runner_command), **kwargs)
    except (OSError, ValueError):
        return LaunchResult(
            started=False,
            manager="detached",
            argv=runner_command,
            pid=None,
            reason_code="detached_start_failed",
        )
    pid = getattr(process, "pid", None)
    valid_pid = pid if isinstance(pid, int) and not isinstance(pid, bool) and pid > 0 else None
    return LaunchResult(
        started=valid_pid is not None,
        manager="detached",
        argv=runner_command,
        pid=valid_pid,
        reason_code="started" if valid_pid is not None else "detached_start_failed",
    )


def _prepare_runtime_directory(paths: MaintenancePaths) -> None:
    for directory in (paths.root, paths.runtime):
        if directory.is_symlink():
            raise ValueError("maintenance runtime directory must not be a symlink")
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        directory.chmod(0o700)


def _runtime_python(venv_root: Path) -> Path:
    return (
        venv_root / "Scripts" / "python.exe"
        if os.name == "nt"
        else venv_root / "bin" / "python"
    )


def _runtime_unavailable(
    python_path: Path,
    artifact: ArtifactMetadata,
    reason_code: str,
    *,
    package_version: str = "",
    package_location: Path | None = None,
) -> MaintenanceRuntimeStatus:
    return MaintenanceRuntimeStatus(
        available=False,
        reason_code=reason_code,
        python_path=Path(python_path).resolve(strict=False),
        package_version=package_version,
        package_location=package_location,
        manager="unavailable",
        artifact_sha256=artifact.sha256,
    )


def _is_below(path: Path, parent: Path) -> bool:
    try:
        path.resolve(strict=False).relative_to(parent.resolve(strict=False))
        return True
    except ValueError:
        return False


def _is_below_lexical(path: Path, parent: Path) -> bool:
    try:
        Path(os.path.abspath(str(path))).relative_to(
            Path(os.path.abspath(str(parent)))
        )
        return True
    except ValueError:
        return False


def _atomic_runtime_metadata(path: Path, payload: dict[str, object]) -> None:
    if path.is_symlink():
        raise ValueError("runtime metadata must not be a symlink")
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=str(path.parent),
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            if hasattr(os, "fchmod"):
                os.fchmod(handle.fileno(), 0o600)
            json.dump(payload, handle, sort_keys=True, separators=(",", ":"))
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        if path.is_symlink():
            raise ValueError("runtime metadata must not be a symlink")
        os.replace(temporary, path)
        path.chmod(0o600)
    finally:
        temporary.unlink(missing_ok=True)


def _systemd_user_available() -> bool:
    if not sys.platform.startswith("linux"):
        return False
    if shutil.which("systemd-run") is None or shutil.which("systemctl") is None:
        return False
    try:
        result = subprocess.run(
            ["systemctl", "--user", "show-environment"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=3,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return result.returncode == 0


def _detached_lifecycle_safe() -> bool:
    """Linux requires a positively-owned external manager for update jobs."""
    return not sys.platform.startswith("linux")


def _validate_job_launch_path(path: Path) -> None:
    selected = Path(path).expanduser()
    if selected.is_symlink() or not selected.is_file():
        raise ValueError("maintenance job path is invalid")
    if os.name != "nt" and selected.stat().st_mode & 0o077:
        raise ValueError("maintenance job path is not private")


def _maintenance_environment() -> dict[str, str]:
    allowed = {
        "APPDATA",
        "HOME",
        "HERMES_FEISHU_CARD_STATE_DIR",
        "LANG",
        "LC_ALL",
        "LOCALAPPDATA",
        "PATH",
        "SYSTEMROOT",
        "TMP",
        "TMPDIR",
        "TEMP",
        "USER",
        "USERNAME",
        "WINDIR",
    }
    return {
        key: value
        for key, value in os.environ.items()
        if key in allowed and isinstance(value, str)
    }
