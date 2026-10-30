# Open Issues and Pull Requests Closure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Resolve every currently open Issue and PR with verified code, a documented product decision, or an evidence-backed closure, while preserving contributor credit.

**Architecture:** Ship user-visible correctness and installer repairs as `v3.9.1`, then build the reusable native picker flow and restrained footer polish as `v3.10.0`. Do not merge stale branches wholesale: retain original commits where they remain correct, split mixed changes into reviewable commits, and close superseded work with links to the replacement implementation.

**Tech Stack:** Python 3.9+, aiohttp, Feishu/Lark CardKit schema 2.0, Hermes Gateway runtime hooks, pytest, GitHub Actions, GitHub CLI.

## Global Constraints

- Active runtime is `hermes_feishu_card/`; do not edit `legacy/`.
- Only `hermes_feishu_card/install/patcher.py` may modify an installed Hermes `gateway/run.py`.
- Unknown or unsupported runtime paths remain fail-open; a card path already accepted by HFC suppresses duplicate native text.
- Normal streaming-card layout and the existing footer element order remain unchanged.
- Private operations do not compare operators; group interactive actions require the initiating operator.
- No token, App Secret, real chat id, open id, local `.env`, or unredacted screenshot enters Git.
- Every adopted external change retains its contributor commit or explicit `Co-authored-by` credit and is listed in release notes.
- Use merge commits for clean contributor PRs unless a maintainer follow-up is required on the contributor branch.
- Release gates run on Python 3.9 and Python 3.12, followed by the GitHub Actions matrix and real Feishu smoke where specified.

---

## Version and Issue Map

| Batch | Included work | Close after |
|---|---|---|
| `v3.9.1` reliability hotfix | PR #97 / issue #96, PR #93 / issue #92, model-picker defect from PR #98, issue #82 corrupt markers, loopback/Windows remainder from PR #52, `tools/__init__.py` syntax | automated gates plus private-chat Feishu smoke |
| `v3.10.0` interaction UX | issue #94 `/resume` picker, sanitized model-name color contribution from PR #98 | automated gates plus private and group/topic Feishu smoke |
| Evidence-backed closure | issues #80/#83/#95; PRs #49/#50/#51/#54/#72 | replacement links and contributor acknowledgement posted |

### Task 1: Create the v3.9.1 Baseline and Remove Immediate Runtime Hazards

**Files:**
- Modify: `tools/__init__.py`
- Modify: `hermes_feishu_card/process.py`
- Modify: `tests/unit/test_process.py`
- Create: `tests/unit/test_tools_package.py`

**Interfaces:**
- Consumes: current `process.fetch_health(config)` behavior and hook-runtime loopback proxy policy.
- Produces: `_open_health_url(url: str, timeout: float)` using a no-proxy opener only for loopback hosts; a syntactically importable `tools` package.

- [ ] **Step 1: Add failing syntax and loopback-proxy tests**

```python
def test_tools_package_compiles():
    source = Path("tools/__init__.py").read_text(encoding="utf-8")
    compile(source, "tools/__init__.py", "exec")


def test_fetch_health_bypasses_proxy_for_loopback(monkeypatch):
    calls = []
    monkeypatch.setattr(process._NO_PROXY_OPENER, "open", lambda request, timeout: calls.append((request.full_url, timeout)) or FakeHealthResponse())
    monkeypatch.setattr(process.urllib.request, "urlopen", lambda *_args, **_kwargs: pytest.fail("global proxy path used"))
    assert process.fetch_health({"server": {"host": "127.0.0.1", "port": 8765}})["status"] == "healthy"
    assert calls == [("http://127.0.0.1:8765/health", 0.4)]
```

- [ ] **Step 2: Run the focused tests and verify both fail**

Run: `python -m pytest tests/unit/test_tools_package.py tests/unit/test_process.py -q`

Expected: `tools/__init__.py` raises `SyntaxError`, and loopback health still calls the global opener.

