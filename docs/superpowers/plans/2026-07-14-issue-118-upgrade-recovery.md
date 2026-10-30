# Issue #118 Hermes Upgrade Recovery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let an operator explicitly accept a verified unpatched `gateway/run.py`/`cron/scheduler.py` replacement after a Hermes upgrade, clear only the stale HFC install artifacts, and reinstall without manually deleting manifest or backup files.

**Architecture:** Keep the default recovery planner fail-closed. Add an `accept_hermes_upgrade` signal that only relaxes the stale-unpatched source-equality check after the current Hermes files parse, expose safe hook capabilities, and the old manifest/backup pair still validates. Thread that signal through planning, fingerprint rechecks, execution, and the `repair`/`install`/`setup` CLI entry points so TOCTOU protections remain intact.

**Tech Stack:** Python 3.9+, `argparse`, AST-based installer recovery, pytest/pytest-asyncio.

## Global Constraints

- Never overwrite the current upgraded Hermes source; only remove stale `.hermes_feishu_card_manifest` and `*.hermes_feishu_card.bak` artifacts before reinstallation.
- Default `repair`, `install`, and `setup` behavior remains fail-closed when current source differs from the verified old backup.
- `--accept-hermes-upgrade` is explicit opt-in and still refuses corrupt/missing backup evidence, invalid manifests, symlinks, unreadable files, invalid Python, unsupported Gateway anchors, or remaining owned patch markers.
- Preserve recovery fingerprint rechecks and atomic rollback behavior.
- Do not edit installed Hermes `gateway/run.py` outside `hermes_feishu_card/install/patcher.py` and the existing installer/recovery write path.

---

### Task 1: Recovery planner opt-in

**Files:**
- Modify: `hermes_feishu_card/install/recovery.py`
- Test: `tests/unit/test_recovery.py`

**Interfaces:**
- Produces: `plan_recovery(detection, *, accept_hermes_upgrade: bool = False) -> RecoveryPlan`
- Produces: `execute_recovery(detection, expected_fingerprint=None, *, accept_hermes_upgrade: bool = False) -> RecoveryResult`
- Consumes: existing `_ManifestChecks`, `_BackupChecks`, `RecoveryEvidence`, and atomic recovery transaction.

- [ ] **Step 1: Write failing planner tests**

Add tests that replace the installed gateway source with valid, supported, unpatched upgraded source and assert:

```python
default_plan = plan_recovery(detection)
assert default_plan.state == "stale_unpatched"
assert default_plan.executable is False

accepted_plan = plan_recovery(detection, accept_hermes_upgrade=True)
assert accepted_plan.state == "stale_unpatched"
assert accepted_plan.executable is True
assert accepted_plan.actions == ("clear_stale_install_state",)
```

Add parallel cron replacement coverage and negative tests proving a changed backup hash and invalid current Python remain refused even with opt-in.

- [ ] **Step 2: Verify RED**

Run:

```bash
../../.venv/bin/python -m pytest tests/unit/test_recovery.py -q
```

Expected: the new tests fail because `plan_recovery` does not accept `accept_hermes_upgrade`.

- [ ] **Step 3: Implement the minimal planner signal**

Thread `accept_hermes_upgrade: bool = False` through `_plan_from_evidence`, `_classify_evidence`, `_classify_gateway_evidence`, and `_classify_cron_evidence`. In stale-unpatched classification, treat source mismatch as accepted only when all of these remain true:

```python
accepted_replacement = bool(
    accept_hermes_upgrade
    and source_valid
    and manifest_checks.valid
    and manifest_checks.backup_matches
    and backup_checks.valid
    and not manifest_invalid
    and not backup_status_error
)
```

Use `source_matches or accepted_replacement` in executability, omit the source-mismatch error when the replacement is accepted, and add a warning finding `hermes_upgrade_source_accepted`. Keep actions unchanged as `("clear_stale_install_state",)`.

- [ ] **Step 4: Preserve execution rechecks**

Pass the same flag through `execute_recovery`, `_execute_fresh_plan`, and `_commit_recovery_changes`. Every internal re-plan must call:

```python
plan_recovery(
    detection,
    accept_hermes_upgrade=accept_hermes_upgrade,
)
```

- [ ] **Step 5: Verify GREEN**

Run the focused unit suite again and expect all recovery tests to pass.

---

### Task 2: CLI recovery path and guidance

**Files:**
- Modify: `hermes_feishu_card/cli.py`
- Test: `tests/integration/test_cli_install.py`

**Interfaces:**
- Consumes: Task 1 planner/executor opt-in.
- Produces: `repair --accept-hermes-upgrade --yes`, `install --accept-hermes-upgrade --yes`, and `setup --accept-hermes-upgrade --yes`.

