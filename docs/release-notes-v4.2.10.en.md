# Hermes Feishu Streaming Card V4.2.10

[中文](release-notes-v4.2.10.md) | [English](release-notes-v4.2.10.en.md)

V4.2.10 closes two runtime gaps confirmed by the repository audit: non-loopback sidecar callbacks and result reads previously relied only on application-level tokens, and the interaction card displayed a timeout that the sidecar did not enforce. This release also adds cross-platform CI and baseline security automation.

## Fixes

- **Dedicated sidecar request authentication**: `sign_sidecar_request(...)` and `SidecarRequestProofVerifier` use the `hfc-sidecar-request-v1` domain and bind the HTTP method, canonical path, and raw body. With non-loopback event authentication enabled, `/card/actions`, `/interactions/{id}`, and `/messages/{id}/summary` verify the proof before parsing or returning state.
- **Absolute interaction deadlines**: the sidecar records `requested_at` and computes `expires_at` when it receives `interaction.requested`. Buttons, form submits, result polling, and periodic cleanup share the same idempotent transition under the existing session lock.
- **Late callback rejection**: an expired interaction becomes `failed`, returns an expired result, and PATCHes the original card. Direct buttons and multi-select/custom-answer forms cannot change it back to completed.
- **Gateway timeout convergence**: once the poll deadline is reached, the Gateway sends one best-effort distinct `interaction.failed`; it never replays the original `interaction.requested`, and send failure remains fail-open.
- **Cleanup no longer blocks forever**: only an unexpired pending interaction prevents retention cleanup. The periodic loop transitions and refreshes expired state before ordinary cleanup.

## CI and security gates

- Full pytest runs on Ubuntu with Python 3.9, 3.10, 3.11, and 3.12 and on macOS 3.12. Windows 3.12 runs a fixed portable runtime/server suite plus dedicated PowerShell installer and migration contracts; tests that require POSIX `dir_fd`, mode bits, systemd, or bash remain on POSIX runners.
- Feishu SDK compatibility, the PowerShell installer, and Docker Compose runtime smoke remain in place.
- `actions/checkout v7.0.1`, `actions/setup-python v7.0.0`, and `github/codeql-action v4` were verified to use Node 24 and are pinned to immutable 40-character commit SHAs.
- CodeQL scans Python on push, pull request, and weekly schedule. Dependabot checks pip and GitHub Actions weekly.

## Compatibility and safety boundary

- Default loopback deployments remain compatible; no proof is invented when a valid transport root is unavailable.
- Callback tokens and exact chat binding remain defense in depth and are not treated as network authentication.
- Missing, expired, cross-method/path/body, and replayed proofs receive the same 401 response. The response and `sidecar_request_auth_rejections` metric contain no signatures, identifiers, bodies, or choices.
- This release does not modify `legacy/`, hand-edit Hermes `gateway/run.py`, or expand patcher ownership.

## Upgrade

macOS / Linux:

```bash
export HFC_VERSION=v4.2.10
bash install.sh
```

Docker:

```bash
export HFC_VERSION=v4.2.10
bash install-docker.sh
```

Windows PowerShell:

```powershell
$env:HFC_VERSION = "v4.2.10"
irm "https://raw.githubusercontent.com/baileyh8/hermes-feishu-streaming-card/v4.2.10/install.ps1" | iex
```

After upgrading:

```bash
hermes-feishu-card doctor --config ~/.hermes/config.yaml --hermes-dir ~/.hermes/hermes-agent --explain
hermes-feishu-card status --config ~/.hermes/config.yaml
```

## Verification boundary

- Session/lifecycle/render/hook unit regressions: `556 passed`.
- Full server/clarify integration regression: `297 passed`.
- Fixed Windows portable runtime/server list (equivalent local execution): `1272 passed`; the exact Windows-runner result is gated by the PR checks.
- CI workflow contracts: `16 passed`.
- Full pytest in the isolated v4.2.10 runtime: `2475 passed, 6 skipped`.
- Exact merge SHA, post-tag Release assets, and public-tag installation results are added to the Release after the publication flow completes.

Expected Release assets:

- `hermes-feishu-card-v4.2.10-macos.tar.gz`
- `hermes-feishu-card-v4.2.10-linux.tar.gz`
- `hermes-feishu-card-v4.2.10-windows.zip`
- `hermes-feishu-card-v4.2.10-checksums.txt`