- [ ] **Step 3: Repair the module header and add loopback-only proxy bypass**

```python
# tools/__init__.py
"""Utility scripts for installer and management."""
```

```python
# hermes_feishu_card/process.py
import urllib.parse

_NO_PROXY_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def _open_health_url(url: str, timeout: float):
    host = urllib.parse.urlsplit(url).hostname or ""
    if host.lower() in {"127.0.0.1", "localhost", "::1"}:
        return _NO_PROXY_OPENER.open(urllib.request.Request(url), timeout=timeout)
    return urllib.request.urlopen(url, timeout=timeout)
```

Update `fetch_health()` to use `_open_health_url(url, 0.4)`. Keep the existing `ctypes`/`taskkill` Windows process implementation; do not add `psutil`.

- [ ] **Step 4: Verify focused tests and compile the complete source tree**

Run: `python -m pytest tests/unit/test_tools_package.py tests/unit/test_process.py tests/unit/test_hook_runtime.py -q`

Run: `python -m compileall -q hermes_feishu_card tools`

Expected: all tests pass and compileall exits 0.

- [ ] **Step 5: Commit with PR #52 and PR #98 provenance**

Commit: `fix: repair local runtime imports and loopback health checks`

Credit PR #52 for the Windows/proxy diagnosis and PR #98 / @charles5g for finding the literal newline defect. If code is reconstructed rather than cherry-picked, include the relevant `Co-authored-by` trailers.

### Task 2: Integrate PR #97 Without Losing Final Answers

**Files:**
- Modify: `hermes_feishu_card/session.py`
- Add or retain: `tests/unit/test_prepare_completed_answer_issue96.py`
- Modify: `tests/unit/test_session.py`

**Interfaces:**
- Consumes: `CardSession._prepare_completed_answer(completed_answer: str) -> str`.
- Produces: `_has_substantial_completed_suffix(final: str, stripped: str) -> bool`, preventing a near-complete streamed answer from being archived as reasoning.

- [ ] **Step 1: Check out PR #97 on an integration branch and retain commit `7409980`**

Use a merge-based integration so @colinaaa remains the code author. Do not squash the contributor commit.

- [ ] **Step 2: Run the new issue #96 tests against unmodified `main`**

Run: `python -m pytest tests/unit/test_prepare_completed_answer_issue96.py -q`

Expected: the punctuation-tail and whitespace-tail reproductions fail before the PR implementation is applied.

- [ ] **Step 3: Make the archival threshold explicit and centralized**

```python
MIN_COMPLETED_SUFFIX_CHARS = 20
MIN_COMPLETED_SUFFIX_RATIO = 0.20


def _has_substantial_completed_suffix(final: str, stripped: str) -> bool:
    return (
        len(stripped) >= MIN_COMPLETED_SUFFIX_CHARS
        and len(stripped) >= len(final) * MIN_COMPLETED_SUFFIX_RATIO
    )
```

Only call `_archive_current_answer_to_reasoning()` when this helper returns true. Otherwise return the full normalized `final`.

- [ ] **Step 4: Add regression boundaries**

Cover exact equality, one-character punctuation, whitespace normalization, a legitimate short pre-tool preface followed by a substantial final answer, Chinese text, and the exact 20-character/20-percent boundaries. Verify no-tool sessions remain unchanged.

- [ ] **Step 5: Run session and renderer tests**

Run: `python -m pytest tests/unit/test_prepare_completed_answer_issue96.py tests/unit/test_session.py tests/unit/test_render.py -q`

Expected: all pass; a completed card shows the whole final answer in the body and keeps only genuine pre-tool narration in the timeline.

- [ ] **Step 6: Add a maintainer follow-up commit only if threshold constants or tests changed**

Commit: `test: harden completed-answer archival boundaries`

### Task 3: Integrate PR #93 and Terminate Interrupted Cards Safely

**Files:**
- Modify: `hermes_feishu_card/server.py`
- Modify: `tests/integration/test_server.py`

