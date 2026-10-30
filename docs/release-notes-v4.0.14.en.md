# V4.0.14

V4.0.14 fixes Issue #142: when a long-running task's primary card is no longer present in sidecar memory, consecutive Hermes `Working` heartbeats no longer create multiple contradictory standalone cards.

## Long-running heartbeat lifecycle

- Heartbeats are explicitly non-terminal. A standalone card stays running instead of showing a “Running” title with a “Completed” subtitle.
- Six-minute, nine-minute, and later heartbeats under the same original message anchor use one stable independent message id and PATCH the same card.
- The stable identity includes the chat and original user-message anchor, isolating concurrent long-running tasks in the same chat.
- A final `message.completed` event still resolves the reply-anchor alias and completes that same card, so the fallback card is not left running forever.

## Reliable delivery boundary

- An `unknown` delivery outcome still falls back only to the fixed generic warning and does not repeat the original runtime notice.
- After an uncertain outcome, later heartbeats reuse the same independent identity and return to the existing lifecycle instead of creating another card.
- Existing `not_sent`, unrecognized-notice, non-Feishu, and other fail-open behavior is unchanged.

## Validation

- Regression coverage includes non-terminal classification, same-anchor reuse, different-anchor isolation, orphaned six/nine-minute updates, final completion, and recovery after an unknown delivery outcome.
- Full automation passed: `1488 passed, 3 skipped`; sdist/wheel build, isolated Python 3.12 `site-packages` import of `4.0.14`, and CLI smoke all passed.
- Thanks to @ati121 for reporting the long-task duplicate-card and contradictory-status symptom in Issue #142.

## Release assets

- `hermes-feishu-card-v4.0.14-macos.tar.gz`
- `hermes-feishu-card-v4.0.14-linux.tar.gz`
- `hermes-feishu-card-v4.0.14-windows.zip`
- `hermes-feishu-card-v4.0.14-checksums.txt`
