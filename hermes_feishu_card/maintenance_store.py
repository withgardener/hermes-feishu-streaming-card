from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, field
from email.parser import Parser
import errno
import hashlib
import json
import os
from pathlib import Path
import secrets
import stat
import tempfile
import threading
import time
from typing import Callable, Iterator, Mapping
import zipfile

from .process import state_dir


ARTIFACT_SCHEMA_VERSION = 1
JOB_SCHEMA_VERSION = 2
DRAIN_SCHEMA_VERSION = 1
JOB_CREDENTIAL_SCHEMA_VERSION = 1
ARTIFACT_METADATA_NAME = "artifact.json"
UPDATE_PHASES = frozenset(
    {
        "locking",
        "draining",
        "restoring_hooks",
        "updating_hermes",
        "reinstalling_hfc",
        "starting_services",
        "verifying",
        "succeeded",
        "failed",
        "cancelled",
    }
)
TERMINAL_UPDATE_PHASES = frozenset({"succeeded", "failed", "cancelled"})
_SAFE_RESULT_KEYS = frozenset(
    {
        "actual_head",
        "actual_version",
        "card_delivery",
        "error_code",
        "hermes_head",
        "hermes_version",
        "hfc_version",
        "import_origin",
        "message",
        "recovery_boundary",
        "service_status",
        "status",
        "target_validation",
    }
)
_MAX_STRING_CHARS = 4096
_EXPECTED_DISTRIBUTION = "hermes-feishu-streaming-card"
PROXY_ENVIRONMENT_KEYS = frozenset(
    {
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "ALL_PROXY",
        "NO_PROXY",
        "http_proxy",
        "https_proxy",
        "all_proxy",
        "no_proxy",
    }
)
JOB_ENVIRONMENT_KEYS = frozenset(
    {
        "FEISHU_APP_ID",
        "FEISHU_APP_SECRET",
        *PROXY_ENVIRONMENT_KEYS,
    }
)


class MaintenanceRefused(ValueError):
    """Raised when maintenance evidence is incomplete or unsafe."""


class UpdateLockBusy(MaintenanceRefused):
    """Raised only when another owner currently holds the OS update lock."""


@dataclass(frozen=True)
class MaintenancePaths:
    root: Path
    runtime: Path
    artifacts: Path
    jobs: Path
    lock: Path
    drain: Path


@dataclass(frozen=True)
class UpdateLockLease:
    job_id: str
    path: Path
    _owner_token: str = field(repr=False)


_UPDATE_LEASE_GUARD = threading.Lock()
_ACTIVE_UPDATE_LEASES: dict[str, UpdateLockLease] = {}


@dataclass(frozen=True)
class ArtifactMetadata:
    schema_version: int
    distribution: str
    version: str
    sha256: str
    wheel_path: Path
    metadata_path: Path
    source_kind: str
    created_at: float


@dataclass(frozen=True)
class DrainLease:
    schema_version: int
    owner_id: str
    created_at: float
    expires_at: float


@dataclass(frozen=True)
class UpdateJob:
    schema_version: int
    job_id: str
    path: Path
    phase: str
    hermes_root: Path
    config_path: Path
    env_file: Path | None
    profile_id: str
    chat_id: str
    card_message_id: str
    operator_hash: str
    pre_update_version: str
    pre_update_head: str
    target_fingerprint: str
    artifact_version: str
    artifact_sha256: str
    artifact_path: Path
    attempts: dict[str, int]
    created_at: float
    updated_at: float
    result: dict[str, object]
    bot_id: str = "default"
    target_head: str = ""
    revision: int = 0
    pre_sidecar_pid: int = 0
    pre_runtime_id_hash: str = ""
    pre_runtime_sequence: int = 0
    hermes_home: Path | None = None


def maintenance_paths(root: Path | None = None) -> MaintenancePaths:
    selected = (
        Path(root).expanduser()
        if root is not None
        else state_dir().expanduser() / "maintenance"
    ).resolve(strict=False)
    return MaintenancePaths(
        root=selected,
        runtime=selected / "runtime",
        artifacts=selected / "artifacts",
        jobs=selected / "jobs",
        lock=selected / "update.lock",
        drain=selected / "drain.json",
    )


def reserve_drain_lease(
    paths: MaintenancePaths,
    *,
    owner_id: str,
    now: Callable[[], float] = time.time,
    ttl_seconds: float = 6 * 60 * 60,
) -> DrainLease:
    _prepare_paths(paths)
    owner = _bounded_string(owner_id, "drain lease owner")
    ttl = float(ttl_seconds)
    if not (0 < ttl <= 24 * 60 * 60):
        raise MaintenanceRefused("drain lease ttl is invalid")
    timestamp = float(now())
    with _acquire_job_lock(paths.drain):
        active = load_active_drain_lease(paths, now=lambda: timestamp)
        if active is not None:
            if active.owner_id != owner:
                raise MaintenanceRefused("maintenance drain already reserved")
            return active
        lease = DrainLease(
            schema_version=DRAIN_SCHEMA_VERSION,
            owner_id=owner,
            created_at=timestamp,
            expires_at=timestamp + ttl,
        )
        _atomic_write_json(paths.drain, _drain_payload(lease))
        return lease