**Interfaces:**
- Consumes: app session maps, `SidecarEvent` routing identity, and `_apply_event_locked(...)`.
- Produces: `_abandon_stale_sessions_for_chat(app, *, new_session_key: str, event: SidecarEvent) -> list[str]`.

- [ ] **Step 1: Merge PR #93 into an integration branch while retaining commit `f24a163`**

Preserve @colinaaa as author; put review corrections in a separate maintainer commit.

- [ ] **Step 2: Run the five PR tests against current `main` and confirm the stuck-card reproduction**

Run: `python -m pytest tests/integration/test_server.py -k 'interrupt or abandoned_session' -q`

Expected: at least the stale-session reproduction fails before the PR is applied.

- [ ] **Step 3: Constrain abandonment to one routing lane**

```python
same_lane = (
    old.chat_id == event.chat_id
    and old.conversation_id == event.conversation_id
    and old.profile_id == event.data.get("profile_id", "default")
)
if old_key != new_session_key and same_lane and old.status in {"thinking", "streaming", "waiting"}:
    old.timeline.complete()
    old.status = "completed"
```

Flush pending deltas before the final PATCH, clear per-session update state after the PATCH, and never abandon a session from another topic `conversation_id`, profile, or chat.

- [ ] **Step 4: Preserve duplicate-suppression semantics for late terminal events**

When a later `message.completed` targets an already-abandoned session, return `{ok: true, applied: true}` without sending a second final PATCH. This proves the plugin still owns delivery and suppresses Hermes native duplicate text.

- [ ] **Step 5: Add race and routing tests**

Test two simultaneous topic threads, a private-chat interrupt, a late completed event, a completed old session, and two profiles sharing the same chat id. Assert exactly one terminal PATCH per abandoned card.

- [ ] **Step 6: Run the server/hook regression matrix**

Run: `python -m pytest tests/integration/test_server.py tests/unit/test_hook_runtime.py -q`

Expected: all pass, with no topic, cron, operations-card, or duplicate-native regression.

### Task 4: Split PR #98 and Fix the Model Picker Callback Path

**Files:**
- Modify: `hermes_feishu_card/hook_runtime.py`
- Modify: `tests/unit/test_hook_runtime.py`

**Interfaces:**
- Consumes: `_hfc_prepare_native_model_action(...)`, `_hfc_update_native_command_card(...)`, adapter loop, and Feishu callback tokens.
- Produces: `_hfc_switch_model_background_task(adapter, data, prepared) -> None` and immediate callback ACK behavior.

- [ ] **Step 1: Extract only model-picker commits `5a9206e` and `fafa6ce` from PR #98**

Do not merge the original PR as one unit. Keep `render.py` color work for Task 7 and the `tools/__init__.py` correction in Task 1. Preserve @charles5g as author of extracted commits.

- [ ] **Step 2: Add timing, retry, and exactly-once tests**

```python
def test_model_picker_sync_callback_acks_before_switch_finishes(...):
    started = time.monotonic()
    response = hook_runtime._hfc_on_feishu_card_action_trigger(adapter, data)
    assert time.monotonic() - started < 0.5
    assert response is not None
    assert response_card_title(response) == "正在切换模型"
```

Also send the same callback token twice and assert `on_model_selected` runs once. Cover malformed JSON, expired picker state, missing `metadata`, update failure, and fallback result-card send.

- [ ] **Step 3: Deduplicate at the synchronous entry before consuming picker state**

```python
if action in {"slash_confirm", "model_picker", "interaction.select"}:
    if _hfc_is_duplicate_card_action(self, data):
        return _hfc_empty_feishu_callback_response(self)
```

Ensure the first callback owns and removes state; retries only receive an empty successful ACK.

- [ ] **Step 4: ACK immediately and finish switching on the adapter loop**

Return a “正在切换模型” card synchronously, then schedule `_hfc_switch_model_background_task`. The task calls the existing model callback, tries `_hfc_update_native_command_card()` on the original message, and sends one result card only when Feishu rejects in-place update. Always pass `metadata=_hfc_action_metadata(data)` to the send helper.

