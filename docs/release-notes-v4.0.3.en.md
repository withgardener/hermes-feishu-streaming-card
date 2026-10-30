# V4.0.3

V4.0.3 fixes the stale-hook path that remained in issue #106 after V4.0.2: upgrading the runtime package and restarting sidecar/Gateway without reinstalling the completion hook could still send the card answer again as gray native text.

## Root cause

- The V4.0.1/V4.0.2 response media split lives in the new completion hook, so `gateway/run.py` changes only after `install` runs again.
- A V4.0.0 hook still sends completion to the sidecar and updates the card. Hermes `BasePlatformAdapter` then sends cleaned answer text before native image/file delivery, producing card text plus gray text plus media.

## Fix

- When a media-bearing `message.completed` event is explicitly accepted by the sidecar, runtime records the chat and card-visible answer.
- The next Feishu adapter `send` is acknowledged without delivery only when both chat and text match exactly; the state is consumed once.
- `send_multiple_images`, `send_image_file`, `send_document`, `send_video`, and `send_voice` remain unchanged, so Hermes native media delivery continues.

## Safety boundaries

- Other chats, different text, later repeated text, non-media completions, and non-Feishu platforms retain their original behavior.
- Sidecar rejection, timeout, or failure registers no suppression, preserving the complete native fail-open response.
- New completion hooks still split the response first; this runtime path is a compatibility fallback for older hooks.

## Credits

- Thanks to @blakejia for retesting V4.0.2 and providing the screenshot that exposed the stale-hook upgrade path.
- Thanks to @ShakuOvO for the original #106 report and @blakejia for independently confirming it on Hermes `0.18.2`.

## Verification

- Hook/patcher/install/server hot-path matrix: `513 passed`.
- Full suite: `1269 passed, 3 skipped`; `git diff --check` passed.
- Local package: the sdist and wheel built successfully, and a clean venv imported version `4.0.3` from `site-packages`.

## Release assets

- `hermes-feishu-card-v4.0.3-macos.tar.gz`
- `hermes-feishu-card-v4.0.3-linux.tar.gz`
- `hermes-feishu-card-v4.0.3-windows.zip`
- `hermes-feishu-card-v4.0.3-checksums.txt`
