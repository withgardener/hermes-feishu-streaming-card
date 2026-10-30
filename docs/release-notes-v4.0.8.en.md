# V4.0.8

V4.0.8 fixes issue #127: regular conversations uploaded files correctly, but cron completion cards showed only the attachment filename and never uploaded the actual file.

## Cron attachment delivery

- The old cron hook sent the card and returned at the entry of `_deliver_result(...)`, before Hermes called `BasePlatformAdapter.extract_media(...)`; consequently, `media_files` was never produced.
- The new hook is anchored after media extraction and safety filtering. When the card succeeds and `media_files` is non-empty, HFC only clears `cleaned_delivery_content` and lets Hermes continue its existing platform upload, topic routing, and failure handling.
- Text-only cron jobs still let the card own the response and stop native delivery. Sidecar failure remains fail-open and executes the complete Hermes delivery path.
- `build_cron_event(...)` now recognizes Hermes `(path, is_voice)` media tuples, retains attachment summaries, and marks `native_delivery=required`.
- `/health` attachment diagnostics report the actual `native_delivery` policy.

## Upgrade safety

- Existing V4.0.7 cron hooks migrate safely from the function entry to the new anchor after `media_files` filtering.
- Both old and new hooks preserve marker validation, idempotence, exact removal, and refusal of unknown edits.
- Older layouts without a verified Hermes media extraction anchor retain the established fallback instead of receiving an unsafe attachment patch.

## Credits

- Thanks to @zyq2552899783-lgtm for reporting #127 and clearly distinguishing working file uploads in regular conversations from filename-only cron delivery.

## Validation

- Added regressions for cron `media_files` events, card-text/native-attachment ownership, V4.0.7 hook migration, and attachment diagnostics.
- Focused hot-file matrix: `556 passed`.
- Full release gate: `1328 passed, 3 skipped`; `git diff --check` passed.
- A real Hermes 0.18.2 installation migrated successfully, `doctor --explain` passed, and the cron hook is located after `media_files` safety filtering.
- A live Feishu no-agent one-shot cron produced both the completion card and a separate file message; the downloaded file matched the source byte-for-byte and `cron_fallbacks=0`.
- The sdist and wheel built successfully, and the wheel imported as `4.0.8` in a clean Python 3.12 venv. The public tag, assets, and tagged installer remain the final post-publish gate.

## Release assets

- `hermes-feishu-card-v4.0.8-macos.tar.gz`
- `hermes-feishu-card-v4.0.8-linux.tar.gz`
- `hermes-feishu-card-v4.0.8-windows.zip`
- `hermes-feishu-card-v4.0.8-checksums.txt`
