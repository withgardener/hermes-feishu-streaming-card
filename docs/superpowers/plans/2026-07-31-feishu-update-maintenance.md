# Feishu Private-Chat Hermes Update Orchestration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a confirmed Feishu private-chat `/update` workflow that runs the official Hermes updater from an independent maintenance runtime, reinstalls the exact pinned HFC version, restores services, and reports progress in one card.

**Architecture:** Extend the existing authenticated operations transport with an update-specific operation kind, but keep durable update state outside the in-memory operations store. A private maintenance root contains a verified HFC wheel, an independent virtual environment, atomic job journals, and a global lock. The sidecar performs read-only inspection and confirmation; a detached supervisor performs restore, official update, pinned reinstall, patch, restart, and verification while directly updating the original Feishu card.

**Tech Stack:** Python 3.9+, stdlib `dataclasses`/`hashlib`/`json`/`subprocess`/`venv`/file locking, aiohttp, existing `FeishuClient`, pytest/pytest-asyncio, Bash, PowerShell.

## Global Constraints

- Intercept only an exact bare `/update` in a Feishu private chat.
- Group, topic-as-group, non-Feishu, alias, and parameterized update paths call Hermes' original handler unchanged.
- A claimed private update path fails closed: it never falls through to an unconfirmed native update.
- Require a signed, chat-bound, initiator-bound, evidence-bound confirmation that expires after 120 seconds.
- Run only `hermes update --yes`; never add `--force`, `--force-venv`, or `--no-backup`.
- Reinstall the exact already verified HFC version from a private cached wheel; never resolve or install `latest`.
- Do not edit installed Hermes files outside `hermes_feishu_card/install/patcher.py`.
- Refuse unrelated tracked changes and incomplete Git operations; preserve all untracked files.
- Do not implement a custom Git rollback, reset, checkout replacement, or stash mutation.
- Keep the maintenance runtime outside the Hermes checkout and Hermes virtual environment.
- Keep the maintenance root mode `0700` and artifact, metadata, lock, and journal files mode `0600`.
- Do not place Feishu secrets, transport secrets, raw subprocess output, or arbitrary commands in journals/cards/health output.
- Do not publish, tag, merge, or contact upstream Hermes in this implementation branch.
- Target the next minor HFC release, `4.2.0`; prepare release documentation but do not publish it.

---

## File Structure

### New Production Files

- `hermes_feishu_card/maintenance_store.py`: private maintenance paths, artifact metadata, atomic job journals, compare-and-swap transitions, retention, and cross-process lock.
- `hermes_feishu_card/maintenance_update.py`: update inspection, Git safety checks, command runner, phase state machine, recovery classification, and service verification.
- `hermes_feishu_card/maintenance_process.py`: maintenance virtual-environment provisioning and detached/systemd-user job launch.
- `hermes_feishu_card/maintenance_card.py`: update card rendering and direct Feishu progress publishing.
- `hermes_feishu_card/maintenance_runner.py`: isolated `python -I -m` entry point that loads one durable job and runs the supervisor.

### Modified Production Files

- `hermes_feishu_card/hook_runtime.py`: exact private `/update` wrapper, authenticated command submission, action forwarding, and fail-closed feedback.
- `hermes_feishu_card/operations.py`: update operation kind, private owner binding, update transitions, and update card dispatch.
- `hermes_feishu_card/server.py`: update command inspection, confirmation action, durable job creation, initial card delivery, and supervisor launch.
- `hermes_feishu_card/cli.py`: `maintenance provision/status/run/resume` commands, setup provisioning, and doctor maintenance report.
- `hermes_feishu_card/process.py`: reusable sidecar identity and wait helpers only where the supervisor needs the same verified lifecycle boundary.
- `install.sh`, `install.ps1`: preserve the exact HFC install spec for setup and report maintenance provisioning outcome.
- `pyproject.toml`, `hermes_feishu_card/__init__.py`: version `4.2.0`.
- `README.md`, `README.en.md`, `CHANGELOG.md`, `docs/wiki/README.md`, `docs/wiki/event-flow.md`, `docs/wiki/maintenance-guide.md`, `docs/wiki/feishu-acceptance.md`, `docs/release-notes-v4.2.0.md`: behavior, recovery, and release documentation.

### New Tests

- `tests/unit/test_maintenance_store.py`
- `tests/unit/test_maintenance_update.py`
- `tests/unit/test_maintenance_process.py`
- `tests/unit/test_maintenance_card.py`
- `tests/integration/test_maintenance_runner.py`

### Modified Tests

- `tests/unit/test_hook_runtime.py`
- `tests/unit/test_operations.py`
- `tests/integration/test_server.py`
- `tests/integration/test_cli.py`
- `tests/integration/test_cli_install.py`
- `tests/unit/test_install_scripts.py`
- `tests/unit/test_diagnostics.py`
- `tests/unit/test_docs.py`
- `tests/unit/test_package_metadata.py`

---

### Task 1: Private Artifact Store and Durable Job Journal

**Files:**
- Create: `hermes_feishu_card/maintenance_store.py`
- Create: `tests/unit/test_maintenance_store.py`

**Interfaces:**
- Produces: `MaintenancePaths`, `ArtifactMetadata`, `UpdateJob`, `maintenance_paths`, `stage_wheel_artifact`, `load_verified_artifact`, `create_job`, `load_job`, `transition_job`, `acquire_update_lock`, `prune_jobs`.
- Consumes: HFC package version and filesystem paths only; it must not import server or Hermes code.

- [ ] **Step 1: Write failing path, permission, and artifact tests**

