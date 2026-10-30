# V3.9.0 Operations, Reliability, and Calm Card UX Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a zero-extra-configuration operations and reliability release that safely repairs verified Hermes hook damage, validates profile routing, cleans long-running state, improves status accuracy, and adds restrained interactive operations cards without changing normal card layout or footer behavior.

**Architecture:** Extract pure recovery planning, structured diagnostics, profile environment editing, lifecycle policy, status classification, and operations state into focused modules. Keep `cli.py`, `server.py`, and `hook_runtime.py` as adapters around those modules; keep all Hermes source mutation inside the installer/recovery boundary and route Feishu actions through the existing CardKit callback/WebSocket paths.

**Tech Stack:** Python 3.9+, stdlib dataclasses/hashlib/pathlib/asyncio/subprocess, aiohttp server, PyYAML config, Feishu CardKit JSON, pytest, shell/PowerShell installers.

## Global Constraints

- Python remains 3.9+ and no new mandatory runtime dependency is introduced.
- Existing single-profile and multi-profile configuration remains valid.
- Existing installer environment variables remain valid; explicit installer arguments have higher precedence.
- `doctor` is always read-only.
- `setup` and `install` automatically execute only an evidence-backed safe recovery plan; `--no-repair` disables that behavior.
- No installed Hermes file is edited manually; patching and recovery remain inside HFC installer modules.
- Unknown Hermes runtime paths remain fail-open, while uncertain source-file mutation fails closed.
- Normal card header/body/timeline/attachments/divider/footer order remains unchanged.
- Existing configured footer fields and ordering remain unchanged.
- No operator allowlist or operator-id configuration is introduced.
- Every Feishu operations click reuses Hermes' existing admission check.
- Group mutation confirmation must use the same operator as the command initiator or first mutation click; private chat does not compare operator identity between confirmation steps.
- Operations output never exposes secrets, raw chat/open/message identifiers, operator identity, or complete local paths.
- The existing-container Docker workflow is supported; no Hermes + HFC combined image is published.
- General Agent continue/retry/cancel actions remain outside V3.9.0.
- PR #84 / @Zanetach receives explicit credit for adopted profile-environment and progress-status directions.

## File Map

- Create `hermes_feishu_card/install/recovery.py`: recovery evidence, planning, fingerprinting, locked atomic execution, quarantine retention.
- Create `hermes_feishu_card/diagnostics.py`: typed findings/report, redaction, route-chain diagnostics, legacy JSON compatibility.
- Create `hermes_feishu_card/install/envfile.py`: atomic HFC-owned `.env` updates preserving unknown keys and comments.
- Create `hermes_feishu_card/lifecycle.py`: pure session/controller retention policy and cleanup decisions.
- Create `hermes_feishu_card/status.py`: explicit display-status normalization and conservative progress-handoff inference.
- Create `hermes_feishu_card/operations.py`: operation records, expiring tokens, group ownership, action transitions, operations-card rendering.
- Modify `hermes_feishu_card/cli.py`: delegate doctor/repair/setup/profile options to focused modules.
- Modify `hermes_feishu_card/server.py`: structured doctor cards, operations action dispatch, background execution, lifecycle cleanup.
- Modify `hermes_feishu_card/hook_runtime.py`: command operator/chat context and WebSocket-native operations action forwarding.
- Modify `hermes_feishu_card/session.py`: display-status metadata and lifecycle timestamps.
- Modify `hermes_feishu_card/render.py`: status adapter only; preserve all normal card element and footer ordering.
- Modify `hermes_feishu_card/metrics.py`: bounded cleanup/recovery/profile counters.
- Modify `install.sh`, `install-docker.sh`, `install.ps1`: equivalent explicit argument handling and env precedence.
- Add focused unit tests beside each module and extend existing CLI/server/hook/install integration suites.

---

### Task 1: Evidence-Based Recovery Planning

**Files:**
- Create: `hermes_feishu_card/install/recovery.py`
- Modify: `hermes_feishu_card/install/__init__.py`
- Test: `tests/unit/test_recovery.py`
- Reference: `hermes_feishu_card/cli.py:819-940`
- Reference: `hermes_feishu_card/cli.py:1595-1788`
- Reference: `hermes_feishu_card/install/patcher.py:780-920`

**Interfaces:**
- Consumes: `HermesDetection`, patcher `apply_patch`, `apply_cron_patch`, marker validation, manifest/backup paths and hashes.
- Produces:
  - `RecoveryFinding(code: str, severity: str, message: str)`
  - `RecoveryEvidence(current_text: str, current_sha256: str, backup_text: str | None, backup_sha256: str, manifest: dict[str, object] | None, marker_error: str)`
  - `RecoveryClassification(state: str, executable: bool, fingerprint_parts: dict[str, str], actions: tuple[str, ...], findings: tuple[RecoveryFinding, ...])`
  - `RecoveryPlan(root: Path, state: str, executable: bool, fingerprint: str, actions: tuple[str, ...], findings: tuple[RecoveryFinding, ...])`
  - `_read_evidence(detection: HermesDetection) -> RecoveryEvidence`
  - `_classify_evidence(detection: HermesDetection, evidence: RecoveryEvidence) -> RecoveryClassification`
  - `plan_recovery(detection: HermesDetection) -> RecoveryPlan`
  - `sanitize_recovery_plan(plan: RecoveryPlan) -> dict[str, object]`

- [ ] **Step 1: Write the shared installed-state fixture and failing safe-corrupt/refusal tests**

Create `tests/unit/test_recovery.py` with real fixture files:

```python
FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "hermes_v2026_4_23"


@pytest.fixture
def installed_state(tmp_path):
    root = tmp_path / "hermes"
    shutil.copytree(FIXTURE, root)
    detection = detect_hermes(root)
    original = detection.run_py.read_text(encoding="utf-8")
    patched = apply_patch(original, strategy=detection.hook_strategy)
    backup = detection.run_py.with_name("run.py.hermes_feishu_card.bak")
    backup.write_text(original, encoding="utf-8")
    detection.run_py.write_text(patched, encoding="utf-8")
    manifest_path = root / ".hermes_feishu_card_manifest"
    manifest_path.write_text(
        json.dumps(
            {
                "run_py": "gateway/run.py",
                "patched_sha256": sha256(patched.encode("utf-8")).hexdigest(),
                "backup": "gateway/run.py.hermes_feishu_card.bak",
                "backup_sha256": sha256(original.encode("utf-8")).hexdigest(),
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return detection, original, patched, manifest_path


def test_plan_recovery_allows_manifest_owned_corrupt_completion_markers(installed_state):
    detection, _original, patched, manifest_path = installed_state
    corrupt = patched.replace(
        "# HERMES_FEISHU_CARD_COMPLETE_PATCH_END\n", ""
    )
    detection.run_py.write_text(corrupt, encoding="utf-8")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["patched_sha256"] = sha256(corrupt.encode("utf-8")).hexdigest()
    manifest_path.write_text(json.dumps(manifest, sort_keys=True) + "\n", encoding="utf-8")

    plan = plan_recovery(detection)

    assert plan.state == "corrupt_owned"
    assert plan.executable is True
    assert plan.actions == ("restore_verified_backup", "reapply_current_hook")


def test_plan_recovery_refuses_corrupt_markers_after_user_edit(installed_state):
    detection, _original, patched, _manifest_path = installed_state
    detection.run_py.write_text(
        patched.replace("import asyncio", "import asyncio\nUSER_EDIT = True")
        .replace("# HERMES_FEISHU_CARD_COMPLETE_PATCH_END\n", ""),
        encoding="utf-8",
    )

    plan = plan_recovery(detection)

    assert plan.executable is False
    assert any(item.code == "current_hash_mismatch" for item in plan.findings)
```

