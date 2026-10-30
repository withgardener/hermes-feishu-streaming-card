# V3.8.1 Hotfix And Read-Only Commands Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship V3.8.1 with gateway-side high-frequency delta coalescing for issue #74 and read-only `/hfc help/status/doctor/monitor` Feishu diagnostics commands.

**Architecture:** Keep the sidecar as the authoritative card renderer and diagnostics source. Move only delta coalescing into `hook_runtime.py` so Hermes stream-reader threads do less per-token work before events reach the sidecar. Route `/hfc` commands through the hook to a sidecar `/commands` endpoint that renders a short diagnostic card without entering the LLM.

**Tech Stack:** Python 3.9+, aiohttp sidecar, Hermes hook runtime, existing `CardSession` / `render_card()` card rendering, pytest.

## Global Constraints

- User-facing conversation and docs for this task are Chinese-first; code names and API names stay English.
- V3.8.1 must fix issue #74 before adding optional polish.
- `/hfc` commands are read-only: `help`, `status`, `doctor`, `monitor`.
- No `reload`, `continue`, `retry`, `cancel`, or active Hermes session control in V3.8.1.
- No raw Feishu `chat_id`, raw Feishu `message_id`, token, app secret, tenant token, or authorization value may appear in command card output.
- TDD is mandatory: write failing tests before production changes.

---

### Task 1: Gateway-Side Delta Coalescing

**Files:**
- Modify: `hermes_feishu_card/hook_runtime.py`
- Test: `tests/unit/test_hook_runtime.py`

**Interfaces:**
- Produces: `emit_from_hermes_locals_threadsafe()` coalesces `thinking.delta` and `answer.delta`.
- Produces: terminal events call a helper that flushes pending delta for the same runtime message before terminal POST.
- Consumes: existing `build_event()`, `_post_json_ordered_response()`, `_send_fail_open_ordered()`.

- [ ] **Step 1: Add failing tests for high-frequency delta coalescing**

Add tests to `tests/unit/test_hook_runtime.py`:

```python
def test_threadsafe_answer_delta_coalesces_many_tokens(monkeypatch):
    monkeypatch.setenv("HERMES_FEISHU_CARD_DELTA_COALESCE_MS", "1000")
    posted = []

    async def fake_send(url, payload, timeout):
        posted.append(payload)

    monkeypatch.setattr(hook_runtime, "_send_fail_open_ordered", fake_send)

    async def run():
        loop = asyncio.get_running_loop()
        base = {
            "source": SourceObject(),
            "message_id": "msg-burst",
            "_hfc_loop": loop,
        }
        for _ in range(1000):
            assert hook_runtime.emit_from_hermes_locals_threadsafe(
                {**base, "text": "x"},
                event_name="answer.delta",
            )
        await asyncio.sleep(0)
        assert posted == []
        await hook_runtime.flush_pending_deltas_for_message("msg-burst")

    asyncio.run(run())

    assert len(posted) == 1
    assert posted[0]["event"] == "answer.delta"
    assert posted[0]["data"]["text"] == "x" * 1000
```

Add a terminal ordering test:

```python
def test_async_terminal_flushes_pending_delta_before_completed(monkeypatch):
    monkeypatch.setenv("HERMES_FEISHU_CARD_DELTA_COALESCE_MS", "1000")
    posted = []

    async def fake_ordered_response(url, payload, timeout):
        posted.append(payload)
        return {"ok": True, "applied": True}

    monkeypatch.setattr(hook_runtime, "_post_json_ordered_response", fake_ordered_response)

    async def run():
        loop = asyncio.get_running_loop()
        base = {
            "source": SourceObject(),
            "message_id": "msg-terminal",
            "_hfc_loop": loop,
        }
        hook_runtime.emit_from_hermes_locals_threadsafe(
            {**base, "text": "hello"},
            event_name="thinking.delta",
        )
        delivered = await hook_runtime.emit_from_hermes_locals_async(
            {**base, "answer": "done"},
            event_name="message.completed",
        )
        assert delivered is True

    asyncio.run(run())

    assert [item["event"] for item in posted] == ["thinking.delta", "message.completed"]
```

- [ ] **Step 2: Run tests to verify RED**

Run:

```bash
.venv/bin/python -m pytest tests/unit/test_hook_runtime.py::test_threadsafe_answer_delta_coalesces_many_tokens tests/unit/test_hook_runtime.py::test_async_terminal_flushes_pending_delta_before_completed -q
```

Expected: fail because `flush_pending_deltas_for_message` does not exist and current code posts per delta.

- [ ] **Step 3: Implement minimal coalescing**

In `hook_runtime.py`:

- Add runtime config fields for delta coalescing.
- Add pending delta state guarded by a threading lock.
- Add `flush_pending_deltas_for_message(message_id: str)`.
- Change `emit_from_hermes_locals_threadsafe()` to route `thinking.delta` / `answer.delta` into pending buffers.
- Change `emit_from_hermes_locals_async()` terminal path to flush pending delta before terminal POST.

- [ ] **Step 4: Verify GREEN**

Run:

```bash
.venv/bin/python -m pytest tests/unit/test_hook_runtime.py -q
```