```python
def test_stage_wheel_records_exact_version_hash_and_private_modes(tmp_path, wheel_file):
    paths = maintenance_paths(tmp_path)
    metadata = stage_wheel_artifact(
        paths,
        wheel_file,
        expected_version="4.2.0",
        source_kind="installer_spec",
    )
    assert metadata.version == "4.2.0"
    assert metadata.sha256 == file_sha256(metadata.wheel_path)
    assert stat.S_IMODE(paths.root.stat().st_mode) == 0o700
    assert stat.S_IMODE(metadata.wheel_path.stat().st_mode) == 0o600
    assert stat.S_IMODE(metadata.metadata_path.stat().st_mode) == 0o600


def test_load_verified_artifact_rejects_hash_or_version_drift(tmp_path, wheel_file):
    paths = maintenance_paths(tmp_path)
    metadata = stage_wheel_artifact(paths, wheel_file, expected_version="4.2.0")
    metadata.wheel_path.write_bytes(metadata.wheel_path.read_bytes() + b"tamper")
    with pytest.raises(MaintenanceRefused, match="artifact hash mismatch"):
        load_verified_artifact(paths, expected_version="4.2.0")
```

- [ ] **Step 2: Run artifact tests and verify RED**

Run:

```bash
python3 -m pytest tests/unit/test_maintenance_store.py -q
```

Expected: collection fails because `hermes_feishu_card.maintenance_store` does not exist.

- [ ] **Step 3: Implement private paths and wheel inspection**

```python
@dataclass(frozen=True)
class MaintenancePaths:
    root: Path
    runtime: Path
    artifacts: Path
    jobs: Path
    lock: Path


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


def maintenance_paths(root: Path | None = None) -> MaintenancePaths:
    selected = (root or state_dir() / "maintenance").expanduser()
    return MaintenancePaths(
        root=selected,
        runtime=selected / "runtime",
        artifacts=selected / "artifacts",
        jobs=selected / "jobs",
        lock=selected / "update.lock",
    )
```

Implement wheel metadata inspection with `zipfile.ZipFile`, requiring one
`*.dist-info/METADATA`, distribution
`hermes-feishu-streaming-card`, and exact `Version`. Copy through a same-directory
temporary file, `fsync`, `chmod(0o600)`, and `os.replace`.

- [ ] **Step 4: Write failing journal and lock tests**

```python
def test_transition_job_is_atomic_and_compare_and_swap(tmp_path, verified_artifact):
    job = create_job(
        maintenance_paths(tmp_path),
        hermes_root=tmp_path / "hermes",
        config_path=tmp_path / "config.yaml",
        env_file=None,
        profile_id="default",
        chat_id="oc_private",
        card_message_id="om_card",
        operator_hash="sha256:operator",
        pre_update_head="abc123",
        target_fingerprint="target-1",
        artifact=verified_artifact,
    )
    updated = transition_job(job.path, expected_phase="locking", phase="draining")
    assert updated.phase == "draining"
    with pytest.raises(MaintenanceRefused, match="job phase changed"):
        transition_job(job.path, expected_phase="locking", phase="failed")


def test_job_json_omits_secrets_and_raw_output(tmp_path, verified_artifact):
    job = create_job(
        maintenance_paths(tmp_path),
        hermes_root=tmp_path / "hermes",
        config_path=tmp_path / "config.yaml",
        env_file=None,
        profile_id="default",
        chat_id="oc_private",
        card_message_id="om_card",
        operator_hash="sha256:operator",
        pre_update_version="0.19.1",
        pre_update_head="abc123",
        target_fingerprint="target-1",
        artifact=verified_artifact,
    )
    payload = json.loads(job.path.read_text())
    assert "app_secret" not in json.dumps(payload).lower()
    assert "tenant_token" not in json.dumps(payload).lower()
    assert "transport_secret" not in json.dumps(payload).lower()
    assert "raw_output" not in payload
```

- [ ] **Step 5: Run journal tests and verify RED**

Run the two new tests directly. Expected: missing `UpdateJob`, `create_job`, and lock APIs.

- [ ] **Step 6: Implement job schema, atomic transitions, lock, and retention**

```python
UPDATE_PHASES = (
    "locking", "draining", "restoring_hooks", "updating_hermes",
    "reinstalling_hfc", "starting_services", "verifying",
    "succeeded", "failed", "cancelled",
)


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
```

Validate exact schema keys, phase names, absolute normalized paths, maximum
field lengths, safe result keys, symlink refusal, owner UID on POSIX, private
modes, and expected-phase compare-and-swap before atomic replace. Use
`fcntl.flock(..., LOCK_EX | LOCK_NB)` on POSIX and `msvcrt.locking` on Windows.
Retain at most five terminal jobs, remove terminal jobs older than seven days,
and never prune an in-flight job.

- [ ] **Step 7: Verify and commit Task 1**

Run:

```bash
python3 -m pytest tests/unit/test_maintenance_store.py -q
git diff --check
```

Expected: all maintenance-store tests pass and no whitespace errors.

Commit:

```bash
git add hermes_feishu_card/maintenance_store.py tests/unit/test_maintenance_store.py
git commit -m "feat: add durable maintenance job store"
```

---

### Task 2: Read-Only Update Inspection

**Files:**
- Create: `hermes_feishu_card/maintenance_update.py`
- Create: `tests/unit/test_maintenance_update.py`

**Interfaces:**
- Consumes: `ArtifactMetadata`, `load_verified_artifact`, existing `detect_hermes`, manifests/backups, config path, active-session count.
- Produces: `CommandResult`, `UpdateInspection`, `inspect_update`, `inspection_fingerprint`, `sanitize_command_result`, `detect_runtime_python`.

- [ ] **Step 1: Write failing command and Git-safety tests**

```python
def test_inspect_update_runs_only_read_only_commands(clean_hermes, artifact, runner):
    inspection = inspect_update(
        hermes_root=clean_hermes,
        artifact=artifact,
        installed_hfc_version="4.2.0",
        active_sessions=0,
        run=runner,
    )
    assert inspection.ready is True
    assert runner.commands == [
        ("git", "-C", str(clean_hermes), "rev-parse", "HEAD"),
        ("git", "-C", str(clean_hermes), "status", "--porcelain=v1", "--untracked-files=no"),
        ("hermes", "update", "--check"),
    ]


def test_inspect_update_refuses_unrelated_tracked_change(clean_hermes, artifact, runner):
    runner.git_status = " M gateway/unrelated.py\n"
    inspection = inspect_update(
        hermes_root=clean_hermes,
        artifact=artifact,
        installed_hfc_version="4.2.0",
        active_sessions=0,
        run=runner,
    )
    assert inspection.ready is False
    assert inspection.reason_code == "unrelated_tracked_changes"


def test_inspect_update_allows_untracked_files(clean_hermes, artifact, runner):
    (clean_hermes / "notes.local.md").write_text("keep")
    inspection = inspect_update(
        hermes_root=clean_hermes,
        artifact=artifact,
        installed_hfc_version="4.2.0",
        active_sessions=0,
        run=runner,
    )
    assert inspection.ready is True
```