- [ ] **Step 5: Run focused and full hook tests**

Run: `python -m pytest tests/unit/test_hook_runtime.py -k 'model_picker or card_action' -q`

Run: `python -m pytest tests/unit/test_hook_runtime.py -q`

Expected: callback returns under 500 ms, the switch runs once, and users receive one final success or failure result.

- [ ] **Step 6: Perform private-chat Feishu smoke**

Send bare `/model`, select a model, repeat-click once, and verify: no callback-timeout toast, no raw JSON, one model switch, and one result state. Record only redacted timing and card result.

### Task 5: Close Issue #82's Corrupt-Marker Gap and Clarify Issue #95 Upgrade Recovery

**Files:**
- Modify: `hermes_feishu_card/install/recovery.py`
- Modify: `hermes_feishu_card/install/detect.py`
- Modify: `hermes_feishu_card/cli.py`
- Modify: `tests/unit/test_recovery.py`
- Modify: `tests/integration/test_cli_install.py`
- Modify: `tests/unit/test_patcher.py`
- Modify: `README-install.md`
- Modify: `docs/installer-safety.md`
- Modify: `docs/installer-safety.en.md`

**Interfaces:**
- Consumes: manifest/backup hashes, patch markers, generated current hook blocks, and Hermes anchor detection.
- Produces: a safe `corrupt_owned` recovery plan even when the manifest still contains the pre-damage patched hash, but only when all differences are confined to HFC-owned markers/blocks.

- [ ] **Step 1: Add the exact issue #82 state as a failing fixture**

Install a fixture normally, remove one completion end marker, leave `manifest.patched_sha256` unchanged, preserve the verified backup, and run `setup --repair`. The current test that rewrites the manifest hash remains, but it is not sufficient for the reported Docker state.

- [ ] **Step 2: Prove the current planner refuses that fixture before changing recovery**

Run: `python -m pytest tests/unit/test_recovery.py tests/integration/test_cli_install.py -k 'issue_82 or corrupt_completion' -q`

Expected: the new realistic fixture fails because `current_hash_mismatch` is treated as an unknown user edit.

- [ ] **Step 3: Add marker-only ownership verification**

```python
def _matches_owned_marker_damage(
    *,
    current: str,
    backup: str,
    expected_patched: str,
    expected_backup_sha256: str,
) -> bool:
    if sha256(backup.encode("utf-8")).hexdigest() != expected_backup_sha256:
        return False
    return normalize_hfc_marker_damage(current) == normalize_hfc_marker_damage(expected_patched)
```

`normalize_hfc_marker_damage()` may normalize only known HFC begin/end marker lines. It must not normalize arbitrary Python, imports, indentation, or user-authored text. If any non-marker byte differs, recovery remains refused.

- [ ] **Step 4: Improve source-stripped version wording without weakening detection**

When version metadata is absent but gateway anchors verify compatibility, print `version: unknown (source-stripped metadata)` and `version_source: gateway anchors`. Continue to fail closed when metadata is explicitly invalid and anchors do not verify.

- [ ] **Step 5: Add Docker-style setup and repeated-repair tests**

Cover pinned `HFC_VERSION`, missing metadata, one corrupt marker, setup auto-repair, second setup idempotency, explicit `--no-repair`, user edits outside markers, and backup hash mismatch. Assert no real paths or secrets appear in card-safe diagnostics.

- [ ] **Step 6: Run installer and recovery gates**

Run: `python -m pytest tests/unit/test_recovery.py tests/unit/test_patcher.py tests/integration/test_cli_install.py tests/unit/test_install_scripts.py -q`

Expected: known owned damage repairs; unknown edits and bad backups are refused.

- [ ] **Step 7: Update the upgrade runbook**