Expected: all hook runtime tests pass.

---

### Task 2: Read-Only `/hfc` Command Recognition In Hook Runtime

**Files:**
- Modify: `hermes_feishu_card/hook_runtime.py`
- Modify: `hermes_feishu_card/install/patcher.py`
- Test: `tests/unit/test_hook_runtime.py`
- Test: `tests/unit/test_patcher.py` or existing patcher test module if present

**Interfaces:**
- Produces: `handle_hfc_command_from_hermes_locals(local_vars) -> bool`.
- Consumes: sidecar `/commands` endpoint through runtime config base URL.
- Patcher calls command handler before normal LLM execution where safe.

- [ ] **Step 1: Add failing tests for command detection**

Add tests:

```python
def test_handle_hfc_command_posts_command_without_building_normal_event(monkeypatch):
    posted = []

    def fake_sync(url, payload, timeout):
        posted.append((url, payload))
        return True

    monkeypatch.setattr(hook_runtime, "_post_json_sync", fake_sync)

    handled = hook_runtime.handle_hfc_command_from_hermes_locals(
        {
            "source": SourceObject(),
            "message_id": "om-command",
            "text": "/hfc monitor",
        }
    )

    assert handled is True
    assert posted[0][0].endswith("/commands")
    assert posted[0][1]["command"] == "monitor"
    assert posted[0][1]["message_id"] == "om-command"
```

Add non-command test:

```python
def test_handle_hfc_command_ignores_regular_messages(monkeypatch):
    posted = []
    monkeypatch.setattr(hook_runtime, "_post_json_sync", lambda *args: posted.append(args))

    assert hook_runtime.handle_hfc_command_from_hermes_locals(
        {"source": SourceObject(), "message_id": "om-normal", "text": "hello /hfc status"}
    ) is False
    assert posted == []
```

- [ ] **Step 2: Run command detection tests to verify RED**

Run:

```bash
.venv/bin/python -m pytest tests/unit/test_hook_runtime.py::test_handle_hfc_command_posts_command_without_building_normal_event tests/unit/test_hook_runtime.py::test_handle_hfc_command_ignores_regular_messages -q
```

Expected: fail because command handler does not exist.

- [ ] **Step 3: Implement command detection**

In `hook_runtime.py`:

- Add `handle_hfc_command_from_hermes_locals(local_vars: dict[str, Any]) -> bool`.
- Extract text from local vars/message object.
- Parse `/hfc`, `/hfc help`, `/hfc status`, `/hfc doctor`, `/hfc monitor`.
- Build command payload with chat/thread/reply context using existing extraction helpers.
- POST to sidecar `/commands` via `_post_json_sync()`.

In `install/patcher.py`:

- Insert command handler before Hermes enters LLM path for supported handler templates.
- If handler returns true, return `None` or equivalent handled response following existing patcher conventions.

- [ ] **Step 4: Verify command detection**

Run:

```bash
.venv/bin/python -m pytest tests/unit/test_hook_runtime.py tests/unit/test_installer_patcher.py -q
```

Expected: command tests and patcher tests pass.

---

### Task 3: Sidecar `/commands` Endpoint And Card Rendering

**Files:**
- Modify: `hermes_feishu_card/server.py`
- Modify: `hermes_feishu_card/render.py` only if a reusable command-card renderer is needed
- Test: `tests/integration/test_server.py`
- Test: `tests/unit/test_server_commands.py` if existing server tests are too large

**Interfaces:**
- Produces: `POST /commands`.
- Consumes: existing app keys: `METRICS_KEY`, `DIAGNOSTICS_KEY`, `ROUTING_DIAGNOSTICS_KEY`, `PROFILE_DIAGNOSTICS_KEY`, `FEISHU_CLIENT_KEY`.

- [ ] **Step 1: Add failing tests for `/commands`**

Add tests:

```python
async def test_commands_help_sends_read_only_card(aiohttp_client):
    client = RecordingFeishuClient()
    app = create_app(client)
    test_client = await aiohttp_client(app)

    response = await test_client.post("/commands", json={
        "command": "help",
        "chat_id": "oc_secret",
        "message_id": "om_secret",
        "platform": "feishu",
    })

    assert response.status == 200
    body = await response.json()
    assert body["ok"] is True
    assert body["handled"] is True
    assert client.sent_cards
    rendered = json.dumps(client.sent_cards[-1], ensure_ascii=False)
    assert "/hfc status" in rendered
    assert "oc_secret" not in rendered
    assert "om_secret" not in rendered
```

Add monitor test:

```python
async def test_commands_monitor_includes_metrics_without_secrets(aiohttp_client):
    client = RecordingFeishuClient()
    app = create_app(client)
    app[METRICS_KEY].events_received = 12
    app[METRICS_KEY].update_coalesced = 3
    test_client = await aiohttp_client(app)

    response = await test_client.post("/commands", json={
        "command": "monitor",
        "chat_id": "oc_secret",
        "message_id": "om_secret",
        "platform": "feishu",
    })

    assert response.status == 200
    rendered = json.dumps(client.sent_cards[-1], ensure_ascii=False)
    assert "events_received" in rendered
    assert "update_coalesced" in rendered
    assert "oc_secret" not in rendered
```

