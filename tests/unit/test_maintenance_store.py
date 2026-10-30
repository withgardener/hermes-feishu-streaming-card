import json
import os
from pathlib import Path
import stat
import zipfile
from concurrent.futures import ThreadPoolExecutor

import pytest

from hermes_feishu_card.maintenance_store import (
    ArtifactMetadata,
    MaintenanceRefused,
    UpdateLockLease,
    acquire_update_lock,
    create_job,
    consume_job_credentials,
    discard_job_credentials,
    discard_unstarted_job,
    file_sha256,
    load_job,
    load_verified_artifact,
    load_active_drain_lease,
    maintenance_paths,
    load_job_credentials,
    prune_jobs,
    release_drain_lease,
    require_drain_lease,
    require_update_lock_lease,
    reserve_drain_lease,
    stage_job_credentials,
    stage_wheel_artifact,
    transition_job,
)


def _write_wheel(
    path: Path,
    *,
    distribution: str = "hermes-feishu-streaming-card",
    version: str = "4.2.0",
) -> Path:
    dist_info = f"hermes_feishu_streaming_card-{version}.dist-info"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(
            f"{dist_info}/METADATA",
            "\n".join(
                [
                    "Metadata-Version: 2.1",
                    f"Name: {distribution}",
                    f"Version: {version}",
                    "",
                ]
            ),
        )
        archive.writestr(
            "hermes_feishu_card/__init__.py",
            f'__version__ = "{version}"\n',
        )
    return path


@pytest.fixture
def wheel_file(tmp_path):
    return _write_wheel(tmp_path / "hfc.whl")


@pytest.fixture
def verified_artifact(tmp_path, wheel_file):
    return stage_wheel_artifact(
        maintenance_paths(tmp_path / "state"),
        wheel_file,
        expected_version="4.2.0",
        source_kind="installer_spec",
        now=lambda: 100.0,
    )


def _create_job(tmp_path: Path, artifact: ArtifactMetadata, **overrides):
    values = {
        "hermes_root": tmp_path / "hermes",
        "config_path": tmp_path / "config.yaml",
        "env_file": None,
        "profile_id": "default",
        "chat_id": "oc_private",
        "card_message_id": "om_card",
        "operator_hash": "sha256:operator",
        "pre_update_version": "0.19.1",
        "pre_update_head": "abc123",
        "target_fingerprint": "target-1",
        "target_head": "d" * 40,
        "artifact": artifact,
    }
    values.update(overrides)
    return create_job(
        maintenance_paths(tmp_path / "state"),
        now=lambda: 100.0,
        **values,
    )


def test_stage_wheel_records_exact_version_hash_and_private_modes(
    tmp_path, wheel_file
):
    paths = maintenance_paths(tmp_path / "state")

    metadata = stage_wheel_artifact(
        paths,
        wheel_file,
        expected_version="4.2.0",
        source_kind="installer_spec",
        now=lambda: 100.0,
    )

    assert metadata.version == "4.2.0"
    assert metadata.distribution == "hermes-feishu-streaming-card"
    assert metadata.sha256 == file_sha256(metadata.wheel_path)
    assert metadata.created_at == 100.0
    assert stat.S_IMODE(paths.root.stat().st_mode) == 0o700
    if os.name != "nt":
        assert stat.S_IMODE(metadata.wheel_path.stat().st_mode) == 0o600
        assert stat.S_IMODE(metadata.metadata_path.stat().st_mode) == 0o600


def test_load_verified_artifact_rejects_hash_drift(tmp_path, wheel_file):
    paths = maintenance_paths(tmp_path / "state")
    metadata = stage_wheel_artifact(
        paths,
        wheel_file,
        expected_version="4.2.0",
    )
    metadata.wheel_path.write_bytes(metadata.wheel_path.read_bytes() + b"tamper")

    with pytest.raises(MaintenanceRefused, match="artifact hash mismatch"):
        load_verified_artifact(paths, expected_version="4.2.0")