Also cover verified stale unpatched state, missing backup, backup hash mismatch, manifest missing with removable owned patch, unsupported anchors, cron marker damage, and symlink refusal.

- [ ] **Step 2: Run the focused tests and verify RED**

Run:

```bash
python -m pytest tests/unit/test_recovery.py -q
```

Expected: collection fails because `hermes_feishu_card.install.recovery` does not exist.

- [ ] **Step 3: Implement immutable recovery models and fingerprinting**

Add the concrete public types:

```python
@dataclass(frozen=True)
class RecoveryFinding:
    code: str
    severity: str
    message: str


@dataclass(frozen=True)
class RecoveryPlan:
    root: Path
    state: str
    executable: bool
    fingerprint: str
    actions: tuple[str, ...]
    findings: tuple[RecoveryFinding, ...]


def _fingerprint(parts: dict[str, str]) -> str:
    encoded = json.dumps(parts, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return sha256(encoded).hexdigest()
```

Fingerprint only hashes normalized evidence; never include file contents in serialized output.

- [ ] **Step 4: Implement `plan_recovery` as a pure evidence classifier**

Use exact state names:

```python
KNOWN_STATES = {
    "clean",
    "installed",
    "stale_unpatched",
    "owned_incomplete",
    "corrupt_owned",
}


def plan_recovery(detection: HermesDetection) -> RecoveryPlan:
    evidence = _read_evidence(detection)
    classification = _classify_evidence(detection, evidence)
    return RecoveryPlan(
        root=detection.root,
        state=classification.state,
        executable=classification.executable,
        fingerprint=_fingerprint(classification.fingerprint_parts),
        actions=classification.actions,
        findings=classification.findings,
    )
```

`corrupt_owned` is executable only when current hash equals manifest `patched_sha256`, backup hash equals manifest `backup_sha256`, backup is valid unpatched source, and in-memory reapplication passes syntax/marker validation. A marker error plus mismatched current hash is always refused.

`clean` and `installed` are healthy no-op states: they have no actions and are not
treated as refusals. `stale_unpatched`, `owned_incomplete`, and `corrupt_owned` may
be executable only when their complete state-specific evidence chain passes.

- [ ] **Step 5: Add card-safe serialization and redaction tests**

Assert `sanitize_recovery_plan` returns state, executable, fingerprint prefix, action codes, and finding codes/messages without root path, backup path, raw hashes, or source text.

- [ ] **Step 6: Run recovery and patcher tests**

Run:

```bash
python -m pytest tests/unit/test_recovery.py tests/unit/test_patcher.py -q
```

Expected: all tests pass.

- [ ] **Step 7: Commit the recovery planner**

```bash
git add hermes_feishu_card/install/recovery.py hermes_feishu_card/install/__init__.py tests/unit/test_recovery.py
git commit -m "feat: add evidence-based recovery planning"
```

---

### Task 2: Structured Diagnostics Shared by CLI and Cards

**Files:**
- Create: `hermes_feishu_card/diagnostics.py`
- Modify: `hermes_feishu_card/cli.py:335-1035`
- Modify: `hermes_feishu_card/metrics.py`
- Test: `tests/unit/test_diagnostics.py`
- Test: `tests/integration/test_cli.py`

**Interfaces:**
- Consumes: `RecoveryPlan`, `HermesDetection`, loaded HFC config, optional sidecar health, optional requested profile id.
- Produces:
  - `DiagnosticFinding(code, severity, message, impact, actions)`
  - `DiagnosticReport(status, created_at, config, hermes, install, routing, runtime, findings)`
  - `build_diagnostic_report(config_path: Path, config: dict[str, object], detection: HermesDetection, recovery_plan: RecoveryPlan, *, health: dict[str, object] | None = None, profile_id: str = "", profile_source: str = "", event_url: str = "") -> DiagnosticReport`
  - `diagnostic_fingerprint(report: DiagnosticReport) -> str`
  - `DiagnosticReport.to_dict(card_safe: bool = False) -> dict[str, object]`
  - `format_diagnostic_text(report: DiagnosticReport, explain: bool) -> str`
  - `_report_dict(report: DiagnosticReport) -> dict[str, object]`
  - `_card_safe_report(data: dict[str, object]) -> dict[str, object]`

- [ ] **Step 1: Write failing report compatibility and redaction tests**

```python
def test_card_safe_report_redacts_paths_and_route_ids(tmp_path):
    report = DiagnosticReport(
        status="warning",
        created_at=100.0,
        config={"path": str(tmp_path / "private" / "config.yaml")},
        hermes={"root": str(tmp_path / "private" / "hermes")},
        streaming={"status": "enabled"},
        install_state={"status": "installed"},
        routing={
            "chat_id": "oc_secret_chat",
            "operator_open_id": "ou_secret_operator",
        },
        runtime={},
        findings=(),
    )

    payload = report.to_dict(card_safe=True)
    serialized = json.dumps(payload, ensure_ascii=False)

    assert "oc_secret_chat" not in serialized
    assert "ou_secret_operator" not in serialized
    assert str(tmp_path) not in serialized
    assert payload["routing"]["chat_id_hash"]


def test_cli_report_keeps_existing_top_level_doctor_contract():
    report = DiagnosticReport(
        status="ok",
        created_at=100.0,
        config={},
        hermes={},
        streaming={},
        install_state={},
        routing={},
        runtime={},
        findings=(),
    )
    payload = report.to_dict()
    assert set(("status", "config", "hermes", "streaming", "install_state")) <= payload.keys()
```

Add profile mismatch findings for missing identity, unknown profile, endpoint mismatch, missing credentials, unknown bot, and fallback route.

- [ ] **Step 2: Run diagnostics tests and verify RED**

Run:

```bash
python -m pytest tests/unit/test_diagnostics.py -q
```

Expected: import failure for `hermes_feishu_card.diagnostics`.

- [ ] **Step 3: Implement typed findings and report serialization**

```python
@dataclass(frozen=True)
class DiagnosticFinding:
    code: str
    severity: str
    message: str
    impact: str = ""
    actions: tuple[str, ...] = ()


@dataclass(frozen=True)
class DiagnosticReport:
    status: str
    created_at: float
    config: dict[str, object]
    hermes: dict[str, object]
    streaming: dict[str, object]
    install_state: dict[str, object]
    routing: dict[str, object]
    runtime: dict[str, object]
    findings: tuple[DiagnosticFinding, ...]

    @property
    def fingerprint(self) -> str:
        return diagnostic_fingerprint(self)

    def to_dict(self, card_safe: bool = False) -> dict[str, object]:
        data = _report_dict(self)
        data["fingerprint"] = self.fingerprint
        return _card_safe_report(data) if card_safe else data
```

