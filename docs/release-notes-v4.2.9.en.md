# Hermes Feishu Streaming Card V4.2.9

Release date: 2026-08-09

V4.2.9 closes the implementation gaps behind Issue #197, PR #196, and PR #199: completed-card quotes retain real answer context, slow slash confirmations no longer block Feishu callbacks, and authenticated multi-select/free-text forms are production-ready.

## Fixes and improvements

- **Quoted reply context (Issue #197)**: a completed card's `config.summary` contains a single-line answer excerpt capped at 120 characters. Progress-handoff, waiting, and failed cards keep their status summaries.
- **Slow command confirmation (PR #196)**: slash-confirm resolves outside the Feishu callback deadline and then PATCHes the original card. A failed PATCH sends a follow-up result card. Pending state is claimed before scheduling, while rejected or raised submission falls back synchronously without losing or duplicating the action.
- **Multi-select and custom answers (PR #199)**: clarify cards support native multi-select, numbered single-choice buttons, and an “Other” input. Unrelated PATCHes freeze while input is pending, and the footer displays the configured expiry.
- **Hermes compatibility**: patch injection works with clarify callbacks both with and without a `multi_select` parameter.

## Security boundary

- Form action names carry an unguessable callback token; `interaction_id` is never accepted as a credential.
- The sidecar requires both an exact callback token and an exact non-empty callback chat binding.
- `/events` is posted once. An ambiguous response is followed only by a read-only interaction lookup, never by event replay.
- Interaction logs omit raw IDs, URLs, user choices, response bodies, and error text.

## Contributors

- Thanks to @zayn-0101 for PR #196.
- Thanks to @Cassius0924 for PR #199.

## Install

macOS / Linux:

```bash
export HFC_VERSION=v4.2.9
bash install.sh
```

Windows PowerShell:

```powershell
$env:HFC_VERSION = "v4.2.9"
irm "https://raw.githubusercontent.com/baileyh8/hermes-feishu-streaming-card/v4.2.9/install.ps1" | iex
```

Then run:

```bash
hermes-feishu-card doctor --config /path/to/config.yaml --hermes-dir /path/to/hermes --explain
```

The installed Python import should resolve from the target environment's `site-packages`, with package and distribution versions both reporting `4.2.9`.

## Release assets

- `hermes-feishu-card-v4.2.9-macos.tar.gz`
- `hermes-feishu-card-v4.2.9-linux.tar.gz`
- `hermes-feishu-card-v4.2.9-windows.zip`
- `hermes-feishu-card-v4.2.9-checksums.txt`