- [ ] **Step 2: Run focused tests and verify RED**

Run:

```bash
python3 -m pytest tests/unit/test_maintenance_update.py -q
```

Expected: missing update inspection APIs.

- [ ] **Step 3: Implement immutable inspection and safe command runner**

```python
@dataclass(frozen=True)
class CommandResult:
    argv: tuple[str, ...]
    returncode: int
    stdout: str
    stderr: str
    timed_out: bool = False


@dataclass(frozen=True)
class UpdateInspection:
    ready: bool
    reason_code: str
    current_version: str
    current_head: str
    target_summary: str
    target_fingerprint: str
    hfc_version: str
    artifact_sha256: str
    active_sessions: int
    hook_state: str
    maintenance_ready: bool
    created_at: float

    @property
    def fingerprint(self) -> str:
        return inspection_fingerprint(self)
```

`inspect_update` must:

- require supported/full Hermes detection;
- reject `.git/MERGE_HEAD`, `.git/rebase-merge`, `.git/rebase-apply`, and
  `git status` unmerged records;
- accept tracked modifications only for the exact HFC-owned files whose
  manifest/backup/current hashes prove an installed HFC transaction;
- omit untracked files from the status command;
- call `hermes update --check` with a 60-second timeout;
- hash the normalized check output for target evidence;
- cap sanitized target copy at 240 characters;
- return data, never raise raw subprocess output into cards.

- [ ] **Step 4: Add artifact drift, active work, timeout, and sanitization tests**

```python
@pytest.mark.parametrize(
    "active_sessions",
    [1, 3],
)
def test_inspection_reports_active_work_without_mutating(
    clean_hermes, artifact, runner, active_sessions
):
    inspection = inspect_update(
        hermes_root=clean_hermes,
        artifact=artifact,
        installed_hfc_version="4.2.0",
        active_sessions=active_sessions,
        run=runner,
    )
    assert inspection.ready is True
    assert inspection.active_sessions == active_sessions


def test_update_check_timeout_is_not_ready(clean_hermes, artifact, runner):
    runner.update_result = CommandResult(
        ("hermes", "update", "--check"), -1, "", "", timed_out=True
    )
    inspection = inspect_update(
        hermes_root=clean_hermes,
        artifact=artifact,
        installed_hfc_version="4.2.0",
        active_sessions=0,
        run=runner,
    )
    assert inspection.reason_code == "update_check_timeout"
```

- [ ] **Step 5: Verify and commit Task 2**

Run:

```bash
python3 -m pytest tests/unit/test_maintenance_update.py tests/unit/test_recovery.py -q
git diff --check
```

Commit:

```bash
git add hermes_feishu_card/maintenance_update.py tests/unit/test_maintenance_update.py
git commit -m "feat: inspect Hermes updates safely"
```

---

### Task 3: Maintenance Cards and Direct Progress Publishing

**Files:**
- Create: `hermes_feishu_card/maintenance_card.py`
- Create: `tests/unit/test_maintenance_card.py`

**Interfaces:**
- Consumes: `UpdateInspection`, `UpdateJob`, existing `FeishuClient`.
- Produces: `render_update_inspection_card`, `render_update_job_card`, `FeishuJobPublisher`.

- [ ] **Step 1: Write failing card-state tests**

```python
def test_ready_inspection_card_has_confirm_and_cancel_only(inspection):
    card = render_update_inspection_card(inspection, confirm_value, cancel_value)
    values = callback_values(card)
    assert [item["operation_action"] for item in values] == [
        "confirm_update", "cancel_update"
    ]
    serialized = json.dumps(card, ensure_ascii=False)
    assert "Hermes" in serialized
    assert "HFC 4.2.0（保持不变）" in serialized


@pytest.mark.parametrize(
    "phase",
    ["locking", "draining", "restoring_hooks", "updating_hermes",
     "reinstalling_hfc", "starting_services", "verifying",
     "succeeded", "failed", "cancelled"],
)
def test_job_card_has_no_buttons_and_no_raw_output(job, phase):
    card = render_update_job_card(replace(job, phase=phase))
    assert callback_values(card) == []
    assert "/Users/" not in json.dumps(card)
    assert "raw_output" not in json.dumps(card)
```

- [ ] **Step 2: Run card tests and verify RED**

Expected: module missing.

- [ ] **Step 3: Implement fixed copy and sanitized rendering**

Use the approved interaction copy:

```python
_PHASE_COPY = {
    "locking": ("正在准备更新", "正在锁定本次维护任务。", "blue"),
    "draining": ("正在等待任务结束", "新任务已暂停接入，正在等待当前工作安全结束。", "blue"),
    "restoring_hooks": ("正在准备 Hermes", "正在安全移除本版本 HFC 管理的钩子。", "blue"),
    "updating_hermes": ("正在更新 Hermes", "正在执行官方 Hermes 更新流程。", "blue"),
    "reinstalling_hfc": ("正在恢复卡片功能", "正在重新安装同一 HFC 版本并生成新钩子。", "blue"),
    "starting_services": ("正在启动服务", "正在启动 sidecar 并重启 Gateway。", "blue"),
    "verifying": ("正在完成验证", "正在检查版本、导入来源、运行时认证与健康状态。", "blue"),
    "succeeded": ("更新完成", "Hermes 已更新，HFC 版本保持不变且服务已就绪。", "green"),
    "failed": ("更新未完成", "已停在安全边界，请按下方恢复建议处理。", "red"),
    "cancelled": ("已取消更新", "未执行 Hermes 更新。", "grey"),
}
```