def test_stage_wheel_rejects_wrong_distribution_or_version(tmp_path):
    paths = maintenance_paths(tmp_path / "state")
    wrong_name = _write_wheel(
        tmp_path / "wrong-name.whl",
        distribution="other-package",
    )
    with pytest.raises(MaintenanceRefused, match="artifact distribution mismatch"):
        stage_wheel_artifact(paths, wrong_name, expected_version="4.2.0")

    wrong_version = _write_wheel(tmp_path / "wrong-version.whl", version="4.1.4")
    with pytest.raises(MaintenanceRefused, match="artifact version mismatch"):
        stage_wheel_artifact(paths, wrong_version, expected_version="4.2.0")


def test_transition_job_is_atomic_and_compare_and_swap(tmp_path, verified_artifact):
    job = _create_job(tmp_path, verified_artifact)

    updated = transition_job(
        job.path,
        expected_phase="locking",
        phase="draining",
        now=lambda: 110.0,
    )

    assert updated.phase == "draining"
    assert updated.updated_at == 110.0
    assert updated.attempts == {"draining": 1}
    assert updated.revision == 1
    with pytest.raises(MaintenanceRefused, match="job phase changed"):
        transition_job(
            job.path,
            expected_phase="locking",
            phase="failed",
        )


def test_job_round_trip_omits_secrets_and_raw_output(tmp_path, verified_artifact):
    env_file = tmp_path / ".env"
    job = _create_job(tmp_path, verified_artifact, env_file=env_file)

    loaded = load_job(job.path)
    payload = json.loads(job.path.read_text(encoding="utf-8"))
    serialized = json.dumps(payload).lower()

    assert loaded == job
    assert loaded.env_file == env_file.resolve(strict=False)
    assert "app_secret" not in serialized
    assert "tenant_token" not in serialized
    assert "transport_secret" not in serialized
    assert "raw_output" not in payload
    assert payload["schema_version"] == 2
    assert payload["target_head"] == "d" * 40
    assert payload["revision"] == 0
    if os.name != "nt":
        assert stat.S_IMODE(job.path.stat().st_mode) == 0o600


def test_load_job_rejects_symlink_and_unknown_result_key(tmp_path, verified_artifact):
    job = _create_job(tmp_path, verified_artifact)
    symlink = job.path.with_name("linked.json")
    try:
        symlink.symlink_to(job.path)
    except OSError:
        pytest.skip("symlinks are unavailable")

    with pytest.raises(MaintenanceRefused, match="job path must not be a symlink"):
        load_job(symlink)

    payload = json.loads(job.path.read_text(encoding="utf-8"))
    payload["result"] = {"raw_output": "secret"}
    job.path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(MaintenanceRefused, match="unsafe job result key"):
        load_job(job.path)


def test_update_lock_is_exclusive(tmp_path):
    paths = maintenance_paths(tmp_path / "state")

    with acquire_update_lock(paths, job_id="job-1"):
        with pytest.raises(MaintenanceRefused, match="update already in progress"):
            with acquire_update_lock(paths, job_id="job-2"):
                raise AssertionError("lock must not be acquired twice")


def test_forged_and_stale_same_job_lock_leases_are_rejected(tmp_path):
    paths = maintenance_paths(tmp_path / "state")
    with acquire_update_lock(paths, job_id="job-1") as real:
        forged = UpdateLockLease(
            job_id=real.job_id,
            path=real.path,
            _owner_token=real._owner_token,
        )
        with pytest.raises(MaintenanceRefused, match="not active"):
            require_update_lock_lease(
                paths,
                job_id="job-1",
                lease=forged,
            )
        stale = real

    with pytest.raises(MaintenanceRefused, match="not active"):
        require_update_lock_lease(paths, job_id="job-1", lease=stale)


def test_update_lock_rejects_symlink_target(tmp_path):
    paths = maintenance_paths(tmp_path / "state")
    paths.root.mkdir(parents=True)
    target = tmp_path / "outside.lock"
    target.write_text("keep\n", encoding="utf-8")
    try:
        paths.lock.symlink_to(target)
    except OSError:
        pytest.skip("symlinks are unavailable")

    with pytest.raises(MaintenanceRefused, match="lock must not be a symlink"):
        with acquire_update_lock(paths, job_id="job-1"):
            raise AssertionError("symlink lock must not be acquired")
    assert target.read_text(encoding="utf-8") == "keep\n"


