# V4.0.19 Release Notes

Released: 2026-07-22

V4.0.19 is a one-line installer hotfix. It prevents an invalid `pip --user` install after the Hermes venv has been selected and makes every pip failure stop the upgrade before an older setup can run.

## Fixes

- `install.sh` omits `--user` when Python comes from `HERMES_DIR/venv`, `.venv`, or a Gateway venv.
- The system-Python fallback still defaults to a user install, and an explicit `HFC_PIP_USER` remains authoritative.
- Failed initial installs and `--break-system-packages` retries preserve the real pip exit status, print the real error, and stop immediately instead of reporting false upgrade success.

## Verification

- Focused installer regression: `22 passed, 3 skipped`.
- Full automation: `1513 passed, 4 skipped`.
- A fresh Hermes venv with no `HFC_PIP_USER` installed successfully and imported the target version from venv `site-packages`.
- Release assets:
  - `hermes-feishu-card-v4.0.19-macos.tar.gz`
  - `hermes-feishu-card-v4.0.19-linux.tar.gz`
  - `hermes-feishu-card-v4.0.19-windows.zip`
  - `hermes-feishu-card-v4.0.19-checksums.txt`

## Upgrade

```bash
export HFC_VERSION=v4.0.19
curl -fsSL https://raw.githubusercontent.com/baileyh8/hermes-feishu-streaming-card/main/install.sh | bash
```