Use stable finding codes because operations cards and tests consume them. Build the
fingerprint from a canonical report payload that excludes `created_at`, raw paths,
raw identifiers, and secrets, so an unchanged diagnosis remains stable while a
changed recovery/profile state invalidates mutation actions.

- [ ] **Step 4: Implement route-chain diagnostics**

Expose this exact ordered data:

```python
def build_route_chain(
    config: dict[str, object],
    *,
    profile_id: str,
    profile_source: str,
    event_url: str,
    route: dict[str, object] | None,
) -> dict[str, object]:
    return {
        "profile_id": profile_id,
        "profile_source": profile_source,
        "event_endpoint": _safe_endpoint(event_url),
        "profile_exists": _profile_exists(config, profile_id),
        "credentials_present": _profile_credentials_present(config, profile_id),
        "bot_id": str((route or {}).get("bot_id") or ""),
        "route_reason": str((route or {}).get("reason") or ""),
    }
```

Card-safe serialization must hash or omit all real identifiers.

- [ ] **Step 5: Migrate CLI doctor formatting without changing behavior**

Replace the current dict assembly with `build_diagnostic_report`, then preserve existing JSON keys and text headings. Keep `doctor` free of all repair execution calls.

- [ ] **Step 6: Add metrics fields with dataclass defaults**

Add integer defaults in `SidecarMetrics`:

```python
recovery_plans_available: int = 0
recovery_attempts: int = 0
recovery_successes: int = 0
recovery_refusals: int = 0
profile_mismatches: int = 0
sessions_collected: int = 0
zombie_sessions_collected: int = 0
flush_controllers_collected: int = 0
```

- [ ] **Step 7: Run doctor compatibility tests**

Run:

```bash
python -m pytest tests/unit/test_diagnostics.py tests/integration/test_cli.py -q
```

Expected: all tests pass and existing doctor text/JSON assertions remain green.

- [ ] **Step 8: Commit structured diagnostics**

```bash
git add hermes_feishu_card/diagnostics.py hermes_feishu_card/cli.py hermes_feishu_card/metrics.py tests/unit/test_diagnostics.py tests/integration/test_cli.py
git commit -m "refactor: share structured operations diagnostics"
```

---

### Task 3: Locked Atomic Recovery Execution and Automatic Setup Repair

**Files:**
- Modify: `hermes_feishu_card/install/recovery.py`
- Modify: `hermes_feishu_card/cli.py:145-220`
- Modify: `hermes_feishu_card/cli.py:1480-1788`
- Test: `tests/unit/test_recovery.py`
- Test: `tests/integration/test_cli_install.py`

**Interfaces:**
- Consumes: `plan_recovery(detection)` and an optional expected fingerprint.
- Produces:
  - `RecoveryResult(status, plan, actions, quarantine_name, message)`
  - `RecoveryRefused(ValueError)`
  - `execute_recovery(detection, expected_fingerprint: str | None = None) -> RecoveryResult`
  - `_root_lock(root: Path) -> ContextManager[None]`
  - `_execute_fresh_plan(detection: HermesDetection, plan: RecoveryPlan) -> RecoveryResult`
  - `_first_refusal(plan: RecoveryPlan) -> str`
  - CLI `setup/install --no-repair` behavior.

- [ ] **Step 1: Write failing execution revalidation and atomicity tests**

```python
def test_execute_recovery_replans_and_refuses_stale_fingerprint(installed_state):
    detection, _original, patched, manifest_path = installed_state
    corrupt = patched.replace("# HERMES_FEISHU_CARD_COMPLETE_PATCH_END\n", "")
    detection.run_py.write_text(corrupt, encoding="utf-8")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["patched_sha256"] = sha256(corrupt.encode("utf-8")).hexdigest()
    manifest_path.write_text(json.dumps(manifest, sort_keys=True) + "\n", encoding="utf-8")
    plan = plan_recovery(detection)
    detection.run_py.write_text(
        detection.run_py.read_text(encoding="utf-8") + "\nUSER_EDIT = True\n",
        encoding="utf-8",
    )

    with pytest.raises(RecoveryRefused, match="evidence changed"):
        execute_recovery(detection, expected_fingerprint=plan.fingerprint)


def test_execute_recovery_replaces_once_and_keeps_three_quarantines(installed_state):
    detection, _original, patched, manifest_path = installed_state
    for _ in range(4):
        corrupt = patched.replace("# HERMES_FEISHU_CARD_COMPLETE_PATCH_END\n", "")
        detection.run_py.write_text(corrupt, encoding="utf-8")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["patched_sha256"] = sha256(corrupt.encode("utf-8")).hexdigest()
        manifest_path.write_text(
            json.dumps(manifest, sort_keys=True) + "\n", encoding="utf-8"
        )
        result = execute_recovery(detection)
        assert result.status == "repaired"
    assert len(list(detection.run_py.parent.glob("run.py.hfc-corrupt-*"))) == 3
```

Add same-process and subprocess concurrent execution, injected atomic-write failure,
manifest-write failure rollback, cron repair, and idempotent already-repaired tests.

- [ ] **Step 2: Run focused execution tests and verify RED**

Run:

```bash
python -m pytest tests/unit/test_recovery.py -q
```

Expected: failure because `execute_recovery` and `RecoveryRefused` do not exist.

- [ ] **Step 3: Implement root-scoped locking and fresh planning**

```python
_PROCESS_LOCKS: dict[str, threading.Lock] = {}
_PROCESS_LOCKS_GUARD = threading.Lock()


def execute_recovery(
    detection: HermesDetection,
    expected_fingerprint: str | None = None,
) -> RecoveryResult:
    with _root_lock(detection.root):
        fresh = plan_recovery(detection)
        if expected_fingerprint and fresh.fingerprint != expected_fingerprint:
            raise RecoveryRefused("recovery evidence changed; rerun diagnosis")
        if not fresh.executable:
            raise RecoveryRefused(_first_refusal(fresh))
        return _execute_fresh_plan(detection, fresh)
```

`_root_lock` combines the process-local mutex with an OS-backed lock file under
the Hermes root (`fcntl.flock` on POSIX and `msvcrt.locking` on Windows). This
serializes CLI and sidecar recovery attempts across processes. Lock acquisition
has a bounded timeout and never deletes another process's lock file.

- [ ] **Step 4: Build and validate repaired files before replacing**

Read the verified backup, apply current gateway/cron patches in memory, run `ast.parse`, validate owned markers, write temporary files in the target directory, then atomically replace. Quarantine the pre-repair current file and cap matching snapshots at three.

- [ ] **Step 5: Route CLI `repair` through the new executor**

Remove duplicated repair mutation from `cli.py`; keep compatibility wrappers only where existing tests import helpers. Format `RecoveryResult.actions` as current human-readable repair output.

- [ ] **Step 6: Make setup/install auto-repair safe plans by default**

Add parser options:

```python
setup.add_argument("--no-repair", action="store_true")
install.add_argument("--no-repair", action="store_true")
```