Document that a Hermes upgrade replaces `gateway/run.py`, so users run the v3.9.1 installer or `setup`, then restart Gateway. Use retrying `curl` examples for transient GitHub 429 responses and show the package-version verification command separately from Hermes source metadata.

### Task 6: Build Issue #94's Native `/resume` Picker on the Original Hermes Security Path

**Files:**
- Modify: `hermes_feishu_card/hook_runtime.py`
- Modify: `tests/unit/test_hook_runtime.py`
- Modify: `tests/unit/test_patcher.py`
- Modify: `docs/wiki/event-flow.md`
- Modify: `docs/wiki/maintenance-guide.md`

**Interfaces:**
- Consumes: `GatewayRunner._handle_resume_command(event)`, `_session_db.list_sessions_rich(...)`, `_resume_row_visible(...)`, Feishu adapter send/update helpers, and the model-picker callback pattern from Task 4.
- Produces: `_hfc_handle_resume_command_with_picker(self, event) -> str`, `_hfc_send_native_resume_picker(...)`, and `hfc_action=resume_picker` callbacks.

- [ ] **Step 1: Add fail-open wrapper tests before runtime changes**

Cover non-Feishu source, `/resume <arg>`, no session DB, no named sessions, card send failure, and an adapter without native-card support. In every case assert the saved original `_handle_resume_command(event)` is called exactly once.

- [ ] **Step 2: Add native picker and callback tests**

Use ten named-session fixtures, one current session, an initiating `open_id`, a topic reply anchor, and a callable original resume handler. Assert dropdown options use opaque session ids, label current session, preserve topic reply metadata, and never expose transcript content beyond the existing 40-character preview policy.

- [ ] **Step 3: Wrap the inherited Hermes handler at runtime**

Inside `install_feishu_command_card_adapter_methods(runner, event)`, store the inherited original handler on `type(runner)` and install:

```python
async def _hfc_handle_resume_command_with_picker(self, event):
    if event.get_command_args().strip():
        return await type(self)._hfc_original_handle_resume_command(self, event)
    picker_result = await _hfc_try_resume_picker(self, event)
    if picker_result is None:
        return await type(self)._hfc_original_handle_resume_command(self, event)
    return picker_result
```

No new source patch block is needed; the existing idempotent command-card adapter hook installs the wrapper.

- [ ] **Step 4: Reuse the original Hermes resume handler for selection**

On click, validate picker id, chat id, allowed session ids, expiry, and group initiating `open_id`. Then create a copy of the stored event with `text=f"/resume {target_session_id}"` and call the original Hermes handler. This preserves `_resume_target_allowed`, continuation resolution, model/reasoning override cleanup, running-agent release, and transcript switching; HFC must not duplicate those security rules.

- [ ] **Step 5: Use immediate ACK plus background completion**

Return a “正在恢复会话” card within 500 ms, execute the original handler on the runner loop, and update the same interactive card. If update is rejected, send one fallback result card. Expired/invalid state returns a localized error card without calling Hermes.

- [ ] **Step 6: Run compatibility and idempotency tests**

Run: `python -m pytest tests/unit/test_hook_runtime.py tests/unit/test_patcher.py tests/integration/test_cli_install.py -q`

Expected: `/resume <arg>`, `/model`, slash confirmation, clarify/approval, install/remove/repair, and non-Feishu behavior remain unchanged.

- [ ] **Step 7: Perform real Feishu acceptance**

Private chat: open, switch, switch-current, expired picker. Group/topic: initiating user succeeds, another user is rejected, and the result stays in the originating topic. Confirm no gray native list and no callback-timeout toast.

### Task 7: Apply Restrained Visual Polish and Resolve Table/Cron Scope

**Files:**
- Modify: `hermes_feishu_card/render.py`
- Modify: `tests/unit/test_render.py`
- Modify: `README.md`
- Modify: `README.en.md`
- Modify: `docs/user-guide.md`
- Modify: `docs/user-guide.en.md`

**Interfaces:**
- Consumes: `_render_footer(...)` and current `footer_fields` ordering.
- Produces: `_colored_model_label(model: str) -> str` with escaped text and no layout changes.

