# Hermes Feishu Streaming Card v4.2.1

## Fixed

- Gateway startup now registers the live Gateway runner before starting authenticated runtime control while installing Feishu command-card adapter methods.
- The first `runtime.hello` / `runtime.heartbeat` can immediately prove complete turn, cron, and API work counts from one `_active_work_count()` sample.
- The first bare Feishu private-chat `/update` after a Gateway restart no longer needs an unrelated warm-up message before maintenance preflight can accept complete runner evidence.

## Safety Boundary

- Maintenance admission is not relaxed: missing, failing, negative, boolean, or non-integer aggregate results remain incomplete evidence and can never be treated as zero work.
- External drain, consecutive heartbeat, `HERMES_HOME` matching, same-version HFC restoration, and every V4.2.0 gate remain unchanged.

## Acceptance

1. Restart Hermes Gateway after installation without sending another message first.
2. Confirm `/health` reports `readiness.status=ready`, `active_work_count_complete=true`, and `drain_home_verified=true`.
3. Make the first Feishu private-chat message a bare `/update`; it should open the 120-second confirmation card instead of reporting incomplete maintenance evidence.

## Release Assets

- `hermes-feishu-card-v4.2.1-macos.tar.gz`
- `hermes-feishu-card-v4.2.1-linux.tar.gz`
- `hermes-feishu-card-v4.2.1-windows.zip`
- `hermes-feishu-card-v4.2.1-checksums.txt`