def load_active_drain_lease(
    paths: MaintenancePaths,
    *,
    now: Callable[[], float] = time.time,
) -> DrainLease | None:
    path = paths.drain
    if path.is_symlink():
        raise MaintenanceRefused("drain lease must not be a symlink")
    if not path.exists():
        return None
    payload = _load_json_file(path, label="drain lease")
    if set(payload) != {"schema_version", "owner_id", "created_at", "expires_at"}:
        raise MaintenanceRefused("drain lease schema fields are invalid")
    if payload.get("schema_version") != DRAIN_SCHEMA_VERSION:
        raise MaintenanceRefused("drain lease schema unsupported")
    created_at = _safe_timestamp(payload.get("created_at"), "drain lease")
    expires_at = _safe_timestamp(payload.get("expires_at"), "drain lease")
    if expires_at <= created_at:
        raise MaintenanceRefused("drain lease expiry is invalid")
    lease = DrainLease(
        schema_version=DRAIN_SCHEMA_VERSION,
        owner_id=_required_string(payload, "owner_id", "drain lease"),
        created_at=created_at,
        expires_at=expires_at,
    )
    return lease if lease.expires_at > float(now()) else None


def require_drain_lease(
    paths: MaintenancePaths,
    *,
    owner_id: str,
    now: Callable[[], float] = time.time,
) -> DrainLease:
    lease = load_active_drain_lease(paths, now=now)
    if lease is None:
        raise MaintenanceRefused("maintenance drain lease is unavailable")
    if lease.owner_id != _bounded_string(owner_id, "drain lease owner"):
        raise MaintenanceRefused("drain lease owner mismatch")
    return lease


def release_drain_lease(paths: MaintenancePaths, *, owner_id: str) -> bool:
    owner = _bounded_string(owner_id, "drain lease owner")
    if not paths.root.exists():
        return False
    _prepare_paths(paths)
    with _acquire_job_lock(paths.drain):
        lease = load_active_drain_lease(paths, now=lambda: 0.0)
        if lease is None or lease.owner_id != owner:
            return False
        if paths.drain.is_symlink():
            raise MaintenanceRefused("drain lease must not be a symlink")
        paths.drain.unlink()
        return True


def stage_job_credentials(
    paths: MaintenancePaths,
    *,
    job_id: str,
    environment: Mapping[str, str],
) -> Path | None:
    selected_job_id = _safe_job_id(job_id)
    values = sanitize_job_environment(environment)
    if not values:
        return None
    _prepare_paths(paths)
    path = paths.jobs / f"{selected_job_id}.credentials.json"
    if path.exists() or path.is_symlink():
        raise MaintenanceRefused("job credential snapshot already exists")
    _atomic_write_json(
        path,
        {
            "schema_version": JOB_CREDENTIAL_SCHEMA_VERSION,
            "job_id": selected_job_id,
            "environment": values,
        },
    )
    return path


def load_job_credentials(paths: MaintenancePaths, *, job_id: str) -> dict[str, str]:
    selected_job_id = _safe_job_id(job_id)
    path = paths.jobs / f"{selected_job_id}.credentials.json"
    if not path.exists() and not path.is_symlink():
        return {}
    if path.is_symlink():
        raise MaintenanceRefused("job credential snapshot must not be a symlink")
    _require_private_file(path, "job credential snapshot")
    payload = _load_json_file(path, label="job credential snapshot")
    if set(payload) != {"schema_version", "job_id", "environment"}:
        raise MaintenanceRefused("job credential snapshot schema fields are invalid")
    if payload.get("schema_version") != JOB_CREDENTIAL_SCHEMA_VERSION:
        raise MaintenanceRefused("job credential snapshot schema unsupported")
    if payload.get("job_id") != selected_job_id:
        raise MaintenanceRefused("job credential snapshot owner mismatch")
    raw_environment = payload.get("environment")
    if not isinstance(raw_environment, dict) or not raw_environment:
        raise MaintenanceRefused("job credential snapshot is invalid")
    values: dict[str, str] = {}
    for key, value in raw_environment.items():
        if key not in JOB_ENVIRONMENT_KEYS:
            raise MaintenanceRefused("job credential snapshot key is invalid")
        values[key] = _bounded_string(value, "job credential value")
    return values


def sanitize_job_environment(
    environment: Mapping[str, str],
) -> dict[str, str]:
    return {
        key: value
        for key, value in environment.items()
        if key in JOB_ENVIRONMENT_KEYS
        and isinstance(value, str)
        and value.strip()
    }