def test_transition_job_is_interprocess_compare_and_swap(tmp_path, verified_artifact):
    job = _create_job(tmp_path, verified_artifact)

    def transition(phase):
        try:
            return transition_job(
                job.path,
                expected_phase="locking",
                phase=phase,
            ).phase
        except MaintenanceRefused:
            return "refused"

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(transition, ("draining", "failed")))

    assert results.count("refused") == 1
    assert load_job(job.path).revision == 1


def test_only_unstarted_job_can_be_discarded(tmp_path, verified_artifact):
    job = _create_job(tmp_path, verified_artifact)
    assert discard_unstarted_job(job.path) is True
    assert not job.path.exists()

    started = _create_job(tmp_path, verified_artifact)
    transition_job(started.path, expected_phase="locking", phase="draining")
    with pytest.raises(MaintenanceRefused, match="cannot be discarded"):
        discard_unstarted_job(started.path)


def test_drain_lease_is_durable_exclusive_and_owner_bound(tmp_path):
    paths = maintenance_paths(tmp_path / "state")

    lease = reserve_drain_lease(
        paths,
        owner_id="job-1",
        now=lambda: 100.0,
        ttl_seconds=60.0,
    )

    assert lease.owner_id == "job-1"
    assert load_active_drain_lease(paths, now=lambda: 120.0) == lease
    assert require_drain_lease(paths, owner_id="job-1", now=lambda: 120.0) == lease
    with pytest.raises(MaintenanceRefused, match="maintenance drain already reserved"):
        reserve_drain_lease(paths, owner_id="job-2", now=lambda: 120.0)
    with pytest.raises(MaintenanceRefused, match="drain lease owner mismatch"):
        require_drain_lease(paths, owner_id="job-2", now=lambda: 120.0)

    assert release_drain_lease(paths, owner_id="job-2") is False
    assert release_drain_lease(paths, owner_id="job-1") is True
    assert load_active_drain_lease(paths, now=lambda: 120.0) is None


def test_expired_drain_lease_can_be_replaced(tmp_path):
    paths = maintenance_paths(tmp_path / "state")
    reserve_drain_lease(
        paths,
        owner_id="job-old",
        now=lambda: 100.0,
        ttl_seconds=10.0,
    )

    assert load_active_drain_lease(paths, now=lambda: 111.0) is None
    replacement = reserve_drain_lease(
        paths,
        owner_id="job-new",
        now=lambda: 111.0,
        ttl_seconds=10.0,
    )
    assert replacement.owner_id == "job-new"


def test_job_credentials_are_private_allowlisted_and_consumed_once(tmp_path):
    paths = maintenance_paths(tmp_path / "state")
    path = stage_job_credentials(
        paths,
        job_id="job-1",
        environment={
            "FEISHU_APP_ID": "cli_test",
            "FEISHU_APP_SECRET": "secret-test-only",
            "UNSAFE_VALUE": "must-not-be-stored",
        },
    )

    assert path is not None
    assert "UNSAFE_VALUE" not in path.read_text(encoding="utf-8")
    if os.name != "nt":
        assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert consume_job_credentials(paths, job_id="job-1") == {
        "FEISHU_APP_ID": "cli_test",
        "FEISHU_APP_SECRET": "secret-test-only",
    }
    assert not path.exists()
    assert consume_job_credentials(paths, job_id="job-1") == {}
    assert discard_job_credentials(paths, job_id="job-1") is False


def test_job_environment_is_private_allowlisted_and_one_shot(tmp_path):
    paths = maintenance_paths(tmp_path / "state")
    staged = stage_job_credentials(
        paths,
        job_id="job-1",
        environment={
            "HTTPS_PROXY": "http://127.0.0.1:7897",
            "UNSAFE_VALUE": "drop-me",
        },
    )

    assert staged is not None
    assert load_job_credentials(paths, job_id="job-1") == {
        "HTTPS_PROXY": "http://127.0.0.1:7897"
    }
    assert consume_job_credentials(paths, job_id="job-1") == {
        "HTTPS_PROXY": "http://127.0.0.1:7897"
    }
    assert not staged.exists()