- [ ] **Step 2: Run server command tests to verify RED**

Run:

```bash
.venv/bin/python -m pytest tests/integration/test_server.py -q
```

Expected: fail because `/commands` does not exist.

- [ ] **Step 3: Implement `/commands`**

In `server.py`:

- Add route `app.router.add_post("/commands", _commands)`.
- Parse command.
- Build allowlisted diagnostic lines.
- Send card using `_send_card()` and `_resolve_route()` with a temporary command event or direct route resolver helper.
- Return `{"ok": True, "handled": True}` when card send succeeds.

- [ ] **Step 4: Verify server commands**

Run:

```bash
.venv/bin/python -m pytest tests/integration/test_server.py -q
```

Expected: integration server tests pass.

---

### Task 4: Safe Summary Redaction

**Files:**
- Modify: `hermes_feishu_card/server.py`
- Test: `tests/integration/test_server.py`

**Interfaces:**
- Produces: `/messages/{message_id}/summary` no longer returns raw `chat_id` or raw Feishu `message_id`.

- [ ] **Step 1: Add failing test for summary redaction**

Add test:

```python
async def test_message_summary_redacts_raw_chat_and_message_ids(aiohttp_client):
    client = RecordingFeishuClient(message_id="om_feishu_secret")
    app = create_app(client)
    test_client = await aiohttp_client(app)

    await post_started_and_completed_events(test_client, chat_id="oc_secret", message_id="msg-runtime")
    response = await test_client.get("/messages/om_feishu_secret/summary")
    body = await response.json()

    assert body["ok"] is True
    assert body["summary"]
    assert "chat_id" not in body
    assert "message_id" not in body
    assert body["chat_id_hash"]
    assert body["message_id_hash"]
```

- [ ] **Step 2: Run test to verify RED**

Run targeted server test.

- [ ] **Step 3: Implement redaction**

Change `_store_card_summary()` to store `chat_id_hash` and `message_id_hash` instead of raw ids.

- [ ] **Step 4: Verify server tests**

Run:

```bash
.venv/bin/python -m pytest tests/integration/test_server.py -q
```

Expected: pass.

---

### Task 5: Version, Docs, Release Notes

**Files:**
- Modify: `pyproject.toml`
- Modify: `README.md`
- Modify: `README.en.md`
- Modify: `README-install.md` if installer examples mention latest release behavior
- Modify: `CHANGELOG.md`
- Modify: `TODO.md`
- Create: `docs/release-notes-v3.8.1.md`
- Modify: `tests/unit/test_docs.py`

**Interfaces:**
- Produces: project version `3.8.1`.
- Produces: public release notes with #74 and `/hfc` read-only command guidance.

- [ ] **Step 1: Add failing docs/version tests**

Update `tests/unit/test_docs.py` to assert:

- `V3.8.1` appears in README and CHANGELOG.
- `docs/release-notes-v3.8.1.md` exists and is linked.
- README mentions issue #74 and `/hfc monitor`.

- [ ] **Step 2: Run docs tests to verify RED**

Run:

```bash
.venv/bin/python -m pytest tests/unit/test_docs.py -q
```

Expected: fail until docs are updated.

- [ ] **Step 3: Update version and docs**

Set `pyproject.toml` version to `3.8.1`; update README, CHANGELOG, TODO, release notes.

- [ ] **Step 4: Verify docs**

Run:

```bash
.venv/bin/python -m pytest tests/unit/test_docs.py -q
```

Expected: pass.

---

### Task 6: Full Verification And Release

**Files:**
- No production code changes unless tests reveal a defect.

**Interfaces:**
- Produces: passing full test suite.
- Produces: local commit(s), then publish after user confirmation.

- [ ] **Step 1: Run relevant test slices**

Run:

```bash
.venv/bin/python -m pytest tests/unit/test_hook_runtime.py tests/integration/test_server.py tests/unit/test_docs.py -q
```

Expected: pass.

- [ ] **Step 2: Run full test suite**

Run:

```bash
.venv/bin/python -m pytest -q
```

Expected: pass.

- [ ] **Step 3: Commit implementation**

Commit in logical chunks or a single release commit if the diff is cohesive.

- [ ] **Step 4: Ask for public release confirmation**

Before pushing/tagging/releasing, summarize:

- commits
- tests
- issue #74 fix
- `/hfc` command scope
- release actions to perform

- [ ] **Step 5: Publish after confirmation**

Publish:

```bash
git push origin <branch-or-main>
git tag -a v3.8.1 -m "V3.8.1"
git push origin v3.8.1
gh release create v3.8.1 --title "V3.8.1" --notes-file docs/release-notes-v3.8.1.md
```

If release-assets workflow creates the release first, edit the release body with `docs/release-notes-v3.8.1.md`.

- [ ] **Step 6: Reply to issue #74**

Comment with:

- fixed in `v3.8.1`
- gateway-side delta coalescing summary
- env override knobs
- upgrade command
- ask reporter to reopen if Qwen thinking still stalls.
