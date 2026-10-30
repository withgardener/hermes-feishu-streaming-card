# Hermes Feishu Streaming Card V4.2.8

Release date: 2026-08-05

V4.2.8 fixes the credential-persistence gap found by the public v4.2.7 installation acceptance.

## Fixes

- `install.sh` persists `FEISHU_APP_ID` and `FEISHU_APP_SECRET` supplied through the process environment into the selected private `.env` instead of keeping them only for the installer process.
- `install-docker.sh` uses the same persistence contract for non-interactive container installs and Compose setup.
- `install.ps1` persists process credentials on Windows and normalizes replacement of an existing dotenv assignment.
- POSIX installers restrict the credential file to mode `0600`, and none of the three installers writes credential values to logs.

## Verification

- New macOS/Linux installer, Docker installer, and PowerShell installer regressions cover process credentials, a secret containing spaces, dotenv persistence, and log redaction.
- The complete release gate still covers Python 3.9/3.12, Windows PowerShell, Docker Compose, Feishu SDK, the exact main merge SHA, public-tag installation, and Release asset checksums.

## Install

macOS / Linux:

```bash
export FEISHU_APP_ID=cli_xxx
export FEISHU_APP_SECRET=xxx
export HFC_VERSION=v4.2.8
bash install.sh
```

Windows PowerShell:

```powershell
$env:FEISHU_APP_ID = "cli_xxx"
$env:FEISHU_APP_SECRET = "xxx"
$env:HFC_VERSION = "v4.2.8"
irm "https://raw.githubusercontent.com/baileyh8/hermes-feishu-streaming-card/v4.2.8/install.ps1" | iex
```

After installation:

```bash
hermes-feishu-card doctor --config /path/to/config.yaml --hermes-dir /path/to/hermes --explain
hermes-feishu-card status --config /path/to/config.yaml
```

The installed Python import should resolve from the target environment's `site-packages`, with package and distribution versions both reporting `4.2.8`.

## Release assets

- `hermes-feishu-card-v4.2.8-macos.tar.gz`
- `hermes-feishu-card-v4.2.8-linux.tar.gz`
- `hermes-feishu-card-v4.2.8-windows.zip`
- `hermes-feishu-card-v4.2.8-checksums.txt`

Verify each download against the SHA-256 checksums file.