Inspection cards show current Hermes, target summary, pinned HFC, hook/artifact
readiness, and active-work warning. Error cards show a stable reason and one
allowlisted local recovery command.

- [ ] **Step 4: Write failing publisher tests**

```python
@pytest.mark.asyncio
async def test_publisher_updates_exact_original_message(fake_client, job):
    publisher = FeishuJobPublisher(client=fake_client)
    assert await publisher.publish(job) is True
    assert fake_client.updated == [(job.card_message_id, ANY_CARD)]


@pytest.mark.asyncio
async def test_publisher_returns_false_without_exposing_api_body(fake_client, job):
    fake_client.error = FeishuAPIError("private response body", status_code=500)
    assert await FeishuJobPublisher(fake_client).publish(job) is False
```

- [ ] **Step 5: Implement direct publisher and commit**

`FeishuJobPublisher` calls only `FeishuClient.update_card_message`. It returns a
boolean and logs only safe status/API codes. It never logs the card message id,
chat id, credentials, or response body.

Run:

```bash
python3 -m pytest tests/unit/test_maintenance_card.py tests/unit/test_feishu_client.py -q
git diff --check
```

Commit:

```bash
git add hermes_feishu_card/maintenance_card.py tests/unit/test_maintenance_card.py
git commit -m "feat: render Hermes update maintenance cards"
```

---

### Task 4: Independent Runtime Provisioning and Job Launch

**Files:**
- Create: `hermes_feishu_card/maintenance_process.py`
- Create: `tests/unit/test_maintenance_process.py`

**Interfaces:**
- Consumes: verified artifact and maintenance paths.
- Produces: `MaintenanceRuntimeStatus`, `provision_runtime`, `inspect_runtime`, `launch_job`.

- [ ] **Step 1: Write failing provisioning tests**

```python
def test_provision_runtime_uses_private_venv_and_exact_wheel(tmp_path, artifact, runner):
    status = provision_runtime(maintenance_paths(tmp_path), artifact, run=runner)
    assert status.available is True
    assert status.package_version == artifact.version
    assert "--no-deps" in runner.pip_argv
    assert str(artifact.wheel_path) in runner.pip_argv
    assert status.python_path.is_relative_to(maintenance_paths(tmp_path).runtime)


def test_inspect_runtime_rejects_python_inside_hermes(tmp_path, artifact):
    status = inspect_runtime(
        maintenance_paths(tmp_path),
        artifact,
        hermes_root=tmp_path / "hermes",
        python_path=tmp_path / "hermes" / "venv" / "bin" / "python",
    )
    assert status.available is False
    assert status.reason_code == "runtime_not_independent"
```

- [ ] **Step 2: Verify RED, then implement provision and inspection**

```python
@dataclass(frozen=True)
class MaintenanceRuntimeStatus:
    available: bool
    reason_code: str
    python_path: Path
    package_version: str
    package_location: Path | None
    manager: str
```

Provision through `python -m venv`, then:

```text
<maintenance-python> -I -m pip install --no-deps --force-reinstall <exact-wheel>
<maintenance-python> -I -c <version-and-import-origin probe>
```

Require the import origin to be under the maintenance runtime's
`site-packages`. Write a private runtime metadata file with only version,
artifact hash, interpreter path, package origin, and provisioning time.

- [ ] **Step 3: Write failing launch tests**

```python
def test_launch_job_uses_systemd_user_when_available(status, job, runner):
    runner.systemd_user_available = True
    launch = launch_job(status, job, run=runner)
    assert launch.manager == "systemd-user"
    assert launch.argv[:3] == ("systemd-run", "--user", "--unit")


def test_launch_job_detaches_without_shell(status, job, popen):
    launch = launch_job(status, job, systemd_available=False, popen=popen)
    assert launch.manager == "detached"
    assert popen.kwargs["shell"] is False
    assert popen.kwargs["start_new_session"] is True
```

- [ ] **Step 4: Implement fixed runner invocation and cross-platform detachment**

The job command is exactly:

```text
<maintenance-python> -I -m hermes_feishu_card.maintenance_runner
  --job <validated-private-job-path>
```

Linux uses `systemd-run --user --unit hfc-maintenance-<job-hash> --collect`
when the user manager is available. Other POSIX systems use
`start_new_session=True`. Windows uses
`CREATE_NEW_PROCESS_GROUP | DETACHED_PROCESS`. No branch uses `shell=True`.

- [ ] **Step 5: Verify and commit Task 4**

Run:

```bash
python3 -m pytest tests/unit/test_maintenance_process.py -q
git diff --check
```

Commit:

```bash
git add hermes_feishu_card/maintenance_process.py tests/unit/test_maintenance_process.py
git commit -m "feat: provision independent maintenance runtime"
```

---

### Task 5: Evidence-Driven Update Supervisor

**Files:**
- Modify: `hermes_feishu_card/maintenance_update.py`
- Create: `hermes_feishu_card/maintenance_runner.py`
- Create: `tests/integration/test_maintenance_runner.py`

**Interfaces:**
- Consumes: `UpdateJob`, lock/store APIs, exact wheel, `FeishuJobPublisher`, existing CLI and process commands.
- Produces: `UpdateSupervisor`, `run_job`, runner `main`.

- [ ] **Step 1: Build a disposable Hermes fixture and write the successful RED test**

```python
def test_supervisor_restores_updates_reinstalls_and_verifies(
    fake_hermes_repo, job, command_harness, health_harness
):
    result = run_job(
        job.path,
        run=command_harness,
        fetch_health=health_harness,
        publish=lambda current: True,
        sleep=lambda _: None,
    )
    assert result.phase == "succeeded"
    assert command_harness.mutations == [
        "sidecar-stop",
        "hfc-restore",
        "hermes-update",
        "pinned-wheel-install",
        "hfc-install",
        "sidecar-start",
        "gateway-restart",
    ]
    assert result.result["hfc_version"] == job.artifact_version
    assert result.result["import_origin"] == "site-packages"
```

- [ ] **Step 2: Run the success test and verify RED**

Expected: `run_job` and `UpdateSupervisor` missing.