- [ ] **Step 1: Write failing CLI integration tests**

Cover:

```python
repair = run_cli(
    "repair", "--hermes-dir", str(hermes_dir),
    "--accept-hermes-upgrade", "--yes",
)
assert repair.returncode == 0
assert "install state: cleared stale unpatched state" in repair.stdout
assert run_py(hermes_dir).read_text(encoding="utf-8") == upgraded
assert not backup_path(hermes_dir).exists()
assert not manifest_path(hermes_dir).exists()
```

Then run `install --accept-hermes-upgrade --yes` in one step and assert the new backup exactly equals the upgraded unpatched source, the current file contains owned markers, and the new manifest hashes match. Keep an unchanged test proving the same command without the flag refuses.

- [ ] **Step 2: Verify RED**

Run:

```bash
../../.venv/bin/python -m pytest tests/integration/test_cli_install.py -q
```

Expected: argument parsing rejects `--accept-hermes-upgrade`.

- [ ] **Step 3: Add CLI options and propagation**

Add this option to `repair`, `install`, and `setup`:

```python
parser.add_argument(
    "--accept-hermes-upgrade",
    action="store_true",
    help=(
        "accept a supported unpatched Hermes source replacement and clear "
        "only verified stale HFC install state"
    ),
)
```

Pass `getattr(args, "accept_hermes_upgrade", False)` to `plan_recovery`, `execute_recovery`, and `_repair_install_state`. Ensure setup passes the value into its internal repair/install namespaces.

- [ ] **Step 4: Improve refusal guidance**

When a stale-unpatched plan is refused without opt-in, append:

```text
If Hermes was intentionally upgraded, rerun with --accept-hermes-upgrade --yes.
```

Do not suggest deleting manifest or backup files manually.

- [ ] **Step 5: Verify GREEN**

Run the integration install suite and expect all tests to pass.

---

### Task 3: Public documentation and release evidence

**Files:**
- Modify: `docs/installer-safety.md`
- Modify: `docs/user-guide.md`
- Modify: `docs/user-guide.en.md`
- Modify: `CHANGELOG.md`
- Test: `tests/unit/test_docs.py`

**Interfaces:**
- Consumes: final CLI spelling and safety behavior from Task 2.
- Produces: operator-facing recovery commands and an explicit warning about what the opt-in means.

- [ ] **Step 1: Document the exact workflow**

Add:

```bash
python3 -m hermes_feishu_card.cli repair \
  --hermes-dir /path/to/hermes-agent \
  --accept-hermes-upgrade \
  --yes
python3 -m hermes_feishu_card.cli install \
  --hermes-dir /path/to/hermes-agent \
  --yes
```

State that the flag confirms the current unpatched source is the intended upgraded Hermes source; it never authorizes overwriting that source and still requires verified old HFC artifacts plus supported anchors.

- [ ] **Step 2: Add changelog entry**

Add an `Unreleased` section crediting `@nasvip` and issue `#118`, describing the explicit recovery path and retained fail-closed default.

- [ ] **Step 3: Run documentation and package tests**

```bash
../../.venv/bin/python -m pytest tests/unit/test_docs.py tests/unit/test_package_metadata.py -q
```

Expected: all tests pass.

- [ ] **Step 4: Run release gate**

```bash
../../.venv/bin/python -m pytest -q
git diff --check
```

Expected: `0 failed`, only expected skips, and no whitespace errors.

- [ ] **Step 5: Commit and publish for review**

```bash
git add CHANGELOG.md docs/installer-safety.md docs/user-guide.md docs/user-guide.en.md \
  docs/superpowers/plans/2026-07-14-issue-118-upgrade-recovery.md \
  hermes_feishu_card/cli.py hermes_feishu_card/install/recovery.py \
  tests/integration/test_cli_install.py tests/unit/test_recovery.py
git commit -m "fix: recover safely after Hermes upgrades"
git push -u origin codex/fix-118-upgrade-recovery
gh pr create --base main --head codex/fix-118-upgrade-recovery \
  --title "fix: recover safely after Hermes upgrades" \
  --body-file /tmp/issue-118-pr-body.md
```

The PR body must include `Fixes #118`, RED/GREEN evidence, full-suite results, and the safety boundary that default recovery still refuses source mismatches.

## Self-Review

- Spec coverage: planner, CLI, docs, failure guidance, atomic recheck, default refusal, gateway and cron paths are covered.
- Placeholder scan: no deferred implementation markers remain.
- Type consistency: `accept_hermes_upgrade` is a keyword-only boolean at planner/executor boundaries and an `argparse` boolean at CLI boundaries.