- [ ] **Step 1: Extract the model-color idea from PR #98 into its own contributor-attributed commit**

Do not reuse the unescaped implementation directly. Keep the existing footer divider, `element_id=footer`, field order, separators, font size, and configured footer fields.

- [ ] **Step 2: Add footer-invariant and escaping tests**

Test known providers, unknown providers, mixed case, a model containing `<script>`, configured field order, thinking/failed states, and empty footer fields. Assert the result cannot inject Feishu markup and existing card element ids are unchanged.

- [ ] **Step 3: Implement sanitized semantic color only around the model label**

```python
MODEL_COLOR_PREFIXES = (
    (("gpt-", "o1", "o3"), "blue"),
    (("claude-",), "orange"),
    (("deepseek-", "deepseek/"), "indigo"),
    (("kimi-", "kimi/", "moonshot-"), "purple"),
    (("glm-",), "green"),
    (("hy3", "tencent/", "hunyuan"), "teal"),
)


def _colored_model_label(model: str) -> str:
    safe = html.escape(model, quote=True)
    for prefixes, color in MODEL_COLOR_PREFIXES:
        if model.lower().startswith(prefixes):
            return f'<font color="{color}">{safe}</font>'
    return safe
```

- [ ] **Step 4: Run renderer tests and perform screenshot QA**

Run: `python -m pytest tests/unit/test_render.py tests/unit/test_text.py -q`

Render completed, thinking, failed, long-table, and operations cards in real Feishu. Confirm the footer remains one compact line when space allows and wraps without overlapping on mobile.

- [ ] **Step 5: Resolve issue #80 as answered, not as an unbounded renderer rewrite**

The issue contains no reproduction sample and asks about existing behavior. Post the current Markdown-structure guarantee, link the long-table tests/docs, invite a new reproducible issue for native CardKit table conversion, and close #80 as answered. Do not claim arbitrary Markdown-to-native-table support.

- [ ] **Step 6: Close PR #51 with the current product boundary**

Explain that current global/profile/bot `card.footer_fields` and title configuration cover supported customization, while hiding the footer conflicts with the confirmed invariant. Credit @coder-zhw for the cron customization proposal; do not merge the `hide_footer` path.

### Task 8: Documentation, Contributor Credit, GitHub Closure, and Releases

**Files:**
- Modify: `TODO.md`
- Modify: `CHANGELOG.md`
- Modify: `README.md`
- Modify: `README.en.md`
- Modify: `docs/user-guide.md`
- Modify: `docs/user-guide.en.md`
- Create: `docs/release-notes-v3.9.1.md`
- Create: `docs/release-notes-v3.10.0.md`
- Modify: `docs/wiki/feishu-acceptance.md`
- Modify: `tests/unit/test_docs.py`
- Modify: `tests/unit/test_package_metadata.py`
- Modify: `pyproject.toml`
- Modify: `hermes_feishu_card/__init__.py`

**Interfaces:**
- Consumes: verified commits and acceptance evidence from Tasks 1-7.
- Produces: public release records, contributor attribution, and a zero-stale-item GitHub queue.

- [ ] **Step 1: Close already-answered issues with precise replacement links**

Close #83 with the multi-profile guide and `/hfc doctor` route-chain instructions. Close #95 with the v3.9.1 upgrade/setup/restart runbook and invite reopening only if the card remains unavailable on the verified version. Close #80 as specified in Task 7.

- [ ] **Step 2: Close superseded PRs without erasing their contribution**

- PR #49: link v3.8.9, v3.8.16, and v3.8.18 topic-routing replacements; thank @0269chaoup for the DM-topic diagnosis.
- PR #50: link v3.8.7 first-event session creation, v3.9.0 lifecycle cleanup, and PR #93 interrupt cleanup; thank @dominofeng-maker for the zombie-session evidence.
- PR #54: link the shipped Hermes runtime-venv installation and diagnostics; thank @x-giraffee for issue #53's venv diagnosis.
- PR #72: close as outside the sidecar runtime boundary; suggest a standalone utility package and thank @jackwude for the tested API proposal.
- PR #51: close using Task 7's footer decision.
- PR #52: close only after Task 1 lands, linking the replacement commit and crediting @wjiemin49-ux.