- [ ] **Step 3: Implement phases with fixed commands**

The supervisor recomputes evidence at each boundary and executes:

```text
<maintenance-python> -I -m hermes_feishu_card.cli stop --config <config> [--env-file <env>]
<maintenance-python> -I -m hermes_feishu_card.cli restore --hermes-dir <root> --yes
hermes update --yes
<new-runtime-python> -I -m pip install --no-deps --force-reinstall <pinned-wheel>
<new-runtime-python> -I -m hermes_feishu_card.cli install --hermes-dir <root> --yes
<new-runtime-python> -I -m hermes_feishu_card.cli start --config <config> --hermes-dir <root> [--env-file <env>]
hermes gateway restart
```

Before the first mutation, require a successful progress-card PATCH. Drain
non-terminal sessions for at most 180 seconds. Run the official update with a
3600-second timeout. Persist and publish before and after each phase. Cap each
mutation phase at one attempt.

- [ ] **Step 4: Write failure-injection and resume tests**

```python
@pytest.mark.parametrize(
    ("failed_step", "expected_boundary"),
    [
        ("preflight", "no_mutation"),
        ("progress_publish", "no_mutation"),
        ("drain", "no_mutation"),
        ("restore", "old_hfc_or_manual"),
        ("hermes-update", "updater_result_classified"),
        ("pinned-wheel-install", "native_hermes"),
        ("hfc-install", "native_hermes"),
        ("sidecar-start", "service_recovery"),
        ("gateway-restart", "service_recovery"),
        ("readiness", "service_recovery"),
    ],
)
def test_failure_stops_at_documented_boundary(
    failed_step,
    expected_boundary,
    fake_hermes_repo,
    job,
    command_harness,
    health_harness,
):
    command_harness.fail_at = failed_step
    result = run_job(
        job.path,
        run=command_harness,
        fetch_health=health_harness,
        publish=lambda current: True,
        sleep=lambda delay: None,
    )
    assert result.phase == "failed"
    assert result.result["recovery_boundary"] == expected_boundary


def test_resume_rechecks_real_state_and_does_not_repeat_completed_update(
    job_at_updating_phase,
    command_harness,
    health_harness,
):
    job = job_at_updating_phase
    command_harness.actual_head = "new-head"
    result = run_job(
        job.path,
        run=command_harness,
        fetch_health=health_harness,
        publish=lambda current: True,
        sleep=lambda delay: None,
    )
    assert result.phase == "succeeded"
    assert command_harness.hermes_update_calls == 0
    assert command_harness.pinned_install_calls == 1
```

- [ ] **Step 5: Implement recovery classifier and verification**

After update, require:

- supported/full `detect_hermes`;
- no incomplete Git/update marker;
- no unrelated tracked changes;
- runtime Python available;
- pinned HFC version importable from that runtime's `site-packages`;
- fully installed hook/manifest/backup state;
- authenticated runtime hello/readiness `ready`;
- health `healthy`;
- actual Hermes version/head recorded.

If and only if read-only diagnostics report the exact verified integrity-fence
state whose prescribed action is `integrity acknowledge-review`, run:

```text
<new-runtime-python> -I -m hermes_feishu_card.cli integrity acknowledge-review
  --config <config> --hermes-dir <root> --state-dir <state-root>
  [--env-file <env>] --yes
```

Recompute the integrity fingerprint immediately before that command. Never edit
the fence directly and never acknowledge an unknown or changed state.

If the official updater fails, never run Git recovery commands. Reinstall HFC
only when the resulting checkout is complete, supported, clean, and matches a
verified old/new state.

- [ ] **Step 6: Implement isolated runner entry point**

```python
def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    job = load_job(Path(args.job), require_private=True)
    config = load_config(job.config_path, env_file=job.env_file)
    client = FeishuClient(_profile_client_config(config, job.profile_id))
    result = run_job(job.path, publisher=FeishuJobPublisher(client))
    return 0 if result.phase == "succeeded" else 1
```

The runner accepts only `--job`; it rejects symlinks, non-private files,
unknown schema, and paths outside the configured jobs directory.

- [ ] **Step 7: Verify and commit Task 5**

Run:

```bash
python3 -m pytest tests/unit/test_maintenance_store.py tests/unit/test_maintenance_update.py tests/unit/test_maintenance_process.py tests/unit/test_maintenance_card.py tests/integration/test_maintenance_runner.py -q
git diff --check
```

Commit:

```bash
git add hermes_feishu_card/maintenance_update.py hermes_feishu_card/maintenance_runner.py tests/integration/test_maintenance_runner.py
git commit -m "feat: run durable Hermes update maintenance jobs"
```

---

### Task 6: Update Operation State and Card Actions

**Files:**
- Modify: `hermes_feishu_card/operations.py`
- Modify: `tests/unit/test_operations.py`

**Interfaces:**
- Consumes: `UpdateInspection`, update-card renderer.
- Produces: `OperationRecord.kind`, `OperationRecord.owner_open_id` for update operations, `OperationStore.prepare_update`, update transitions and render dispatch.

- [ ] **Step 1: Write failing update-operation tests**

```python
def test_private_update_binds_initiator_and_expires_in_120_seconds():
    store = OperationStore(secret=b"test", now=lambda: 100.0)
    operation = store.prepare_update(
        chat_id="oc_private",
        profile_id="default",
        initiator_open_id="ou_owner",
        inspection=ready_inspection(),
        operation_id="update-1",
        transport_secret=b"x" * 32,
        idempotency_key="message-1",
    )
    assert operation.kind == "update"
    assert operation.owner_open_id == "ou_owner"
    assert operation.state == "awaiting_confirmation"
    assert operation.expires_at == 220.0


def test_private_update_rejects_different_confirmer():
    operation = prepare_update(owner="ou_owner")
    token = store.token(operation, "confirm_update")
    with pytest.raises(OperationRejected, match="different operator"):
        store.transition_update(
            token,
            action="confirm_update",
            operator_open_id="ou_other",
            callback_chat_id="oc_private",
            callback_profile_id="default",
            callback_evidence_fingerprint=operation.update_evidence_fingerprint,
        )


def test_duplicate_confirm_claims_update_once():
    accepted = concurrently_confirm_eight_times()
    assert [item.state for item in accepted] == ["locking"]
```

