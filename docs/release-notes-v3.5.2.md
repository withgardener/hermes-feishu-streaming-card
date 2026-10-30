# V3.5.2 Release Notes

[中文](release-notes-v3.5.2.md)

V3.5.2 is an installation patch release for Hermes Feishu Streaming Card. It keeps the V3.5.x interactive streaming card runtime intact and focuses on making the project easier to install, package, verify, and publish.

## Highlights

- **One-line install** for macOS/Linux and Windows PowerShell.
- **Release packages** for macOS, Linux, and Windows, with checksum generation through GitHub Actions.
- **Safer macOS `.env` handling**: `install.sh` no longer sources the whole `.env` file and only imports Feishu/sidecar variables.
- **uv/PEP 668 support**: `install.sh` retries pip with `--break-system-packages` when Python reports `externally-managed-environment`.
- **Windows installer validation**: CI parses `install.ps1` on `windows-latest` before release.
- **Forward roadmap**: V3.6.0 planning now covers repair diagnostics, media/file delivery, multi-profile operations, and E2E/release matrices.

## Install

macOS / Linux:

```bash
curl -fsSL https://raw.githubusercontent.com/baileyh8/hermes-feishu-streaming-card/main/install.sh | bash
```

Windows PowerShell:

```powershell
irm https://raw.githubusercontent.com/baileyh8/hermes-feishu-streaming-card/main/install.ps1 | iex
```

From a GitHub Release package:

```bash
tar -xzf hermes-feishu-card-v3.5.2-macos.tar.gz
bash install.sh
```

```powershell
Expand-Archive hermes-feishu-card-v3.5.2-windows.zip
powershell -ExecutionPolicy Bypass -File .\install.ps1
```

## Verification

Automated checks expected before publishing:

```bash
python3 -m pytest -q
bash -n install.sh
```

Release asset dry run should produce:

- `hermes-feishu-card-v3.5.2-macos.tar.gz`
- `hermes-feishu-card-v3.5.2-linux.tar.gz`
- `hermes-feishu-card-v3.5.2-windows.zip`
- `hermes-feishu-card-v3.5.2-checksums.txt`

## Known Boundary

The installer remains fail-closed for real Hermes hook conflicts. If `setup` reports `run.py changed since install`, do not force overwrite it blindly. Back up the Hermes directory and use the V3.6.0 repair/diagnostics plan as the next implementation track.