- [ ] **Step 3: Close adopted PRs and issues through releases**

Merge #97 and #93 with contributor history. Close #98 after linking the extracted model-picker, syntax, and model-color commits and crediting @charles5g. Close #82/#92/#96 in the v3.9.1 release notes. Close #94 in the v3.10.0 release notes.

- [ ] **Step 4: Prepare and verify v3.9.1**

Bump both version files to `3.9.1`, update docs and tests, then run:

```bash
python -m pytest tests/unit/test_hook_runtime.py tests/unit/test_session.py tests/unit/test_render.py tests/unit/test_recovery.py tests/unit/test_patcher.py tests/unit/test_process.py tests/integration/test_server.py tests/integration/test_cli_install.py -q
python -m pytest -q
git diff --check
```

Expected: the focused matrix and full suite pass on Python 3.9 and 3.12; GitHub Actions is green; private Feishu model-picker, interrupt, answer-body, and setup-repair smoke pass.

- [ ] **Step 5: Publish v3.9.1**

Merge through a PR, create annotated tag `v3.9.1`, push main and tag, wait for release-assets workflow, and verify macOS/Linux/Windows/checksums assets. Release notes must list @colinaaa, @charles5g, and @wjiemin49-ux for adopted work.

- [ ] **Step 6: Prepare and verify v3.10.0**

Bump both version files to `3.10.0`, update docs/screenshots, then run:

```bash
python -m pytest tests/unit/test_hook_runtime.py tests/unit/test_patcher.py tests/unit/test_render.py tests/unit/test_text.py tests/integration/test_cli_install.py -q
python -m pytest -q
git diff --check
```

Expected: Python 3.9/3.12 and GitHub Actions pass; private and group/topic `/resume` acceptance passes; model footer polish preserves layout.

- [ ] **Step 7: Publish v3.10.0 and audit the queue**

Create annotated tag `v3.10.0`, verify release assets and notes, then list open Issues and PRs again. Success means no item from the 2026-07-11 inventory remains open without a newly documented external blocker or a new user reproduction.

## Execution Order and Review Gates

1. Run Task 1 first because it repairs an active syntax defect and loopback reliability.
2. Tasks 2 and 3 can be reviewed in parallel, but merge one at a time and rerun server/session tests after each.
3. Task 4 follows Tasks 1-3 on the v3.9.1 branch so callback behavior is tested against the current runtime.
4. Task 5 completes the v3.9.1 code scope; Task 8 then publishes v3.9.1.
5. Task 6 builds on Task 4's asynchronous picker path; Task 7 can proceed in parallel.
6. Task 8 publishes v3.10.0 and performs the final GitHub queue audit.

## Completion Audit

- [ ] Every open Issue #80, #82, #83, #92, #94, #95, and #96 has a release link or evidence-backed answer/closure.
- [ ] Every open PR #49, #50, #51, #52, #54, #72, #93, #97, and #98 is merged, extracted with credit, or closed with a replacement link.
- [ ] Issue #82's realistic unchanged-manifest corrupt-marker fixture repairs safely, while user edits still refuse.
- [ ] Model picker and `/resume` callbacks ACK under 500 ms and execute exactly once.
- [ ] Interrupted cards terminate once; late completion remains suppressed; topic/profile lanes remain isolated.
- [ ] Final answers are never reduced to punctuation-only tails.
- [ ] Existing streaming-card footer structure remains unchanged; model color text is escaped.
- [ ] Python 3.9, Python 3.12, GitHub Actions, release assets, and required real Feishu smokes are verified for each release.
- [ ] Release notes and README preserve all adopted contributor credit.