Before `_run_install` validates existing state, call `plan_recovery`. If
`plan.actions` is nonempty, execute it only when `plan.executable` and repair is
not disabled. A nonempty refused plan remains a clear install failure and never
clears state silently; healthy no-op states continue normally.

- [ ] **Step 7: Add the exact #82 corrupt completion marker fixture**

Create an integration fixture with valid manifest hashes, valid backup, and a missing completion end marker. Assert `setup --yes` repairs it, installs the current hook, starts sidecar through a fake runner, and final doctor reports `installed`.

- [ ] **Step 8: Run recovery/install suites**

Run:

```bash
python -m pytest tests/unit/test_recovery.py tests/unit/test_patcher.py tests/integration/test_cli_install.py -q
```

Expected: all tests pass.

- [ ] **Step 9: Commit atomic automatic recovery**

```bash
git add hermes_feishu_card/install/recovery.py hermes_feishu_card/cli.py tests/unit/test_recovery.py tests/integration/test_cli_install.py
git commit -m "feat: auto-repair verified hook damage"
```

---

### Task 4: Installer Arguments, `.env` Preservation, and Profile Route Validation

**Files:**
- Create: `hermes_feishu_card/install/envfile.py`
- Modify: `hermes_feishu_card/cli.py:74-220`
- Modify: `install.sh`
- Modify: `install-docker.sh`
- Modify: `install.ps1`
- Modify: `docs/user-guide.md`
- Modify: `docs/user-guide.en.md`
- Test: `tests/unit/test_envfile.py`
- Test: `tests/unit/test_install_scripts.py`
- Test: `tests/integration/test_cli.py`
- Test: `tests/integration/test_cli_install.py`

**Interfaces:**
- Consumes: explicit CLI/script args, process env, selected env file, HFC config/profile registry.
- Produces:
  - `update_hfc_env(path: Path, updates: dict[str, str]) -> None`
  - `setup --env-file PATH --profile-id PROFILE_ID --event-url URL`
  - `doctor --profile-id PROFILE_ID --explain`
  - equivalent shell/Docker/PowerShell installer arguments.

- [ ] **Step 1: Preserve PR #84 / @Zanetach as a merge parent**

Fetch the contributor commit and record it in branch history without taking the stale/conflicting tree verbatim:

```bash
git fetch origin pull/84/head:refs/heads/pr-84-contributor
git merge --no-ff -s ours pr-84-contributor \
  -m "Merge pull request #84 from Zanetach/codex/feishu-card-status-routing" \
  -m "Preserve @Zanetach's profile-env and progress-status contribution; refresh implementation against current main in V3.9.0."
```

Expected: the merge commit has the current implementation branch and PR #84 commit `5c0ade5` as parents, while the working tree remains unchanged for test-first implementation. Do not push until all V3.9.0 gates pass.

- [ ] **Step 2: Write failing `.env` preservation tests**

```python
def test_update_hfc_env_preserves_comments_unknown_keys_and_order(tmp_path):
    env_path = tmp_path / ".env"
    env_path.write_text(
        "# local browser\nAGENT_BROWSER_PATH=/Applications/Chrome\n"
        "HERMES_FEISHU_CARD_PROFILE_ID=old\n",
        encoding="utf-8",
    )

    update_hfc_env(
        env_path,
        {
            "HERMES_FEISHU_CARD_PROFILE_ID": "child",
            "HERMES_FEISHU_CARD_EVENT_URL": "http://127.0.0.1:8766/events",
        },
    )

    text = env_path.read_text(encoding="utf-8")
    assert "# local browser" in text
    assert "AGENT_BROWSER_PATH=/Applications/Chrome" in text
    assert text.count("HERMES_FEISHU_CARD_PROFILE_ID=") == 1
    assert "HERMES_FEISHU_CARD_PROFILE_ID=child" in text
```

Also test quoting, CRLF preservation where possible, atomic failure, invalid key, newline injection, and empty values.

- [ ] **Step 3: Run envfile tests and verify RED**

Run:

```bash
python -m pytest tests/unit/test_envfile.py -q
```

Expected: import failure for `hermes_feishu_card.install.envfile`.

- [ ] **Step 4: Implement the HFC-owned env editor**

Allow only:

```python
HFC_ENV_KEYS = {
    "HERMES_FEISHU_CARD_PROFILE_ID",
    "HERMES_FEISHU_CARD_EVENT_URL",
}
```

Reject newline-containing values. Replace existing owned key lines in place, append missing keys, preserve all unknown lines/comments, and use the project's atomic text-write helper.

- [ ] **Step 5: Add setup/doctor profile arguments and validation**

Validate profile ids with the same runtime identity constraints. Validate the
event URL as an HTTP(S) sidecar endpoint ending in `/events`, with a hostname and
without credentials, query, or fragment; allow loopback,
`host.docker.internal`, and Docker Compose service hostnames. Update the selected
`.env`, then rebuild the diagnostic report. Unknown profile ids produce
`profile_unknown`; missing credentials produce `profile_credentials_missing`;
endpoint/config port differences produce `event_endpoint_mismatch`.

- [ ] **Step 6: Add explicit shell and Docker arguments**

Support:

```bash
install.sh --config PATH --env-file PATH --version VERSION \
  --profile-id PROFILE_ID --event-url URL --no-repair

install-docker.sh --config PATH --env-file PATH --version VERSION \
  --profile-id PROFILE_ID --event-url URL --no-repair
```

Translate arguments into normalized `HFC_*` variables before package installation. Preserve precedence: args > process env > env file > defaults.

- [ ] **Step 7: Add equivalent PowerShell parameters**

Use this concrete parameter block and retain env defaults when parameters are absent:

```powershell
param(
  [string]$Config = $env:HFC_CONFIG,
  [string]$EnvFile = $env:HFC_ENV_FILE,
  [string]$Version = $env:HFC_VERSION,
  [string]$ProfileId = $env:HERMES_FEISHU_CARD_PROFILE_ID,
  [string]$EventUrl = $env:HERMES_FEISHU_CARD_EVENT_URL,
  [switch]$NoRepair
)
```

Keep existing `irm https://raw.githubusercontent.com/baileyh8/hermes-feishu-streaming-card/main/install.ps1 | iex` compatibility by treating blank parameters as the current script defaults.

- [ ] **Step 8: Extend script parser tests**

Add tests that execute shell installers against fake `curl`/Python commands and parse `install.ps1`. Assert all three installers forward identical config/env/version/profile/event/no-repair values and never source unknown env keys.

- [ ] **Step 9: Add main/child route-chain integration tests**

Build a config with `profiles.default` and `profiles.child`; assert setup writes only selected HFC env keys and doctor reports the exact profile/endpoint/bot stages without exposing credentials.

- [ ] **Step 10: Run installer/profile suites**

Run:

```bash
python -m pytest tests/unit/test_envfile.py tests/unit/test_install_scripts.py tests/unit/test_config.py tests/integration/test_cli.py tests/integration/test_cli_install.py -q
```

Expected: all tests pass.

- [ ] **Step 11: Commit installer and profile UX**