def consume_job_credentials(paths: MaintenancePaths, *, job_id: str) -> dict[str, str]:
    values = load_job_credentials(paths, job_id=job_id)
    if values:
        discard_job_credentials(paths, job_id=job_id)
    return values


def discard_job_credentials(paths: MaintenancePaths, *, job_id: str) -> bool:
    selected_job_id = _safe_job_id(job_id)
    path = paths.jobs / f"{selected_job_id}.credentials.json"
    if path.is_symlink():
        raise MaintenanceRefused("job credential snapshot must not be a symlink")
    try:
        path.unlink()
        return True
    except FileNotFoundError:
        return False


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def stage_wheel_artifact(
    paths: MaintenancePaths,
    wheel_path: Path,
    *,
    expected_version: str,
    source_kind: str = "unknown",
    now: Callable[[], float] = time.time,
) -> ArtifactMetadata:
    _prepare_paths(paths)
    source = Path(wheel_path).expanduser()
    if source.is_symlink():
        raise MaintenanceRefused("artifact wheel must not be a symlink")
    if not source.is_file():
        raise MaintenanceRefused("artifact wheel is missing")
    distribution, version = _wheel_identity(source)
    if _normalized_distribution(distribution) != _normalized_distribution(
        _EXPECTED_DISTRIBUTION
    ):
        raise MaintenanceRefused("artifact distribution mismatch")
    if version != _bounded_string(expected_version, "artifact expected version"):
        raise MaintenanceRefused("artifact version mismatch")
    safe_source_kind = _bounded_string(source_kind, "artifact source kind")
    destination = paths.artifacts / source.name
    _atomic_copy(source, destination)
    digest = file_sha256(destination)
    created_at = float(now())
    metadata_path = paths.artifacts / ARTIFACT_METADATA_NAME
    payload = {
        "schema_version": ARTIFACT_SCHEMA_VERSION,
        "distribution": _EXPECTED_DISTRIBUTION,
        "version": version,
        "sha256": digest,
        "wheel_filename": destination.name,
        "source_kind": safe_source_kind,
        "created_at": created_at,
    }
    _atomic_write_json(metadata_path, payload)
    return ArtifactMetadata(
        schema_version=ARTIFACT_SCHEMA_VERSION,
        distribution=_EXPECTED_DISTRIBUTION,
        version=version,
        sha256=digest,
        wheel_path=destination.resolve(strict=False),
        metadata_path=metadata_path.resolve(strict=False),
        source_kind=safe_source_kind,
        created_at=created_at,
    )


def load_verified_artifact(
    paths: MaintenancePaths,
    *,
    expected_version: str | None = None,
) -> ArtifactMetadata:
    _prepare_paths(paths)
    metadata_path = paths.artifacts / ARTIFACT_METADATA_NAME
    payload = _load_json_file(metadata_path, label="artifact metadata")
    if payload.get("schema_version") != ARTIFACT_SCHEMA_VERSION:
        raise MaintenanceRefused("artifact metadata schema unsupported")
    distribution = _required_string(payload, "distribution", "artifact metadata")
    version = _required_string(payload, "version", "artifact metadata")
    digest = _required_string(payload, "sha256", "artifact metadata")
    wheel_filename = _required_string(
        payload, "wheel_filename", "artifact metadata"
    )
    source_kind = _required_string(payload, "source_kind", "artifact metadata")
    created_at = _safe_timestamp(payload.get("created_at"), "artifact metadata")
    if Path(wheel_filename).name != wheel_filename:
        raise MaintenanceRefused("artifact wheel filename is invalid")
    if _normalized_distribution(distribution) != _normalized_distribution(
        _EXPECTED_DISTRIBUTION
    ):
        raise MaintenanceRefused("artifact distribution mismatch")
    if expected_version is not None and version != expected_version:
        raise MaintenanceRefused("artifact version mismatch")
    wheel_path = paths.artifacts / wheel_filename
    if wheel_path.is_symlink() or not wheel_path.is_file():
        raise MaintenanceRefused("artifact wheel is missing")
    if file_sha256(wheel_path) != digest:
        raise MaintenanceRefused("artifact hash mismatch")
    wheel_distribution, wheel_version = _wheel_identity(wheel_path)
    if _normalized_distribution(wheel_distribution) != _normalized_distribution(
        distribution
    ):
        raise MaintenanceRefused("artifact distribution mismatch")
    if wheel_version != version:
        raise MaintenanceRefused("artifact version mismatch")
    return ArtifactMetadata(
        schema_version=ARTIFACT_SCHEMA_VERSION,
        distribution=distribution,
        version=version,
        sha256=digest,
        wheel_path=wheel_path.resolve(strict=False),
        metadata_path=metadata_path.resolve(strict=False),
        source_kind=source_kind,
        created_at=created_at,
    )


