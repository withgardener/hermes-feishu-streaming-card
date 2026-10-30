# Hermes Feishu Streaming Card V4.2.7

Release date: 2026-08-05

V4.2.7 resolves Issue #193 and integrates the Windows installation and detached-runner fixes from PR #180 and PR #181.

## Fixes

- **Issue #193 — cold-import probe timeouts**: both the Feishu SDK check and HFC runtime import probe now allow 30 seconds instead of 8 seconds, covering Windows/Python cold starts while keeping bounded failure.
- **Issue #193 — manifest paths**: new ownership manifests and recovery plans always write POSIX `/` relative paths; exact legacy Windows backslash Base paths remain reinstallable and recoverable.
- **PR #180 — parent `HERMES_HOME`**: config discovery checks the parent `HERMES_HOME` layout commonly used on Windows instead of missing a parent-level configuration.
- **PR #181 — detached runner PID**: a Windows venv detached launcher can safely rebind an owned pidfile from its verified parent launcher to the real runner child.
- **PowerShell failure propagation**: `install.ps1` explicitly checks native `pip` and `setup` exit codes. Failure stops immediately and never continues to print `done`.

## Safety boundaries

- PID rebinding requires `win32 + detached + exact process token + pidfile PID == runner parent PID`, followed by a strict `{pid, token, manager}` read-back check.
- Legacy path compatibility accepts only the exact expected relative path; absolute paths, traversal, additional components, and extra suffixes remain rejected.
- Unknown Windows launchers, managers, tokens, or parent evidence remain fail-closed; other platforms are unchanged.
- The tag is created only after a clean detached worktree verifies the exact main merge SHA.

## Install

```bash
export HFC_VERSION=v4.2.7
bash install.sh
```

Windows PowerShell:

```powershell
$env:HFC_VERSION = "v4.2.7"
irm "https://raw.githubusercontent.com/baileyh8/hermes-feishu-streaming-card/v4.2.7/install.ps1" | iex
```

After installation:

```bash
hermes-feishu-card doctor --config /path/to/config.yaml --hermes-dir /path/to/hermes --explain
hermes-feishu-card status --config /path/to/config.yaml
```

The installed Python import should resolve from the target environment's `site-packages`, with package and distribution versions both reporting `4.2.7`.

## Release assets

- `hermes-feishu-card-v4.2.7-macos.tar.gz`
- `hermes-feishu-card-v4.2.7-linux.tar.gz`
- `hermes-feishu-card-v4.2.7-windows.zip`
- `hermes-feishu-card-v4.2.7-checksums.txt`

Verify each download against the SHA-256 checksums file.