```bash
git add hermes_feishu_card/install/envfile.py hermes_feishu_card/cli.py install.sh install-docker.sh install.ps1 docs/user-guide.md docs/user-guide.en.md tests/unit/test_envfile.py tests/unit/test_install_scripts.py tests/integration/test_cli.py tests/integration/test_cli_install.py
git commit -m "feat: add profile-aware installer workflow"
```

---

### Task 5: Bounded Runtime Lifecycle Cleanup

**Files:**
- Create: `hermes_feishu_card/lifecycle.py`
- Modify: `hermes_feishu_card/session.py`
- Modify: `hermes_feishu_card/server.py:35-160`
- Modify: `hermes_feishu_card/server.py:1200-1260`
- Modify: `hermes_feishu_card/metrics.py`
- Test: `tests/unit/test_lifecycle.py`
- Test: `tests/integration/test_server.py`

**Interfaces:**
- Consumes: session status/timestamps, active interaction, Feishu binding presence, controller closed state.
- Produces:
  - `CleanupPolicy(session_retention_seconds=3600, zombie_grace_seconds=120, history_limit=50)`
  - `CleanupResult(session_keys: tuple[str, ...], reasons: tuple[str, ...], controllers_collected: int)`
  - `session_cleanup_reason(...) -> str | None`
  - `cleanup_runtime_state(app, now: float) -> CleanupResult`
  - one bounded periodic server task plus post-terminal cleanup.

- [ ] **Step 1: Write failing pure lifecycle predicate tests**

```python
def test_completed_session_is_collected_after_retention():
    session = CardSession(conversation_id="oc_1", message_id="om_1", chat_id="oc_1")
    session.status = "completed"
    session.updated_at = 100.0
    reason = session_cleanup_reason(
        session,
        now=3701.0,
        has_card=True,
        has_inflight_send=False,
        controller_closed=True,
        policy=CleanupPolicy(),
    )
    assert reason == "terminal_retention_expired"


def test_empty_session_waits_for_zombie_grace_and_never_collects_active_interaction():
    session = CardSession(conversation_id="oc_1", message_id="om_1", chat_id="oc_1")
    session.updated_at = 100.0
    assert session_cleanup_reason(
        session,
        now=219.0,
        has_card=False,
        has_inflight_send=False,
        controller_closed=False,
        policy=CleanupPolicy(),
    ) is None
    session.active_interaction = InteractionState(
        interaction_id="interaction-1",
        kind="approval",
        prompt="允许吗？",
    )
    assert session_cleanup_reason(
        session,
        now=500.0,
        has_card=False,
        has_inflight_send=False,
        controller_closed=False,
        policy=CleanupPolicy(),
    ) is None
```

Cover active sends, nonempty text, tool progress, sequence progress, card binding, thinking sessions, failed sessions, and boundary timestamps.

- [ ] **Step 2: Run lifecycle tests and verify RED**

Run:

```bash
python -m pytest tests/unit/test_lifecycle.py -q
```

Expected: import failure for `hermes_feishu_card.lifecycle`.

- [ ] **Step 3: Add `created_at` and `updated_at` to `CardSession`**

Use `time.time` defaults and update `updated_at` only when an event is accepted/applied. Do not change session serialization exposed to cards.

- [ ] **Step 4: Implement pure cleanup decisions and coordinated deletion**

`cleanup_runtime_state` must remove a session key from sessions, aliases pointing to the key, message locks, update locks, Feishu message ids, bot ids, card configs, send state, last-update state, and flush controllers in one function. Hash any recorded key before adding it to bounded diagnostics.

- [ ] **Step 5: Remove closed controllers immediately after terminal work**

After terminal drain and post-lock card update completes, pop only the controller for that canonical key if it is still the same closed instance. This avoids deleting a newly created controller for a reused topic `message_id`.

- [ ] **Step 6: Add a bounded periodic cleanup task**

Start one task during app startup, wait 60 seconds between scans, and cancel/await it during app cleanup. Do not scan all sessions on every delta.

- [ ] **Step 7: Add server integration tests**

Use a fake clock or direct cleanup call to prove terminal state, aliases, locks, card maps, and controllers disappear together; active interactions and in-flight sends remain; history stops at 50; metrics increment exactly once.

- [ ] **Step 8: Run lifecycle/server suites**

Run:

```bash
python -m pytest tests/unit/test_lifecycle.py tests/unit/test_session.py tests/unit/test_runner.py tests/integration/test_server.py -q
```

Expected: all tests pass.

- [ ] **Step 9: Commit runtime cleanup**

```bash
git add hermes_feishu_card/lifecycle.py hermes_feishu_card/session.py hermes_feishu_card/server.py hermes_feishu_card/metrics.py tests/unit/test_lifecycle.py tests/integration/test_server.py
git commit -m "feat: bound sidecar runtime lifecycle state"
```

---

### Task 6: Explicit-First Status Semantics Without Layout or Footer Changes

**Files:**
- Create: `hermes_feishu_card/status.py`
- Modify: `hermes_feishu_card/events.py`
- Modify: `hermes_feishu_card/session.py:150-215`
- Modify: `hermes_feishu_card/render.py:50-150`
- Modify: `hermes_feishu_card/hook_runtime.py:3450-3660`
- Modify: `config.yaml.example`
- Test: `tests/unit/test_status.py`
- Test: `tests/unit/test_session.py`
- Test: `tests/unit/test_render.py`
- Test: `tests/unit/test_hook_runtime.py`

**Interfaces:**
- Consumes: event `data.display_status`, session status/text, configured marker pairs.
- Produces:
  - `normalize_display_status(value: object) -> str`
  - `infer_progress_handoff(answer: str, config: StatusConfig) -> bool`
  - `DisplayStatus(value: str, source: str)`
  - `resolve_display_status(session: CardSession, config: StatusConfig) -> DisplayStatus`
  - `CardSession.display_status` and `CardSession.display_status_source`.

- [ ] **Step 1: Write failing explicit-priority and false-positive tests**

```python
def test_explicit_completed_wins_over_progress_words():
    session = CardSession(conversation_id="oc_1", message_id="om_1", chat_id="oc_1")
    session.status = "completed"
    session.answer_text = "正在分析这一方法的历史影响，结论如下。"
    session.display_status = "completed"
    status = resolve_display_status(session, StatusConfig.defaults())
    assert status.value == "completed"
    assert status.source == "explicit"


def test_inference_requires_active_and_future_signals():
    config = StatusConfig.defaults()
    assert infer_progress_handoff("正在分析，请稍等", config) is False
    assert infer_progress_handoff("数据收集中，数据到位后我会继续生成报告", config) is True
```

Add English pairs, empty answer, failed session, pending interaction, explicit invalid value, and completed final-answer cases containing generic progress vocabulary.

- [ ] **Step 2: Run status tests and verify RED**

Run:

```bash
python -m pytest tests/unit/test_status.py -q
```

Expected: import failure for `hermes_feishu_card.status`.

- [ ] **Step 3: Implement exact status values and conservative paired inference**

```python
DISPLAY_STATUSES = {"thinking", "in_progress", "waiting", "completed", "failed"}


@dataclass(frozen=True)
class StatusConfig:
    active_markers: tuple[str, ...]
    future_markers: tuple[str, ...]


def infer_progress_handoff(answer: str, config: StatusConfig) -> bool:
    text = normalize_stream_text(answer).strip().lower()
    return bool(text) and any(x in text for x in config.active_markers) and any(
        x in text for x in config.future_markers
    )
```