def create_job(
    paths: MaintenancePaths,
    *,
    hermes_root: Path,
    hermes_home: Path | None = None,
    config_path: Path,
    env_file: Path | None,
    profile_id: str,
    chat_id: str,
    card_message_id: str,
    operator_hash: str,
    pre_update_version: str,
    pre_update_head: str,
    target_fingerprint: str,
    target_head: str,
    artifact: ArtifactMetadata,
    pre_sidecar_pid: int = 0,
    pre_runtime_id_hash: str = "",
    pre_runtime_sequence: int = 0,
    bot_id: str = "default",
    job_id: str | None = None,
    now: Callable[[], float] = time.time,
) -> UpdateJob:
    _prepare_paths(paths)
    verified_artifact = load_verified_artifact(
        paths, expected_version=artifact.version
    )
    if verified_artifact.sha256 != artifact.sha256:
        raise MaintenanceRefused("artifact hash mismatch")
    selected_job_id = _safe_job_id(
        job_id if job_id is not None else secrets.token_urlsafe(18)
    )
    job_path = paths.jobs / f"{selected_job_id}.json"
    if job_path.exists() or job_path.is_symlink():
        raise MaintenanceRefused("job id collision")
    timestamp = float(now())
    job = UpdateJob(
        schema_version=JOB_SCHEMA_VERSION,
        job_id=selected_job_id,
        path=job_path.resolve(strict=False),
        phase="locking",
        hermes_root=_absolute_path(hermes_root, "Hermes root"),
        hermes_home=_absolute_path(hermes_home, "Hermes home") if hermes_home is not None else None,
        config_path=_absolute_path(config_path, "config path"),
        env_file=(
            _absolute_path(env_file, "env file") if env_file is not None else None
        ),
        profile_id=_bounded_string(profile_id, "profile id"),
        chat_id=_bounded_string(chat_id, "chat id"),
        card_message_id=_bounded_string(card_message_id, "card message id"),
        operator_hash=_bounded_string(operator_hash, "operator hash"),
        pre_update_version=_bounded_string(
            pre_update_version, "pre-update version"
        ),
        pre_update_head=_bounded_string(pre_update_head, "pre-update head"),
        target_fingerprint=_bounded_string(
            target_fingerprint, "target fingerprint"
        ),
        artifact_version=verified_artifact.version,
        artifact_sha256=verified_artifact.sha256,
        artifact_path=verified_artifact.wheel_path,
        attempts={},
        created_at=timestamp,
        updated_at=timestamp,
        result={},
        bot_id=_bounded_string(bot_id, "bot id"),
        target_head=_commit_id(target_head, "target head"),
        revision=0,
        pre_sidecar_pid=_safe_nonnegative_int(pre_sidecar_pid, "pre-sidecar pid"),
        pre_runtime_id_hash=_optional_sha256(
            pre_runtime_id_hash, "pre-runtime id hash"
        ),
        pre_runtime_sequence=_safe_nonnegative_int(
            pre_runtime_sequence, "pre-runtime sequence"
        ),
    )
    _atomic_write_json(job.path, _job_payload(job))
    return job


