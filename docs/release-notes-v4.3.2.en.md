# Hermes Feishu Streaming Card V4.3.2

[中文](release-notes-v4.3.2.md) | [English](release-notes-v4.3.2.en.md)

V4.3.2 fixes the two Feishu card-dialect failures reported in Issue #227 after a clarify/approval click. V4.3.1 could wake Hermes through the WebSocket callback, but it sent the pending choice as a legacy interaction card and then treated that same message as a schema 2.0 streaming PATCH target. The Gateway also returned a schema 2.0 card as a raw callback card. Feishu rejects those two cross-dialect operations as `230099/200800` and `200673`, respectively.

## Fixed

- The schema 2.0 streaming message remains the only PATCH owner for the turn. Sending a legacy clarify/approval card no longer promotes that message into `FEISHU_MESSAGE_IDS_KEY`.
- The legacy interaction card owns only the user's selection. On completion or expiry, `/card/actions` returns a noninteractive terminal card in the same legacy dialect, without buttons, forms, callback tokens, or other callback credentials.
- After a choice resolves, later Hermes answer/thinking/tool/terminal updates resume PATCHing the original schema 2.0 streaming message. Standard interactions and runtime admission now follow the same ownership rule.
- A new Gateway callback guard converts any accidental schema 2.0 card returned by the sidecar into a success toast for both direct-select and form-submit paths, preventing a raw callback card from triggering `200673`.
- A dialect-aware Feishu fake now rejects cross-dialect PATCH operations in regression tests. Coverage includes standard interactions, runtime admission, repeated interactions, expiry, predecessor PATCH failure, and subsequent streaming recovery.

## Safety boundaries

- Callback tokens, interaction IDs, chat/operator/profile binding, expiry, idempotency, runtime admission, and fail-open behavior are unchanged.
- Legacy terminal cards contain no actionable control or callback credential. Logs and tests do not retain real chat/message/user IDs, user answers, or secrets.
- The archived `legacy/` runtime, Hermes patch ownership, Feishu token/send APIs, and ordinary card-update API are unchanged.
- Empty-value `/card` fallback remains a separate follow-up and is not folded into this card-dialect fix.

## Verification status

- Combined renderer, Gateway hook, sidecar server, and Feishu SDK compatibility regression: `932 passed, 1 skipped`.
- The isolated Python 3.12 candidate ran full pytest with `3253 passed, 5 skipped in 413.97s`. PEP 517 sdist/wheel builds passed. In a fresh venv pinned to `lark-oapi 1.6.8` with HFC installed only from the candidate wheel, package and distribution versions were both `4.3.2`, import origin was inside that venv's `site-packages`, exactly one Hermes plugin entrypoint was present, all 24 provenance slices were packaged, and the main CLI plus `enable/disable --help` exited 0.
- GitHub CI, exact merge SHA, public tag/install, Release assets, and checksums are recorded in [release readiness](release-readiness.en.md) and are marked passed only after completion.
- Real Feishu acceptance for a direct choice and a custom-input form remains a distinct release step. Automation is not presented as real-client evidence; if no approved test session is available before publishing, Issue #227 stays open for reporter retesting.

## Credits

- Thanks @saulgoodmanngabriel for the complete Hermes 0.20.0 + hfc 4.3.1 + lark-oapi 1.6.8 reproduction, the `230099/200800` counters, and the decisive direct-API comparison in which ordinary card messages succeeded while interaction-card messages failed.
- Thanks @lyp88997 for the toast-only `200673` fix direction and the contrasting update observation that helped separate the callback-response failure from the message-update failure.
