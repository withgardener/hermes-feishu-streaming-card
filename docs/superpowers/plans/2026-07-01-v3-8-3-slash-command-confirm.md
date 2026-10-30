# V3.8.3 Slash Command Confirm Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship V3.8.3 with independent Feishu command cards for Hermes slash-command confirmations and pickers such as `/new`, `/reset`, and `/model`, while keeping the existing text fallback safe path.

**Architecture:** Hermes already centralizes slash confirmation in async `_request_slash_confirm()`. The plugin should patch that method after Hermes registers the pending slash confirmation, post an independent sidecar `interaction.requested` event with `slash_confirm` metadata, poll `/interactions/{interaction_id}` asynchronously, and call Hermes's original `handler(choice)` when the user clicks a Feishu card button. Feishu command cards are separate command surfaces: they do not attach to the previous Agent streaming card. Existing in-session Agent choices, such as approvals and clarify prompts, continue to render in the active Agent card.

**Tech Stack:** Python 3.9+, aiohttp sidecar, Hermes Gateway patcher, existing `interaction.requested` / `/card/actions` protocol, pytest.

## Global Constraints

- Do not edit Hermes source directly; only `hermes_feishu_card/install/patcher.py` may patch `gateway/run.py`.
- The async Hermes Gateway path must not call the existing synchronous polling helper because it can block the event loop.
- V3.8.3 reuses the current card interaction loop; no new Feishu callback endpoint is introduced.
- Command cards are independent cards for slash commands. Active Agent cards only own approvals, clarify prompts, and other options that belong to the current Agent turn.
- `/update` is not a command-card target in V3.8.3. It is a Hermes background upgrade command; follow-up work may check whether the final upgrade completion/failure notification is reliably delivered.
- If sidecar/card interaction cannot be applied, fall back to Hermes native `send_slash_confirm` or text message behavior.
- No token, app secret, tenant token, raw authorization value, or private chat content may be logged or documented.
- TDD is mandatory: write failing tests and verify they fail before production changes.

---

## File Structure

- Modify `hermes_feishu_card/hook_runtime.py`: add async helpers that build and post independent command-card interaction events and poll for the clicked choice.
- Modify `hermes_feishu_card/install/patcher.py`: inject owned marker blocks into Hermes `_request_slash_confirm()` and install Feishu command-card adapter methods before slash command dispatch.
- Modify `tests/unit/test_hook_runtime.py`: cover async slash confirm event posting, option shape, polling, and fallback behavior.
- Modify `tests/unit/test_patcher.py`: cover patch insertion, idempotency, removal, and fallback-preserving placement for command cards.
- Modify `TODO.md`: record V3.8.3 scope, including original V3.8.3 maintenance items plus slash command confirmation coverage.
- Optionally update release docs after implementation is verified.
- Verify in the real local Hermes runtime with the configured Feishu bot before release.

---

### Task 1: Runtime Async Slash Confirm Helper

**Files:**
- Modify: `tests/unit/test_hook_runtime.py`
- Modify: `hermes_feishu_card/hook_runtime.py`

**Interfaces:**
- Produces: `request_slash_confirm_from_hermes_locals_async(local_vars, *, command, title, message, interaction_id, timeout_seconds=None, poll_interval_seconds=None) -> str | None`
- Consumes: existing `build_interaction_event()`, `_post_json_ordered_response()`, `_get_json()`, `_uses_text_interaction_fallback()`

- [x] **Step 1: Write failing test**

Add a test that calls the new async helper, verifies it posts `interaction.requested` with `kind == "slash_confirm"`, options `once`, `always`, `cancel`, and returns `"once"` after `/interactions/{interaction_id}` reports completion.

- [x] **Step 2: Verify RED**

Run:

```bash
python -m pytest tests/unit/test_hook_runtime.py::test_request_slash_confirm_async_posts_event_and_polls_until_completed -q
```