def load_job(path: Path, *, require_private: bool = True) -> UpdateJob:
    selected = Path(path).expanduser()
    if selected.is_symlink():
        raise MaintenanceRefused("job path must not be a symlink")
    if not selected.is_file():
        raise MaintenanceRefused("job file is missing")
    if require_private:
        _require_private_file(selected, "job file")
    payload = _load_json_file(selected, label="job")
    expected_keys = {
        "schema_version",
        "job_id",
        "phase",
        "hermes_root",
        "config_path",
        "env_file",
        "profile_id",
        "chat_id",
        "card_message_id",
        "operator_hash",
        "pre_update_version",
        "pre_update_head",
        "target_fingerprint",
        "target_head",
        "artifact_version",
        "artifact_sha256",
        "artifact_path",
        "attempts",
        "created_at",
        "updated_at",
        "result",
        "bot_id",
        "revision",
        "pre_sidecar_pid",
        "pre_runtime_id_hash",
        "pre_runtime_sequence",
    }
    if "hermes_home" in payload:
        expected_keys.add("hermes_home")
    if set(payload) != expected_keys:
        raise MaintenanceRefused("job schema fields are invalid")
    if payload.get("schema_version") != JOB_SCHEMA_VERSION:
        raise MaintenanceRefused("job schema unsupported")
    job_id = _required_string(payload, "job_id", "job")
    if selected.name != f"{job_id}.json":
        raise MaintenanceRefused("job path does not match job id")
    phase = _required_string(payload, "phase", "job")
    if phase not in UPDATE_PHASES:
        raise MaintenanceRefused("job phase is invalid")
    attempts = _safe_attempts(payload.get("attempts"))
    result = _safe_result(payload.get("result"))
    env_value = payload.get("env_file")
    if env_value is not None and not isinstance(env_value, str):
        raise MaintenanceRefused("job env file is invalid")
    return UpdateJob(
        schema_version=JOB_SCHEMA_VERSION,
        job_id=job_id,
        path=selected.resolve(strict=False),
        phase=phase,
        hermes_root=_serialized_absolute_path(payload, "hermes_root"),
        hermes_home=_serialized_absolute_path(payload, "hermes_home") if "hermes_home" in payload else None,
        config_path=_serialized_absolute_path(payload, "config_path"),
        env_file=(
            _absolute_path(Path(env_value), "env file") if env_value else None
        ),
        profile_id=_required_string(payload, "profile_id", "job"),
        chat_id=_required_string(payload, "chat_id", "job"),
        card_message_id=_required_string(payload, "card_message_id", "job"),
        operator_hash=_required_string(payload, "operator_hash", "job"),
        pre_update_version=_required_string(
            payload, "pre_update_version", "job"
        ),
        pre_update_head=_required_string(payload, "pre_update_head", "job"),
        target_fingerprint=_required_string(
            payload, "target_fingerprint", "job"
        ),
        artifact_version=_required_string(payload, "artifact_version", "job"),
        artifact_sha256=_required_string(payload, "artifact_sha256", "job"),
        artifact_path=_serialized_absolute_path(payload, "artifact_path"),
        attempts=attempts,
        created_at=_safe_timestamp(payload.get("created_at"), "job"),
        updated_at=_safe_timestamp(payload.get("updated_at"), "job"),
        result=result,
        bot_id=_required_string(payload, "bot_id", "job"),
        target_head=_commit_id(
            _required_string(payload, "target_head", "job"), "target head"
        ),
        revision=_safe_revision(payload.get("revision")),
        pre_sidecar_pid=_safe_nonnegative_int(
            payload.get("pre_sidecar_pid"), "pre-sidecar pid"
        ),
        pre_runtime_id_hash=_optional_sha256(
            payload.get("pre_runtime_id_hash"), "pre-runtime id hash"
        ),
        pre_runtime_sequence=_safe_nonnegative_int(
            payload.get("pre_runtime_sequence"), "pre-runtime sequence"
        ),
    )


def transition_job(
    path: Path,
    *,
    expected_phase: str,
    phase: str,
    result: Mapping[str, object] | None = None,
    now: Callable[[], float] = time.time,
) -> UpdateJob:
    if phase not in UPDATE_PHASES:
        raise MaintenanceRefused("job phase is invalid")
    with _acquire_job_lock(Path(path)):
        current = load_job(path)
        if current.phase != expected_phase:
            raise MaintenanceRefused("job phase changed")
        attempts = dict(current.attempts)
        attempts[phase] = attempts.get(phase, 0) + 1
        safe_result = _safe_result(
            dict(result) if result is not None else current.result
        )
        updated = UpdateJob(
            **{
                **current.__dict__,
                "phase": phase,
                "attempts": attempts,
                "updated_at": float(now()),
                "result": safe_result,
                "revision": current.revision + 1,
            }
        )
        _atomic_write_json(current.path, _job_payload(updated))
        return updated


def discard_unstarted_job(path: Path) -> bool:
    selected = Path(path).expanduser()
    with _acquire_job_lock(selected):
        current = load_job(selected)
        if (
            current.phase != "locking"
            or current.revision != 0
            or current.attempts
            or current.result
        ):
            raise MaintenanceRefused("started maintenance job cannot be discarded")
        selected.unlink()
        return True