- [ ] **Step 2: Verify RED, then implement update-specific transitions**

Add `kind: str = "diagnostic"` and `update_evidence_fingerprint: str = ""` to
`OperationRecord`. Do not add update actions to the repair transition table.
Implement:

```python
def prepare_update(
    self,
    *,
    chat_id: str,
    profile_id: str,
    initiator_open_id: str,
    inspection: UpdateInspection,
    operation_id: str,
    transport_secret: bytes,
    idempotency_key: str,
) -> tuple[OperationRecord, bool]:
    if not initiator_open_id:
        raise OperationRejected("operator identity required")
    record, created = self.prepare(
        chat_id=chat_id,
        profile_id=profile_id,
        group=False,
        initiator_open_id="",
        operation_id=operation_id,
        transport_secret=transport_secret,
        idempotency_key=idempotency_key,
    )
    if created:
        record.kind = "update"
        record.owner_open_id = initiator_open_id
        record.state = "awaiting_confirmation"
        record.update_evidence_fingerprint = inspection.fingerprint
        record.update_inspection = inspection
    return record, created

def transition_update(
    self,
    token: str,
    *,
    action: Literal["confirm_update", "cancel_update"],
    operator_open_id: str,
    callback_chat_id: str,
    callback_profile_id: str,
    callback_evidence_fingerprint: str,
) -> OperationRecord:
    with self._lock:
        claims, record = self._verify_token_locked(token)
        if record.kind != "update" or claims.action != action:
            raise OperationRejected("operation action mismatch")
        if record.chat_id != callback_chat_id or record.profile_id != callback_profile_id:
            raise OperationRejected("operation scope mismatch")
        if record.update_evidence_fingerprint != callback_evidence_fingerprint:
            raise OperationRejected("update evidence changed")
        if operator_open_id != record.owner_open_id:
            raise OperationRejected("different operator")
        if record.state != "awaiting_confirmation":
            raise OperationRejected("invalid operation transition")
        record.state = "locking" if action == "confirm_update" else "cancelled"
        return record
```

Valid transitions are
`awaiting_confirmation -> locking` and
`awaiting_confirmation -> cancelled`. Both actions require the exact private
initiator. Tokens continue to omit raw chat/operator ids.

- [ ] **Step 3: Add render-dispatch tests**

`render_operations_card` dispatches update operations to
`render_update_inspection_card`/`render_update_job_card`; diagnostic repair
cards retain byte-for-byte action semantics.

- [ ] **Step 4: Verify and commit Task 6**

Run:

```bash
python3 -m pytest tests/unit/test_operations.py tests/unit/test_maintenance_card.py -q
git diff --check
```

Commit:

```bash
git add hermes_feishu_card/operations.py tests/unit/test_operations.py
git commit -m "feat: add confirmed private update operations"
```

---

### Task 7: Hook Runtime Exact Private `/update` Wrapper

**Files:**
- Modify: `hermes_feishu_card/hook_runtime.py`
- Modify: `tests/unit/test_hook_runtime.py`

**Interfaces:**
- Consumes: existing command proof/operation transport, Hermes update handler.
- Produces: `_hfc_install_update_command_handler`, `_hfc_handle_update_command_with_card`, authenticated `/commands` update request.

- [ ] **Step 1: Write failing routing matrix tests**

```python
@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("platform", "chat_type", "args", "expected"),
    [
        ("feishu", "private", "", "hfc"),
        ("feishu", "p2p", "", "hfc"),
        ("feishu", "group", "", "original"),
        ("telegram", "private", "", "original"),
        ("feishu", "private", "--check", "original"),
    ],
)
async def test_update_wrapper_routes_only_exact_private_command(
    monkeypatch, platform, chat_type, args, expected
):
    runner, event, calls = update_runner_event(
        platform=platform,
        chat_type=chat_type,
        command_args=args,
    )
    monkeypatch.setattr(
        hook_runtime,
        "_hfc_request_update_operation",
        lambda current_runner, current_event: True,
    )
    result = await hook_runtime._hfc_handle_update_command_with_card(runner, event)
    if expected == "hfc":
        assert result is None
        assert calls == []
    else:
        assert result == "original"
        assert calls == ["original"]
```

- [ ] **Step 2: Run focused tests and verify RED**

Run:

```bash
python3 -m pytest tests/unit/test_hook_runtime.py -k update_command -q
```

Expected: update wrapper missing.

- [ ] **Step 3: Implement exact wrapper and authenticated submission**

```python
async def _hfc_handle_update_command_with_card(runner: Any, event: Any) -> Any:
    original = getattr(type(runner), "_hfc_original_handle_update_command", None)
    if not callable(original):
        return "HFC 更新确认暂不可用；未执行 Hermes 更新。"
    if not _hfc_exact_private_update_event(event):
        return await original(runner, event)
    accepted = _hfc_request_update_operation(runner, event)
    if accepted:
        return None
    return "HFC 更新确认暂不可用；未执行 Hermes 更新。请在本机运行 `hermes-feishu-card maintenance status` 检查。"
```

`_hfc_request_update_operation` reuses the root-secret command proof used by
`/hfc doctor`, sends `command: "update"`, and remembers the derived operation
transport secret. The wrapper is installed beside resume/compress wrappers.

- [ ] **Step 4: Add identity, idempotency, fail-closed, and original-handler tests**

Require private sender `open_id`, exact chat id/message id, and no command args.
Sidecar timeout/auth rejection returns safe feedback and never invokes original.
Duplicate message delivery returns the same operation id through server
idempotency.

- [ ] **Step 5: Verify and commit Task 7**

Run:

```bash
python3 -m pytest tests/unit/test_hook_runtime.py tests/integration/test_hook_runtime_integration.py -q
git diff --check
```

Commit:

```bash
git add hermes_feishu_card/hook_runtime.py tests/unit/test_hook_runtime.py
git commit -m "feat: intercept private Feishu update commands"
```