Expected: fail because `request_slash_confirm_from_hermes_locals_async` does not exist.

- [x] **Step 3: Implement minimal helper**

Implement the async helper using existing runtime config, event builders, async post/get helpers, and existing text-fallback detection.

- [x] **Step 4: Verify GREEN**

Run:

```bash
python -m pytest tests/unit/test_hook_runtime.py::test_request_slash_confirm_async_posts_event_and_polls_until_completed -q
```

Expected: pass.

---

### Task 2: Patcher Hook For Hermes `_request_slash_confirm`

**Files:**
- Modify: `tests/unit/test_patcher.py`
- Modify: `hermes_feishu_card/install/patcher.py`

**Interfaces:**
- Produces marker constants `SLASH_CONFIRM_PATCH_BEGIN` / `SLASH_CONFIRM_PATCH_END`
- Produces patch insertion after Hermes `_slash_confirm_mod.register(session_key, confirm_id, command, handler)`
- Consumes: runtime helper `request_slash_confirm_from_hermes_locals_async`

- [x] **Step 1: Write failing patcher test**

Add a fixture with an async `_request_slash_confirm()` method containing `_slash_confirm_mod.register(...)`. Assert `apply_patch(..., strategy="gateway_run_013_plus")` inserts the slash confirm marker block, calls the runtime helper with `await`, calls `return await handler(_hfc_slash_choice)` when a card choice is received, remains idempotent, and `remove_patch()` restores the original content.

- [x] **Step 2: Verify RED**

Run:

```bash
python -m pytest tests/unit/test_patcher.py::test_apply_patch_inserts_slash_confirm_card_hook -q
```

Expected: fail because the slash confirm marker and insertion logic do not exist.

- [x] **Step 3: Implement minimal patcher support**

Add marker constants, apply/remove support, lenient removal support, a slash-confirm insertion helper, and a rendered hook block that falls through on any exception or text-fallback result.

- [x] **Step 4: Verify GREEN**

Run:

```bash
python -m pytest tests/unit/test_patcher.py::test_apply_patch_inserts_slash_confirm_card_hook -q
```

Expected: pass.

---

### Task 3: Independent `/model` Picker Command Card

**Files:**
- Modify: `tests/unit/test_hook_runtime.py`
- Modify: `tests/unit/test_patcher.py`
- Modify: `hermes_feishu_card/hook_runtime.py`
- Modify: `hermes_feishu_card/install/patcher.py`

**Interfaces:**
- Produces: `install_feishu_command_card_adapter_methods(runner) -> bool`
- Produces: a Feishu-only `send_model_picker(...)` adapter method when Hermes's Feishu adapter lacks one.
- Consumes: Hermes `on_model_selected(chat_id, model_id, provider_slug)` callback.

- [x] **Step 1: Write failing runtime test**

Add a test that installs command-card adapter methods onto a dummy Feishu adapter, calls `send_model_picker(...)`, simulates the user selecting a model through the sidecar interaction poll result, verifies `on_model_selected(...)` receives the selected provider/model, and verifies the command card receives a terminal `message.completed` update with the callback result.

- [x] **Step 2: Verify RED**

Run:

```bash
python -m pytest tests/unit/test_hook_runtime.py::test_install_feishu_command_card_methods_adds_model_picker -q
```

Expected: fail because `install_feishu_command_card_adapter_methods` does not exist.

- [x] **Step 3: Implement minimal model picker method**

Flatten Hermes provider/model data into card button options, wait for a choice, call Hermes's callback, post the callback result back to the same independent command card, and return a `SendResult(success=True)`-compatible object.

- [x] **Step 4: Add patcher test for install hook**

Add a test that `_handle_message()` receives a marker-wrapped hook calling `install_feishu_command_card_adapter_methods(self)` before slash command dispatch.

- [x] **Step 5: Verify GREEN**

Run:

```bash
python -m pytest tests/unit/test_hook_runtime.py::test_install_feishu_command_card_methods_adds_model_picker tests/unit/test_patcher.py::test_apply_patch_installs_feishu_command_card_adapter_methods -q
```

Expected: pass.

---

### Task 4: Documentation And Version Scope

**Files:**
- Modify: `TODO.md`
- Later release step may modify: `CHANGELOG.md`, `README.md`, `README.en.md`, `docs/release-notes-v3.8.3.md`

**Interfaces:**
- Produces: visible V3.8.3 plan entry that includes slash command card confirmation coverage.

- [x] **Step 1: Update TODO**

Record:

- V3.8.3 covers independent slash command cards:
  - slash confirmations (`/new`, `/reset`, `/undo`, and `/model <model>` high-cost model confirmation when Hermes requests it).
  - `/model` picker when Hermes asks the adapter for `send_model_picker`.
  - `/update` remains a background upgrade command and should not use an interactive command card in this version; separately evaluate completion notification reliability.
- It must preserve native text fallback when Feishu card callbacks are unavailable.
- It continues the existing V3.8.x polish line instead of starting a separate feature branch.

- [x] **Step 2: Run doc tests if exact strings changed**

Run:

```bash
python -m pytest tests/unit/test_docs.py -q
```

Expected: pass.

---

### Task 5: Final Verification

**Files:**
- Verify: runtime, patcher, render/server compatibility tests

- [x] **Step 1: Run targeted tests**

Run:

```bash
python -m pytest tests/unit/test_hook_runtime.py tests/unit/test_patcher.py tests/unit/test_render.py tests/integration/test_server.py -q
```

- [x] **Step 2: Run full suite before release or merge**

Run:

```bash
python -m pytest -q
```

- [x] **Step 3: Summarize release boundary**

Report exactly what is implemented, which tests passed, and whether V3.8.3 is ready for version bump/tag/release.

---

### Task 6: Real Local Hermes Smoke Test

**Files:**
- Verify: local Hermes runtime under `~/.hermes/hermes-agent`
- Verify: configured Feishu bot conversation

**Interfaces:**
- Consumes: installed package entry points and patched Hermes `gateway/run.py`
- Produces: manual smoke evidence before V3.8.3 release

- [x] **Step 1: Install current checkout into Hermes runtime**

Run the project installer/setup path so `hermes_feishu_card` is importable from the Python interpreter Hermes actually runs, then refresh the hook patch in Hermes `gateway/run.py`.

- [x] **Step 2: Verify `/new` command path**

In the real Feishu chat, send `/new`. Expected in callback/public mode: Feishu receives an independent command confirmation card with Approve Once / Always Approve / Cancel style options, not an update to the previous Agent streaming card. Local result on 2026-07-01: current bot runs private/text fallback mode, so `/new` correctly returned only Hermes native text fallback; no extra sidecar command card was created, and `/cancel` cleared the pending confirmation.

- [x] **Step 3: Verify `/model` picker path**

In the real Feishu chat, send `/model`. Expected in callback/public mode: Feishu receives an independent model picker card. Selecting a model calls Hermes's selection callback and updates the same command card with the result. Local result on 2026-07-01: current bot runs private/text fallback mode, so `/model` correctly returned Hermes native model list text and did not create an extra sidecar command card.

- [x] **Step 4: Verify `/update` remains non-interactive by scope**

In the real Feishu chat, verify `/update` does not produce an interactive command card. It may run Hermes's background upgrade path and should rely on Hermes's own completion/failure notification behavior.

- [x] **Step 5: Record smoke result**

Record the tested commands, observed Feishu behavior, and any screenshots or limitations in the release notes or final summary before tagging V3.8.3.

Smoke note: `/update` was not executed in the live bot during this release smoke because it can trigger a background Hermes upgrade. The V3.8.3 patch does not hook `/update`, and this boundary is covered by code review plus the patch insertion scope.