One marker group alone is never sufficient.

- [ ] **Step 4: Carry explicit status through event/session data**

Accept optional `data.display_status`, normalize it in session application, and record source as `explicit`, `inferred`, or `session`. Do not add a new required event field.

- [ ] **Step 5: Adapt `_render_status` only**

Map resolved display status to existing subtitles/templates. Do not change `render_card` element assembly or `_render_footer`.

- [ ] **Step 6: Add normal-card snapshot guards**

Assert completed and failed cards without operations data have the exact same element ids/order and configured footer content as V3.8.18. Assert only the header status changes for a progress handoff.

- [ ] **Step 7: Add configuration defaults and docs comments**

Add optional status marker settings under `card` with conservative Chinese/English paired defaults. Existing configs without the section use defaults.

- [ ] **Step 8: Run status/render/runtime suites**

Run:

```bash
python -m pytest tests/unit/test_status.py tests/unit/test_events.py tests/unit/test_session.py tests/unit/test_render.py tests/unit/test_hook_runtime.py -q
```

Expected: all tests pass.

- [ ] **Step 9: Commit status semantics and PR #84 refresh**

```bash
git add hermes_feishu_card/status.py hermes_feishu_card/events.py hermes_feishu_card/session.py hermes_feishu_card/render.py hermes_feishu_card/hook_runtime.py config.yaml.example tests/unit/test_status.py tests/unit/test_session.py tests/unit/test_render.py tests/unit/test_hook_runtime.py
git commit -m "feat: add explicit-first card status semantics"
```

---

### Task 7: Interactive Operations Cards Across HTTP and WebSocket

**Files:**
- Create: `hermes_feishu_card/operations.py`
- Modify: `hermes_feishu_card/server.py:80-330`
- Modify: `hermes_feishu_card/hook_runtime.py:480-590`
- Modify: `hermes_feishu_card/hook_runtime.py:1980-2240`
- Modify: `hermes_feishu_card/config.py`
- Test: `tests/unit/test_operations.py`
- Test: `tests/integration/test_server.py`
- Test: `tests/unit/test_hook_runtime.py`
- Test: `tests/integration/test_hook_runtime_integration.py`

**Interfaces:**
- Consumes: card-safe `DiagnosticReport`, `RecoveryPlan`, `execute_recovery`, Hermes action admission, command chat/operator context.
- Produces:
  - `OperationStore`
  - `OperationRecord`
  - `OperationClaims`
  - `OperationRejected(ValueError)`
  - `OperationStore.complete(operation_id, expected_state, state, result)`
  - `render_operations_card(report, operation, footer) -> dict[str, object]`
  - operations action dispatch through existing `/card/actions`.

- [ ] **Step 1: Write failing operation transition and ownership tests**

```python
def operation_kwargs() -> dict[str, object]:
    return {
        "chat_id": "oc_group",
        "profile_id": "default",
        "report_fingerprint": "report-123",
        "recovery_fingerprint": "recovery-123",
    }


def test_group_repair_confirmation_requires_claimed_operator():
    store = OperationStore(secret=b"test", now=lambda: 100.0)
    operation = store.create(
        group=True, initiator_open_id="ou_owner", **operation_kwargs()
    )
    confirm = store.transition(
        store.token(operation, "repair"),
        action="repair",
        operator_open_id="ou_owner",
        callback_chat_id="oc_group",
        callback_profile_id="default",
    )

    with pytest.raises(OperationRejected, match="different operator"):
        store.transition(
            store.token(confirm, "confirm_repair"),
            action="confirm_repair",
            operator_open_id="ou_other",
            callback_chat_id="oc_group",
            callback_profile_id="default",
        )


def test_private_repair_confirmation_does_not_compare_operators():
    store = OperationStore(secret=b"test", now=lambda: 100.0)
    operation = store.create(
        group=False, initiator_open_id="ou_first", **operation_kwargs()
    )
    confirm = store.transition(
        store.token(operation, "repair"),
        action="repair",
        operator_open_id="ou_first",
        callback_chat_id="oc_group",
        callback_profile_id="default",
    )
    accepted = store.transition(
        store.token(confirm, "confirm_repair"),
        action="confirm_repair",
        operator_open_id="ou_second",
        callback_chat_id="oc_group",
        callback_profile_id="default",
    )
    assert accepted.state == "executing"
```

Also test rejection when a group command has an initiator but a different user makes
the first mutation click; first-click claim when the initiator is absent; missing
group operator identity; expiration at 120 seconds; chat/profile/report/recovery
fingerprint mismatch; duplicate clicks; concurrent executing state; read-only
`details`/`recheck` by another admitted group user; `cancel` transitions; opaque
token contents; and bounded record retention.

- [ ] **Step 2: Run operations tests and verify RED**

Run:

```bash
python -m pytest tests/unit/test_operations.py -q
```

Expected: import failure for `hermes_feishu_card.operations`.

- [ ] **Step 3: Implement operation records, signed tokens, and transitions**