@contextmanager
def acquire_update_lock(
    paths: MaintenancePaths,
    *,
    job_id: str,
) -> Iterator[UpdateLockLease]:
    _prepare_paths(paths)
    safe_job_id = _bounded_string(job_id, "job id")
    descriptor = _open_private_lock_file(paths.lock, "update lock")
    locked = False
    lease: UpdateLockLease | None = None
    try:
        if os.name == "nt":
            import msvcrt

            try:
                os.lseek(descriptor, 0, os.SEEK_SET)
                msvcrt.locking(descriptor, msvcrt.LK_NBLCK, 1)
            except OSError as exc:
                if _is_update_lock_contention(exc):
                    raise UpdateLockBusy("update already in progress") from exc
                raise
        else:
            import fcntl

            try:
                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError as exc:
                if _is_update_lock_contention(exc):
                    raise UpdateLockBusy("update already in progress") from exc
                raise
        locked = True
        os.fchmod(descriptor, 0o600) if hasattr(os, "fchmod") else None
        os.ftruncate(descriptor, 0)
        os.write(descriptor, (safe_job_id + "\n").encode("utf-8"))
        os.fsync(descriptor)
        owner_token = secrets.token_urlsafe(32)
        lease = UpdateLockLease(
            job_id=safe_job_id,
            path=paths.lock.resolve(strict=False),
            _owner_token=owner_token,
        )
        with _UPDATE_LEASE_GUARD:
            _ACTIVE_UPDATE_LEASES[owner_token] = lease
        yield lease
    finally:
        if lease is not None:
            with _UPDATE_LEASE_GUARD:
                if _ACTIVE_UPDATE_LEASES.get(lease._owner_token) is lease:
                    _ACTIVE_UPDATE_LEASES.pop(lease._owner_token, None)
        if locked:
            try:
                if os.name == "nt":
                    import msvcrt

                    os.lseek(descriptor, 0, os.SEEK_SET)
                    msvcrt.locking(descriptor, msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl

                    fcntl.flock(descriptor, fcntl.LOCK_UN)
            except OSError:
                pass
        os.close(descriptor)


def require_update_lock_lease(
    paths: MaintenancePaths,
    *,
    job_id: str,
    lease: UpdateLockLease,
) -> UpdateLockLease:
    expected_job_id = _bounded_string(job_id, "job id")
    expected_path = paths.lock.resolve(strict=False)
    if not isinstance(lease, UpdateLockLease):
        raise MaintenanceRefused("update lock lease is invalid")
    with _UPDATE_LEASE_GUARD:
        current = _ACTIVE_UPDATE_LEASES.get(lease._owner_token)
        valid = (
            current is lease
            and lease.job_id == expected_job_id
            and lease.path == expected_path
        )
    if not valid:
        raise MaintenanceRefused("update lock lease is not active")
    return lease


def _is_update_lock_contention(exc: OSError) -> bool:
    return isinstance(exc, BlockingIOError) or exc.errno in {
        errno.EACCES,
        errno.EAGAIN,
        getattr(errno, "EWOULDBLOCK", errno.EAGAIN),
    }


@contextmanager
def _acquire_job_lock(path: Path) -> Iterator[Path]:
    selected = Path(path).expanduser()
    lock_path = selected.with_suffix(selected.suffix + ".lock")
    descriptor = _open_private_lock_file(lock_path, "job lock")
    try:
        if os.name == "nt":
            import msvcrt

            if os.fstat(descriptor).st_size == 0:
                os.write(descriptor, b"\0")
            os.lseek(descriptor, 0, os.SEEK_SET)
            msvcrt.locking(descriptor, msvcrt.LK_LOCK, 1)
        else:
            import fcntl

            fcntl.flock(descriptor, fcntl.LOCK_EX)
        yield lock_path
    finally:
        try:
            if os.name == "nt":
                import msvcrt

                os.lseek(descriptor, 0, os.SEEK_SET)
                msvcrt.locking(descriptor, msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(descriptor, fcntl.LOCK_UN)
        except OSError:
            pass
        os.close(descriptor)


def _open_private_lock_file(path: Path, label: str) -> int:
    if path.is_symlink():
        raise MaintenanceRefused(f"{label} must not be a symlink")
    flags = os.O_RDWR | os.O_CREAT
    flags |= getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags, 0o600)
    except OSError as exc:
        raise MaintenanceRefused(f"{label} is unavailable") from exc
    try:
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode):
            raise MaintenanceRefused(f"{label} must be a regular file")
        getuid = getattr(os, "getuid", None)
        if callable(getuid) and info.st_uid != getuid():
            raise MaintenanceRefused(f"{label} owner is invalid")
        if hasattr(os, "fchmod"):
            os.fchmod(descriptor, 0o600)
    except Exception:
        os.close(descriptor)
        raise
    return descriptor


def prune_jobs(
    paths: MaintenancePaths,
    *,
    now: float | None = None,
    max_terminal: int = 5,
    max_age_seconds: float = 7 * 24 * 60 * 60,
) -> None:
    _prepare_paths(paths)
    if max_terminal < 0:
        raise ValueError("max_terminal must be non-negative")
    current_time = time.time() if now is None else float(now)
    terminal: list[UpdateJob] = []
    jobs_by_id: dict[str, UpdateJob] = {}
    for path in paths.jobs.glob("*.json"):
        if path.name.endswith(".credentials.json"):
            continue
        try:
            job = load_job(path)
        except MaintenanceRefused:
            continue
        jobs_by_id[job.job_id] = job
        if job.phase in TERMINAL_UPDATE_PHASES:
            terminal.append(job)
    for credential_path in paths.jobs.glob("*.credentials.json"):
        job_id = credential_path.name[: -len(".credentials.json")]
        job = jobs_by_id.get(job_id)
        if job is None or job.phase in TERMINAL_UPDATE_PHASES:
            _unlink_regular_job(credential_path)
    terminal.sort(key=lambda item: (item.updated_at, item.job_id), reverse=True)
    retained = 0
    for job in terminal:
        expired = current_time - job.updated_at > max_age_seconds
        over_capacity = retained >= max_terminal
        if expired or over_capacity:
            _unlink_regular_job(job.path)
        else:
            retained += 1