---

### Task 8: Sidecar Command, Confirmation, and Supervisor Launch

**Files:**
- Modify: `hermes_feishu_card/server.py`
- Modify: `tests/integration/test_server.py`

**Interfaces:**
- Consumes: authenticated update command, maintenance runtime status, inspection, update operation store, job store, launcher.
- Produces: initial confirmation delivery, confirm/cancel handling, progress-card-before-launch guarantee.

- [ ] **Step 1: Write failing private update command tests**

```python
async def test_update_command_requires_proof_private_chat_and_operator(client):
    response = await client.post("/commands", json=signed_update_payload())
    assert response.status == 200
    body = await response.json()
    assert body["handled"] is True
    assert body["operation_id"]


@pytest.mark.parametrize("chat_type", ["group", "topic"])
async def test_update_command_rejects_non_private_chat(client, chat_type):
    response = await client.post(
        "/commands", json=signed_update_payload(chat_type=chat_type)
    )
    assert response.status == 400
```

- [ ] **Step 2: Implement authenticated asynchronous inspection**

Treat `command == "update"` as an authenticated operations command. Require
private chat and operator. `OperationStore.prepare_update` is idempotent by
chat/profile/message. Run `inspect_update` on the bounded operations diagnostic
executor. Send and store exactly one confirmation-card delivery.

- [ ] **Step 3: Write failing confirm/cancel and delivery-gate tests**

```python
async def test_cancel_update_never_creates_job(
    update_server_client, maintenance_paths_fixture
):
    response = await update_server_client.post_action("cancel_update")
    assert response.status == 200
    assert list(maintenance_paths_fixture.jobs.glob("*.json")) == []


async def test_confirm_publishes_locking_card_before_launch(
    update_server_client, update_call_log
):
    response = await update_server_client.post_action("confirm_update")
    await response.read()
    assert update_call_log == ["patch:locking", "create-job", "launch-job"]


async def test_failed_locking_patch_aborts_before_job(
    update_server_client, card_updater, maintenance_launcher
):
    card_updater.result = False
    await update_server_client.post_action("confirm_update")
    assert maintenance_launcher.calls == []
```

- [ ] **Step 4: Implement confirm revalidation and launch sequence**

At confirmation:

1. verify transport proof;
2. verify token/chat/profile/exact initiator;
3. rerun inspection;
4. compare inspection fingerprint;
5. atomically transition to `locking`;
6. PATCH the same card;
7. create the durable job with stored message/bot/profile delivery;
8. launch the independent supervisor.

Cancel transitions to `cancelled`, PATCHes the card, and creates no job.
Repeated confirms return current state and never create a second job.

- [ ] **Step 5: Add active-session drain snapshot**

Pass the count of sessions whose status is not `completed` or `failed` into
inspection and write an authenticated local sidecar endpoint used by the
supervisor to poll the drain state. The endpoint exposes only a count and
requires the existing runtime control proof.

- [ ] **Step 6: Verify and commit Task 8**

Run:

```bash
python3 -m pytest tests/integration/test_server.py tests/unit/test_operations.py tests/unit/test_hook_runtime.py -q
git diff --check
```

Commit:

```bash
git add hermes_feishu_card/server.py tests/integration/test_server.py
git commit -m "feat: launch confirmed Hermes update jobs"
```

---

### Task 9: CLI Provisioning, Setup, Doctor, and Installer Integration

**Files:**
- Modify: `hermes_feishu_card/cli.py`
- Modify: `install.sh`
- Modify: `install.ps1`
- Modify: `tests/integration/test_cli.py`
- Modify: `tests/integration/test_cli_install.py`
- Modify: `tests/unit/test_install_scripts.py`
- Modify: `tests/unit/test_diagnostics.py`

**Interfaces:**
- Consumes: artifact store, runtime provisioner, supervisor runner.
- Produces: `maintenance provision/status/run/resume`, setup provisioning, doctor maintenance block.

- [ ] **Step 1: Write failing CLI parser and status tests**

```python
def test_maintenance_status_is_read_only(capsys, tmp_path):
    code = main(["maintenance", "status", "--state-dir", str(tmp_path)])
    assert code == 1
    assert json.loads(capsys.readouterr().out)["available"] is False


def test_maintenance_run_requires_private_job(monkeypatch, public_job):
    assert main(["maintenance", "run", "--job", str(public_job)]) == 1
```

- [ ] **Step 2: Implement maintenance CLI**

Parser:

```text
maintenance provision --wheel PATH [--state-dir PATH]
maintenance status [--state-dir PATH] [--json]
maintenance run --job PATH
maintenance resume --job PATH
```

`provision` validates/stages the wheel before creating the runtime. `run` and
`resume` call the same evidence-driven runner; resume never forces a phase.

- [ ] **Step 3: Write failing setup-provisioning tests**

```python
def test_setup_stages_exact_install_spec_wheel_and_keeps_normal_install_success(
    setup_environment, monkeypatch
):
    monkeypatch.setenv("HFC_INSTALL_SPEC", setup_environment.install_spec)
    result = main(
        [
            "setup",
            "--hermes-dir", str(setup_environment.hermes_root),
            "--config", str(setup_environment.config_path),
            "--env-file", str(setup_environment.env_file),
            "--yes",
        ]
    )
    assert result == 0
    assert inspect_runtime(setup_environment.maintenance_paths).available is True


def test_setup_reports_unavailable_maintenance_without_breaking_hfc(
    setup_environment, wheel_builder, capsys, monkeypatch
):
    monkeypatch.setenv("HFC_INSTALL_SPEC", setup_environment.install_spec)
    wheel_builder.returncode = 1
    code = main(
        [
            "setup",
            "--hermes-dir", str(setup_environment.hermes_root),
            "--config", str(setup_environment.config_path),
            "--env-file", str(setup_environment.env_file),
            "--yes",
        ]
    )
    assert code == 0
    assert "automatic update: unavailable" in capsys.readouterr().out
```

- [ ] **Step 4: Implement best-effort setup provisioning**

When `HFC_INSTALL_SPEC` is non-empty, build an exact wheel into a private
temporary directory:

```text
<setup-python> -m pip wheel --no-deps --wheel-dir <private-temp> <install-spec>
```

Validate/stage/provision it and remove only the task-created temporary
directory. A provisioning failure does not roll back normal HFC setup; it
prints an exact local retry command.

- [ ] **Step 5: Update shell and PowerShell installer tests and scripts**

Both installers continue exporting `HFC_INSTALL_SPEC` into the setup process.
They do not resolve a second version for maintenance. Tests assert the selected
tag/spec reaches setup unchanged and no secret is written into arguments.

- [ ] **Step 6: Add doctor maintenance report**

`doctor --json` adds:

```json
{
  "maintenance": {
    "status": "ready|unavailable|busy|stale",
    "artifact_version": "4.2.0",
    "artifact_integrity": "verified|failed|missing",
    "runtime": "independent|invalid|missing",
    "active_job": "none|running|stale",
    "recovery_command": "allowlisted local command"
  }
}
```

Card-safe diagnostics omit paths and hashes. Text doctor prints the same stable
state and recovery command.

- [ ] **Step 7: Verify and commit Task 9**

Run:

```bash
python3 -m pytest tests/integration/test_cli.py tests/integration/test_cli_install.py tests/unit/test_install_scripts.py tests/unit/test_diagnostics.py -q
git diff --check
```

Commit:

```bash
git add hermes_feishu_card/cli.py install.sh install.ps1 tests/integration/test_cli.py tests/integration/test_cli_install.py tests/unit/test_install_scripts.py tests/unit/test_diagnostics.py
git commit -m "feat: provision update maintenance during setup"
```

---

### Task 10: Version, Documentation, and Acceptance Coverage

**Files:**
- Modify: `pyproject.toml`
- Modify: `hermes_feishu_card/__init__.py`
- Modify: `README.md`
- Modify: `README.en.md`
- Modify: `CHANGELOG.md`
- Modify: `docs/wiki/README.md`
- Modify: `docs/wiki/event-flow.md`
- Modify: `docs/wiki/maintenance-guide.md`
- Modify: `docs/wiki/feishu-acceptance.md`
- Create: `docs/release-notes-v4.2.0.md`
- Modify: `tests/unit/test_docs.py`
- Modify: `tests/unit/test_package_metadata.py`

**Interfaces:**
- Documents all implemented behavior; no new runtime interface.

- [ ] **Step 1: Write failing version and documentation assertions**

Assert:

- package metadata and `__version__` are `4.2.0`;
- README states private-chat-only and same-HFC-version behavior;
- group `/update` remains native;
- release notes list independent runtime, confirmation, and recovery limits;
- maintenance guide adds the new hot files and focused test matrix;
- Feishu acceptance includes one-card progress, initiator-only confirmation,
  temporary service interruption, and final runtime readiness.

- [ ] **Step 2: Run docs/version tests and verify RED**

```bash
python3 -m pytest tests/unit/test_docs.py tests/unit/test_package_metadata.py -q
```

- [ ] **Step 3: Update version and documentation**

Use `4.2.0` consistently. Do not claim Windows/Linux/macOS behavior beyond what
platform tests prove. State that automatic update availability is optional and
normal HFC installation remains usable when provisioning fails.

- [ ] **Step 4: Run focused hot-area tests**

```bash
python3 -m pytest \
  tests/unit/test_maintenance_store.py \
  tests/unit/test_maintenance_update.py \
  tests/unit/test_maintenance_process.py \
  tests/unit/test_maintenance_card.py \
  tests/integration/test_maintenance_runner.py \
  tests/unit/test_hook_runtime.py \
  tests/unit/test_operations.py \
  tests/integration/test_server.py \
  tests/integration/test_cli.py \
  tests/integration/test_cli_install.py \
  tests/unit/test_install_scripts.py \
  tests/unit/test_diagnostics.py \
  tests/unit/test_docs.py \
  tests/unit/test_package_metadata.py -q
```

- [ ] **Step 5: Commit Task 10**

```bash
git add pyproject.toml hermes_feishu_card/__init__.py README.md README.en.md CHANGELOG.md docs/wiki/README.md docs/wiki/event-flow.md docs/wiki/maintenance-guide.md docs/wiki/feishu-acceptance.md docs/release-notes-v4.2.0.md tests/unit/test_docs.py tests/unit/test_package_metadata.py
git commit -m "docs: prepare HFC 4.2.0 update workflow"
```

---

### Task 11: Full Verification and Branch Review

**Files:**
- Review all changes since `origin/main`.

**Interfaces:**
- No new interfaces; this task validates the complete feature.

- [ ] **Step 1: Run the complete test suite**

```bash
python3 -m pytest -q
```

Expected: all tests pass with zero failures.

- [ ] **Step 2: Run repository and package gates**

```bash
git diff --check origin/main...HEAD
python3 -m build
```

Create a temporary virtual environment outside the checkout, install the wheel,
then verify:

```text
hermes_feishu_card.__version__ == "4.2.0"
Path(hermes_feishu_card.__file__) is below that environment's site-packages
```

- [ ] **Step 3: Run a disposable end-to-end update simulation**

Use a temporary fake Hermes checkout, fake `hermes` executable, fake Feishu
PATCH boundary, and replacement virtual environment. Confirm:

- one confirmation creates one job;
- group requests call original behavior;
- unrelated tracked changes block before mutation;
- untracked files survive;
- update replaces checkout/runtime;
- exact cached HFC wheel is installed;
- hooks are restored;
- final health becomes ready/healthy;
- the original card receives the success state.

- [ ] **Step 4: Review the complete diff**

```bash
git status --short --branch
git diff --stat origin/main...HEAD
git diff --check origin/main...HEAD
git log --oneline --decorate origin/main..HEAD
```

Check every design acceptance criterion against code/tests and record any
remaining real-Feishu or platform smoke that cannot be performed locally.

- [ ] **Step 5: Use `superpowers:finishing-a-development-branch`**

Re-run its required verification, present the safe branch completion choices,
and do not push, merge, tag, or publish without Bailey's explicit approval.