```python
@dataclass(frozen=True)
class OperationClaims:
    operation_id: str
    action: str
    report_fingerprint: str
    expires_at: int


@dataclass
class OperationRecord:
    operation_id: str
    chat_id: str
    profile_id: str
    report_fingerprint: str
    recovery_fingerprint: str
    group: bool
    owner_open_id: str
    state: str
    expires_at: float
    result: dict[str, object] | None = None


def _next_operation_state(state: str, action: str) -> str:
    transitions = {
        ("diagnosed", "details"): "diagnosed",
        ("diagnosed", "recheck"): "diagnosed",
        ("diagnosed", "repair"): "confirm_repair",
        ("confirm_repair", "cancel"): "diagnosed",
        ("confirm_repair", "confirm_repair"): "executing",
        ("repaired", "restart"): "confirm_restart",
        ("confirm_restart", "cancel"): "repaired",
        ("confirm_restart", "confirm_restart"): "restarting",
        ("diagnosed", "dismiss"): "dismissed",
        ("repaired", "dismiss"): "dismissed",
    }
    try:
        return transitions[(state, action)]
    except KeyError as exc:
        raise OperationRejected("invalid operation transition") from exc


class OperationStore:
    def __init__(self, *, secret: bytes, now: Callable[[], float] = time.time,
                 max_records: int = 200):
        self._secret = secret
        self._now = now
        self._max_records = max_records
        self._records: dict[str, OperationRecord] = {}
        self._lock = threading.RLock()

    def create(self, *, chat_id: str, profile_id: str, report_fingerprint: str,
               recovery_fingerprint: str, group: bool,
               initiator_open_id: str = "") -> OperationRecord:
        with self._lock:
            self._prune_locked()
            operation_id = secrets.token_urlsafe(18)
            record = OperationRecord(
                operation_id=operation_id,
                chat_id=chat_id,
                profile_id=profile_id,
                report_fingerprint=report_fingerprint,
                recovery_fingerprint=recovery_fingerprint,
                group=group,
                owner_open_id=initiator_open_id if group else "",
                state="diagnosed",
                expires_at=self._now() + 120.0,
            )
            self._records[operation_id] = record
            self._prune_locked()
            return record

    def _prune_locked(self) -> None:
        cutoff = self._now() - 300.0
        for operation_id, item in list(self._records.items()):
            if item.expires_at < cutoff:
                self._records.pop(operation_id, None)
        while len(self._records) > self._max_records:
            self._records.pop(next(iter(self._records)))

    def token(self, record: OperationRecord, action: str) -> str:
        payload = json.dumps(
            {
                "operation_id": record.operation_id,
                "action": action,
                "report_fingerprint": record.report_fingerprint,
                "expires_at": int(record.expires_at),
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        encoded = base64.urlsafe_b64encode(payload).decode("ascii").rstrip("=")
        scope = sha256(
            f"{record.chat_id}\0{record.profile_id}".encode("utf-8")
        ).hexdigest()
        signing_input = f"{encoded}.{scope}".encode("ascii")
        signature = hmac.new(self._secret, signing_input, sha256).hexdigest()
        return f"{encoded}.{signature}"

    def _verify_token(self, token: str, callback_chat_id: str,
                      callback_profile_id: str) -> tuple[OperationClaims, OperationRecord]:
        encoded, supplied = token.rsplit(".", 1)
        padding = "=" * (-len(encoded) % 4)
        payload = json.loads(base64.urlsafe_b64decode(encoded + padding))
        claims = OperationClaims(
            operation_id=str(payload["operation_id"]),
            action=str(payload["action"]),
            report_fingerprint=str(payload["report_fingerprint"]),
            expires_at=int(payload["expires_at"]),
        )
        record = self._records.get(claims.operation_id)
        if record is None:
            raise OperationRejected("operation expired")
        scope = sha256(
            f"{record.chat_id}\0{record.profile_id}".encode("utf-8")
        ).hexdigest()
        expected = hmac.new(
            self._secret, f"{encoded}.{scope}".encode("ascii"), sha256
        ).hexdigest()
        if not hmac.compare_digest(supplied, expected):
            raise OperationRejected("invalid operation token")
        if callback_chat_id != record.chat_id or callback_profile_id != record.profile_id:
            raise OperationRejected("operation scope mismatch")
        if claims.report_fingerprint != record.report_fingerprint:
            raise OperationRejected("diagnosis changed")
        return claims, record

    def transition(self, token: str, *, action: str, operator_open_id: str,
                   callback_chat_id: str,
                   callback_profile_id: str) -> OperationRecord:
        with self._lock:
            claims, record = self._verify_token(
                token, callback_chat_id, callback_profile_id
            )
            if claims.action != action:
                raise OperationRejected("operation action mismatch")
            if claims.expires_at < self._now() or record.expires_at < self._now():
                raise OperationRejected("operation expired")
            mutation_actions = {
                "repair", "confirm_repair", "restart", "confirm_restart"
            }
            if record.group and action in mutation_actions:
                if not operator_open_id:
                    raise OperationRejected("operator identity required")
                if not record.owner_open_id and action in {"repair", "restart"}:
                    record.owner_open_id = operator_open_id
                elif operator_open_id != record.owner_open_id:
                    raise OperationRejected("different operator")
            record.state = _next_operation_state(record.state, action)
            return record

    def complete(self, operation_id: str, *, expected_state: str, state: str,
                 result: dict[str, object]) -> OperationRecord:
        with self._lock:
            record = self._records.get(operation_id)
            if record is None or record.state != expected_state:
                raise OperationRejected("operation state changed")
            record.state = state
            record.result = dict(result)
            return record
```

Generate the process-local secret with `secrets.token_bytes(32)`; no user
configuration is required. Tokens expose only a random operation id, action,
non-sensitive fingerprints, and expiry. Raw chat/profile ids are HMAC scope input
and server-side record fields, never token payload fields. Keep parsing bounded,
catch malformed input as `OperationRejected`, prune expired/old records under the
same lock, and never render operator identity or internal state codes.

- [ ] **Step 4: Render operations cards with existing layout/footer conventions**

Keep header/body/divider/footer order. Add buttons before the existing divider. `安全修复` appears only for an executable plan; `确认修复` and `确认重启` use primary style; `查看诊断`, `重新检测`, `暂不处理`, and `取消` use secondary/default styles.

- [ ] **Step 5: Add command initiator and chat-type context**

Extend `handle_hfc_command_from_hermes_locals` payload with:

```python
"chat_type": _command_chat_type(local_vars, source_obj, gateway_event_obj),
"operator": _command_operator(local_vars, source_obj, gateway_event_obj),
```

The server stores raw operator id only inside the in-memory `OperationRecord`; diagnostics and card output omit it.

- [ ] **Step 6: Dispatch operations actions through `/card/actions`**

Refactor `_card_actions` to branch on `hfc_action`. Keep `interaction.select`
behavior unchanged; route `operations.select` to an operations handler. Treat the
endpoint as localhost adapter transport in production: it independently verifies
the signed operation token, callback chat/profile scope, report fingerprint,
expiry, and group ownership. `details` renders sanitized findings;
`recheck` builds a fresh report and replacement operation; stale mutation actions
render a stable expired card with a newly signed `recheck` button.

- [ ] **Step 7: Add WebSocket-native forwarding**

Add `operations.select` beside `interaction.select` in
`_hfc_on_feishu_card_action_trigger`. Before forwarding, require
`_hfc_card_operator_allowed`; then forward action value, chat context, operator
identity, profile context, and token to sidecar and return the updated card as the
Feishu callback response. Recognized operations actions, including rejected or
expired ones, are claimed by HFC and never call the native unknown handler;
unrecognized action namespaces retain the existing fallback.

- [ ] **Step 8: Execute repair off the event loop and refresh diagnosis**

For `confirm_repair`, call `execute_recovery` with `asyncio.to_thread`, passing
`OperationRecord.recovery_fingerprint`, not the broader diagnostic fingerprint.
Use `OperationStore.complete` to publish exactly one terminal state, then rebuild
diagnostics and update the same card. Concurrent/duplicate callbacks observe the
current state and never execute repair twice. Increment metrics exactly once.

- [ ] **Step 9: Implement confirmed Gateway restart**

Show restart only when `shutil.which("hermes")` succeeds. On `confirm_restart`, return the callback card first, then schedule:

```python
subprocess.run(
    [hermes_binary, "gateway", "restart"],
    cwd=hermes_root,
    check=False,
    capture_output=True,
    text=True,
    timeout=30,
)
```

Store only return code and sanitized tail output. Recheck after completion;
distinguish repaired/restart-failed from full success. The callback response is
returned before scheduling the subprocess, and completion updates use the same
atomic operation-state guard as repair.

- [ ] **Step 10: Add HTTP/WebSocket integration coverage**

Cover private and group ownership, command initiator binding, first-click claim,
changed operator rejection on both mutation steps, missing operator identity,
read-only clicks by another admitted user, stale/tampered/scope-mismatched tokens,
tokens that do not expose raw chat/profile ids, duplicate and concurrent actions,
recovery refusal after recovery-fingerprint change, callback card updates,
unknown action fallback, recognized-action gray-message suppression, and unchanged
`interaction.select` behavior.

