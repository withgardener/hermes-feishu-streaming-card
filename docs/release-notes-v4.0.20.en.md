# V4.0.20 Release Notes

Release date: 2026-07-22

V4.0.20 fixes Issue #153: when the sidecar has already accepted an existing-card `system.notice` and queued its asynchronous PATCH, the hook no longer emits a false gray warning claiming that delivery could not be confirmed.

## Fixes

- `/events` returns `delivery.outcome=accepted` only after the notice is applied and the asynchronous PATCH task is queued; the response must also contain `applied=true`.
- The hook recognizes explicit `accepted + applied=true` acknowledgements while incomplete acknowledgements remain fail-open.
- Initial independent notice create/reply still returns `delivered`, `not_sent`, or `unknown`; this fix neither waits for every PATCH nor represents queued work as delivered.

## Observability

- `/health.metrics.notice_update_failures` counts accepted notice update tasks that still fail after internal PATCH retries are exhausted.
- `last_update_error` can append only validated `status_code` / `api_code` values. Response bodies, tokens, URLs, credentials, and raw identifiers remain excluded.

## Verification

- Focused hook/server regressions cover explicit accepted acknowledgements, missing applied state, queued existing-card updates, retry exhaustion, and redacted diagnostics.
- Full automation: `1517 passed, 4 skipped`.
- The sdist/wheel build and isolated Python `site-packages` import both report version `4.0.20`.
- Release assets:
  - `hermes-feishu-card-v4.0.20-macos.tar.gz`
  - `hermes-feishu-card-v4.0.20-linux.tar.gz`
  - `hermes-feishu-card-v4.0.20-windows.zip`
  - `hermes-feishu-card-v4.0.20-checksums.txt`

## Upgrade

```bash
export HFC_VERSION=v4.0.20
curl -fsSL https://raw.githubusercontent.com/baileyh8/hermes-feishu-streaming-card/main/install.sh | bash
```