def test_prune_jobs_keeps_five_recent_and_removes_jobs_older_than_seven_days(
    tmp_path, verified_artifact
):
    paths = maintenance_paths(tmp_path / "state")
    jobs = []
    for index in range(7):
        job = create_job(
            paths,
            hermes_root=tmp_path / "hermes",
            config_path=tmp_path / "config.yaml",
            env_file=None,
            profile_id="default",
            chat_id=f"oc_{index}",
            card_message_id=f"om_{index}",
            operator_hash="sha256:operator",
            pre_update_version="0.19.1",
            pre_update_head=f"head-{index}",
            target_fingerprint=f"target-{index}",
            target_head="d" * 40,
            artifact=verified_artifact,
            job_id=f"job-{index}",
            now=lambda index=index: float(index * 100),
        )
        jobs.append(
            transition_job(
                job.path,
                expected_phase="locking",
                phase="failed",
                result={
                    "error_code": "test_failure",
                    "recovery_boundary": "no_mutation",
                },
                now=lambda index=index: float(index * 100),
            )
        )

    prune_jobs(paths, now=700.0, max_terminal=5, max_age_seconds=10_000.0)

    assert not jobs[0].path.exists()
    assert not jobs[1].path.exists()
    assert all(job.path.exists() for job in jobs[2:])

    prune_jobs(paths, now=700.0 + 604_801.0, max_terminal=5)

    assert list(paths.jobs.glob("*.json")) == []


def test_prune_jobs_removes_terminal_and_orphan_credential_snapshots(
    tmp_path, verified_artifact
):
    paths = maintenance_paths(tmp_path / "state")
    live = create_job(
        paths,
        hermes_root=tmp_path / "hermes",
        config_path=tmp_path / "config.yaml",
        env_file=None,
        profile_id="default",
        chat_id="oc_live",
        card_message_id="om_live",
        operator_hash="sha256:operator",
        pre_update_version="0.19.1",
        pre_update_head="a" * 40,
        target_fingerprint="b" * 64,
        target_head="c" * 40,
        artifact=verified_artifact,
        job_id="job-live",
    )
    terminal = create_job(
        paths,
        hermes_root=tmp_path / "hermes",
        config_path=tmp_path / "config.yaml",
        env_file=None,
        profile_id="default",
        chat_id="oc_terminal",
        card_message_id="om_terminal",
        operator_hash="sha256:operator",
        pre_update_version="0.19.1",
        pre_update_head="a" * 40,
        target_fingerprint="b" * 64,
        target_head="c" * 40,
        artifact=verified_artifact,
        job_id="job-terminal",
    )
    terminal = transition_job(
        terminal.path,
        expected_phase="locking",
        phase="failed",
        result={"error_code": "test", "recovery_boundary": "no_mutation"},
    )
    environment = {
        "FEISHU_APP_ID": "cli_test",
        "FEISHU_APP_SECRET": "secret-test-only",
    }
    live_credentials = stage_job_credentials(
        paths, job_id=live.job_id, environment=environment
    )
    terminal_credentials = stage_job_credentials(
        paths, job_id=terminal.job_id, environment=environment
    )
    orphan_credentials = stage_job_credentials(
        paths, job_id="job-orphan", environment=environment
    )

    prune_jobs(paths)

    assert live_credentials is not None and live_credentials.exists()
    assert terminal_credentials is not None and not terminal_credentials.exists()
    assert orphan_credentials is not None and not orphan_credentials.exists()


def test_default_maintenance_paths_secure_shared_state_root(
    tmp_path, monkeypatch
):
    shared_state = tmp_path / "shared-state"
    monkeypatch.setenv("HERMES_FEISHU_CARD_STATE_DIR", str(shared_state))
    paths = maintenance_paths()

    reserve_drain_lease(paths, owner_id="job-private")

    assert shared_state.is_dir()
    if os.name != "nt":
        assert stat.S_IMODE(shared_state.stat().st_mode) == 0o700


def test_job_keeps_home_binding_across_reload_and_transition(tmp_path, verified_artifact):
    home=tmp_path/'profile-a'
    job=_create_job(tmp_path,verified_artifact,hermes_home=home)
    assert load_job(job.path).hermes_home==home
    moved=transition_job(job.path,expected_phase='locking',phase='draining',now=lambda:101.0)
    assert moved.hermes_home==home and load_job(job.path).hermes_home==home
    payload=json.loads(job.path.read_text()); payload['hermes_home']='relative'
    job.path.write_text(json.dumps(payload))
    with pytest.raises(MaintenanceRefused):load_job(job.path)