def _prepare_paths(paths: MaintenancePaths) -> None:
    configured_state = state_dir().expanduser()
    default_maintenance_root = (configured_state / "maintenance").resolve(
        strict=False
    )
    if paths.root == default_maintenance_root:
        if configured_state.is_symlink():
            raise MaintenanceRefused("state directory must not be a symlink")
        configured_state.mkdir(parents=True, exist_ok=True, mode=0o700)
        if not configured_state.is_dir():
            raise MaintenanceRefused("state directory is not a directory")
        try:
            configured_state.chmod(0o700)
        except OSError as exc:
            raise MaintenanceRefused(
                "state directory permissions could not be secured"
            ) from exc
    for directory in (paths.root, paths.runtime, paths.artifacts, paths.jobs):
        if directory.is_symlink():
            raise MaintenanceRefused("maintenance directory must not be a symlink")
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        if not directory.is_dir():
            raise MaintenanceRefused("maintenance path is not a directory")
        try:
            directory.chmod(0o700)
        except OSError as exc:
            raise MaintenanceRefused(
                "maintenance directory permissions could not be secured"
            ) from exc


def _wheel_identity(path: Path) -> tuple[str, str]:
    try:
        with zipfile.ZipFile(path) as archive:
            candidates = [
                name
                for name in archive.namelist()
                if name.endswith(".dist-info/METADATA")
                and "/" not in name[: -len("/METADATA")].split(".dist-info", 1)[0]
            ]
            if len(candidates) != 1:
                raise MaintenanceRefused("artifact metadata is invalid")
            contents = archive.read(candidates[0]).decode("utf-8")
    except (OSError, UnicodeDecodeError, zipfile.BadZipFile, KeyError) as exc:
        raise MaintenanceRefused("artifact wheel is invalid") from exc
    metadata = Parser().parsestr(contents)
    distribution = str(metadata.get("Name") or "").strip()
    version = str(metadata.get("Version") or "").strip()
    if not distribution or not version:
        raise MaintenanceRefused("artifact metadata is invalid")
    return distribution, version


def _normalized_distribution(value: str) -> str:
    return value.strip().lower().replace("_", "-").replace(".", "-")


def _atomic_copy(source: Path, destination: Path) -> None:
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{destination.name}.", suffix=".tmp", dir=str(destination.parent)
    )
    temporary = Path(temporary_name)
    try:
        with source.open("rb") as reader, os.fdopen(descriptor, "wb") as writer:
            if hasattr(os, "fchmod"):
                os.fchmod(writer.fileno(), 0o600)
            for chunk in iter(lambda: reader.read(1024 * 1024), b""):
                writer.write(chunk)
            writer.flush()
            os.fsync(writer.fileno())
        if destination.is_symlink():
            raise MaintenanceRefused("artifact destination must not be a symlink")
        os.replace(temporary, destination)
        destination.chmod(0o600)
    finally:
        temporary.unlink(missing_ok=True)


def _atomic_write_json(path: Path, payload: Mapping[str, object]) -> None:
    if path.is_symlink():
        raise MaintenanceRefused("maintenance file must not be a symlink")
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent)
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
            raise MaintenanceRefused("maintenance file must not be a symlink")
        os.replace(temporary, path)
        path.chmod(0o600)
    finally:
        temporary.unlink(missing_ok=True)


def _load_json_file(path: Path, *, label: str) -> dict[str, object]:
    if path.is_symlink():
        raise MaintenanceRefused(f"{label} must not be a symlink")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise MaintenanceRefused(f"{label} is invalid") from exc
    if not isinstance(data, dict):
        raise MaintenanceRefused(f"{label} is invalid")
    return data


def _require_private_file(path: Path, label: str) -> None:
    if os.name == "nt":
        return
    try:
        info = path.stat()
    except OSError as exc:
        raise MaintenanceRefused(f"{label} is unavailable") from exc
    if not stat.S_ISREG(info.st_mode):
        raise MaintenanceRefused(f"{label} must be a regular file")
    if stat.S_IMODE(info.st_mode) & 0o077:
        raise MaintenanceRefused(f"{label} permissions are not private")
    getuid = getattr(os, "getuid", None)
    if callable(getuid) and info.st_uid != getuid():
        raise MaintenanceRefused(f"{label} owner is invalid")


def _required_string(
    payload: Mapping[str, object],
    key: str,
    label: str,
) -> str:
    value = payload.get(key)
    if not isinstance(value, str):
        raise MaintenanceRefused(f"{label} {key} is invalid")
    return _bounded_string(value, f"{label} {key}")


def _bounded_string(value: object, label: str) -> str:
    if not isinstance(value, str):
        raise MaintenanceRefused(f"{label} is invalid")
    normalized = value.strip()
    if not normalized or len(normalized) > _MAX_STRING_CHARS or "\x00" in normalized:
        raise MaintenanceRefused(f"{label} is invalid")
    return normalized