- [ ] **Step 11: Run operations/server/hook suites**

Run:

```bash
python -m pytest tests/unit/test_operations.py tests/integration/test_server.py tests/unit/test_hook_runtime.py tests/integration/test_hook_runtime_integration.py -q
```

Expected: all tests pass.

- [ ] **Step 12: Commit interactive operations cards**

```bash
git add hermes_feishu_card/operations.py hermes_feishu_card/server.py hermes_feishu_card/hook_runtime.py hermes_feishu_card/config.py tests/unit/test_operations.py tests/integration/test_server.py tests/unit/test_hook_runtime.py tests/integration/test_hook_runtime_integration.py
git commit -m "feat: add interactive operations recovery cards"
```

---

### Task 8: Cross-Platform Release Matrix, Documentation, and V3.9.0 Gate

**Files:**
- Modify: `TODO.md`
- Modify: `CHANGELOG.md`
- Modify: `README.md`
- Modify: `README.en.md`
- Modify: `README-install.md`
- Modify: `docs/user-guide.md`
- Modify: `docs/user-guide.en.md`
- Modify: `docs/wiki/maintenance-guide.md`
- Modify: `docs/wiki/event-flow.md`
- Modify: `docs/wiki/feishu-acceptance.md`
- Modify: `docs/release-readiness.md`
- Modify: `docs/release-readiness.en.md`
- Modify: `tests/unit/test_docs.py`
- Modify: `tests/unit/test_package_metadata.py`
- Modify: `pyproject.toml`
- Modify: `hermes_feishu_card/__init__.py`
- Add: `docs/release-notes-v3.9.0.md`

**Interfaces:**
- Consumes: all previous task behavior and test evidence.
- Produces: public V3.9.0 docs, contributor credit, release checklist, real Feishu smoke record, and final release metadata.

- [ ] **Step 1: Write failing documentation/version assertions**

Add assertions for:

```python
assert __version__ == "3.9.0"
assert 'version = "3.9.0"' in pyproject
assert "PR #84" in release_notes
assert "@Zanetach" in release_notes
assert "安全修复" in readme
assert "profile" in install_doc.lower()
assert "group" in acceptance_doc.lower()
```

Also assert release assets and TODO completion entries.

- [ ] **Step 2: Run docs/version tests and verify RED**

Run:

```bash
python -m pytest tests/unit/test_docs.py tests/unit/test_package_metadata.py -q
```

Expected: failures for missing V3.9.0 notes/version references.

- [ ] **Step 3: Update public docs without changing normal card promises**

Document:

- installer explicit arguments and precedence;
- automatic safe repair and `--no-repair`;
- group/private operations ownership behavior;
- profile setup and route-chain diagnosis;
- status semantics and unchanged footer/layout;
- runtime cleanup metrics;
- existing-container Docker boundary;
- CLI fallback when Feishu operations cards are unavailable.

Credit PR #84 / @Zanetach in README contributor lists, CHANGELOG, user guides, TODO, and release notes.

- [ ] **Step 4: Update maintainer and acceptance documentation**

Add recovery planner/executor to hot-file guidance. Add real Feishu smoke cases for private repair, group initiator repair, group changed-operator rejection, recheck, restart, normal footer snapshot, topic, cron, and profile route mismatch.

- [ ] **Step 5: Bump version and create V3.9.0 release notes**

Set both package versions to `3.9.0`. Release notes list the operations/reliability foundation, calm visual behavior, PR #84 contribution, compatibility, install examples, validation, and expected four assets.

- [ ] **Step 6: Run focused cross-platform suites**

Run:

```bash
python -m pytest \
  tests/unit/test_recovery.py \
  tests/unit/test_diagnostics.py \
  tests/unit/test_envfile.py \
  tests/unit/test_install_scripts.py \
  tests/unit/test_lifecycle.py \
  tests/unit/test_status.py \
  tests/unit/test_operations.py \
  tests/integration/test_cli.py \
  tests/integration/test_cli_install.py \
  tests/integration/test_server.py \
  tests/integration/test_hook_runtime_integration.py \
  -q
```

Expected: all focused tests pass.

- [ ] **Step 7: Run the complete automated release gate**

Run:

```bash
python -m pytest -q
git diff --check
```

Expected: zero failures and no diff-check output.

- [ ] **Step 8: Run existing-container Docker smoke**

In a disposable Hermes container fixture, verify fresh install, pinned upgrade, known-safe corrupt-marker auto-repair, refused user edit, main/child profile endpoint mapping, and final doctor. Record only sanitized output in the release checklist.

- [ ] **Step 9: Run real Feishu acceptance**

Using local credentials outside the repository, verify private and group operations cards, group same-operator confirmation, group different-operator rejection, repair result, restart confirmation, ordinary streaming, completed footer, topic update, and cron delivery.

- [ ] **Step 10: Commit V3.9.0 release preparation**

```bash
git add TODO.md CHANGELOG.md README.md README.en.md README-install.md \
  docs/user-guide.md docs/user-guide.en.md docs/wiki docs/release-readiness.md \
  docs/release-readiness.en.md docs/release-notes-v3.9.0.md \
  pyproject.toml hermes_feishu_card/__init__.py \
  tests/unit/test_docs.py tests/unit/test_package_metadata.py
git commit -m "Release v3.9.0 operations and reliability"
```

- [ ] **Step 11: Create and verify the release only after smoke approval**

```bash
git tag -a v3.9.0 -m "Release v3.9.0 operations and reliability"
git push origin main
git push origin v3.9.0
gh run watch --repo baileyh8/hermes-feishu-streaming-card --exit-status
gh release edit v3.9.0 --repo baileyh8/hermes-feishu-streaming-card \
  --title "v3.9.0" --notes-file docs/release-notes-v3.9.0.md
gh release view v3.9.0 --repo baileyh8/hermes-feishu-streaming-card
```

Expected: release-assets succeeds and macOS, Linux, Windows, and checksums assets are present.

## Plan Completion Check

Before implementation is considered complete, map every design acceptance criterion to evidence:

1. #82 safe corrupt fixture: Task 3 integration test and Docker smoke.
2. Unsafe overwrite refusal: Tasks 1 and 3 unit/integration tests.
3. Zero operator configuration: Task 7 operations tests and docs.
4. Existing admission plus two-step confirmation: Task 7 HTTP/WebSocket tests.
5. Group same-operator/private no-comparison behavior: Task 7 unit and real Feishu tests.
6. Exactly-once mutation: Tasks 3 and 7 concurrency tests.
7. Main/child profile mapping: Task 4 CLI integration and Docker smoke.
8. Cross-platform argument parity: Task 4 installer tests.
9. PR #84 status/env contribution and original commit history: Tasks 4, 6, and 8.
10. Unchanged normal layout/footer: Task 6 render snapshots and real Feishu smoke.
11. Bounded runtime state: Task 5 lifecycle/server tests.
12. Redacted operations output: Tasks 1, 2, 5, and 7 redaction tests.
13. Full automation and real smoke: Task 8 release gates.