def _commit_id(value: object, label: str) -> str:
    normalized = _bounded_string(value, label).lower()
    if len(normalized) not in {40, 64} or any(
        character not in "0123456789abcdef" for character in normalized
    ):
        raise MaintenanceRefused(f"{label} is invalid")
    return normalized


def _safe_job_id(value: object) -> str:
    selected = _bounded_string(value, "job id")
    if not all(character.isalnum() or character in {"-", "_"} for character in selected):
        raise MaintenanceRefused("job id is invalid")
    return selected


def _safe_revision(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not (0 <= value <= 10_000):
        raise MaintenanceRefused("job revision is invalid")
    return value


def _safe_nonnegative_int(value: object, label: str) -> int:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or not 0 <= value <= 2**63 - 1
    ):
        raise MaintenanceRefused(f"{label} is invalid")
    return value


def _optional_sha256(value: object, label: str) -> str:
    if value == "":
        return ""
    if not isinstance(value, str):
        raise MaintenanceRefused(f"{label} is invalid")
    normalized = value.strip().lower()
    if len(normalized) != 64 or any(
        character not in "0123456789abcdef" for character in normalized
    ):
        raise MaintenanceRefused(f"{label} is invalid")
    return normalized


def _absolute_path(value: Path, label: str) -> Path:
    selected = Path(value).expanduser()
    if not selected.is_absolute():
        selected = selected.resolve(strict=False)
    resolved = selected.resolve(strict=False)
    if "\x00" in str(resolved):
        raise MaintenanceRefused(f"{label} is invalid")
    return resolved


def _serialized_absolute_path(
    payload: Mapping[str, object],
    key: str,
) -> Path:
    value = _required_string(payload, key, "job")
    path = Path(value).expanduser()
    if not path.is_absolute():
        raise MaintenanceRefused(f"job {key} must be absolute")
    return path.resolve(strict=False)


def _safe_timestamp(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise MaintenanceRefused(f"{label} timestamp is invalid")
    timestamp = float(value)
    if timestamp < 0 or timestamp == float("inf") or timestamp != timestamp:
        raise MaintenanceRefused(f"{label} timestamp is invalid")
    return timestamp


def _safe_attempts(value: object) -> dict[str, int]:
    if not isinstance(value, dict):
        raise MaintenanceRefused("job attempts are invalid")
    attempts: dict[str, int] = {}
    for key, count in value.items():
        if key not in UPDATE_PHASES:
            raise MaintenanceRefused("job attempts are invalid")
        if isinstance(count, bool) or not isinstance(count, int) or not (0 <= count <= 9):
            raise MaintenanceRefused("job attempts are invalid")
        attempts[key] = count
    return attempts


def _safe_result(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        raise MaintenanceRefused("job result is invalid")
    result: dict[str, object] = {}
    for key, item in value.items():
        if key not in _SAFE_RESULT_KEYS:
            raise MaintenanceRefused("unsafe job result key")
        if isinstance(item, str):
            result[key] = _bounded_string(item, f"job result {key}")
        elif isinstance(item, bool) or item is None:
            result[key] = item
        elif isinstance(item, int) and not isinstance(item, bool):
            result[key] = item
        else:
            raise MaintenanceRefused("job result value is invalid")
    return result


def _job_payload(job: UpdateJob) -> dict[str, object]:
    return {
        **({"hermes_home": str(job.hermes_home)} if job.hermes_home is not None else {}),
        "schema_version": job.schema_version,
        "job_id": job.job_id,
        "phase": job.phase,
        "hermes_root": str(job.hermes_root),
        "config_path": str(job.config_path),
        "env_file": str(job.env_file) if job.env_file is not None else None,
        "profile_id": job.profile_id,
        "chat_id": job.chat_id,
        "card_message_id": job.card_message_id,
        "operator_hash": job.operator_hash,
        "pre_update_version": job.pre_update_version,
        "pre_update_head": job.pre_update_head,
        "target_fingerprint": job.target_fingerprint,
        "target_head": job.target_head,
        "artifact_version": job.artifact_version,
        "artifact_sha256": job.artifact_sha256,
        "artifact_path": str(job.artifact_path),
        "attempts": dict(job.attempts),
        "created_at": job.created_at,
        "updated_at": job.updated_at,
        "result": dict(job.result),
        "bot_id": job.bot_id,
        "revision": job.revision,
        "pre_sidecar_pid": job.pre_sidecar_pid,
        "pre_runtime_id_hash": job.pre_runtime_id_hash,
        "pre_runtime_sequence": job.pre_runtime_sequence,
    }


def _drain_payload(lease: DrainLease) -> dict[str, object]:
    return {
        "schema_version": lease.schema_version,
        "owner_id": lease.owner_id,
        "created_at": lease.created_at,
        "expires_at": lease.expires_at,
    }


def _unlink_regular_job(path: Path) -> None:
    if path.is_symlink():
        return
    try:
        if path.is_file():
            path.unlink()
    except OSError:
        return
