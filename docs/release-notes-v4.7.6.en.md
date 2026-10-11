# V4.7.6: split HOME and multi-instance ownership

A system source install such as `/usr/local/lib/hermes-agent` with data in `/root/.hermes`, or several Gateways sharing source, could deliver cards while reporting `runtime_owner_unverified`. This release fixes #384 with explicit source/process HOME binding.

## Changes and upgrade

- `setup --hermes-home /actual/Hermes/HOME` persists the binding in the selected HFC env file; `service.hermes_home` is also supported. Install, PM selection, lifecycle checks and signed heartbeats use the same HOME. Ambient `HERMES_HOME` does not override the sidecar binding.
- Separate HOMEs sharing source have different target digests. Wrong HOME, legacy source-only claims and replay cannot take ownership. Split layouts require Hermes' process-scoped `get_process_hermes_home()`; a task-local profile API is insufficient.
- Doctor loads the same binding via `--env-file` or `HFC_ENV_FILE`; conflicting `--hermes-home` refuses before probes, without rewriting configuration.
- `integrity.last_reason` preserves safe owner diagnostics rather than reporting known reasons as `unknown`. Doctor separates configured binding from live runtime evidence.
- Legacy source-parent identities remain unchanged. Credential-free Docker bootstrap can install hooks before Hermes configuration; split HOME must be an absolute directory containing Hermes `config.yaml`.
- Maintenance jobs capture HOME and refuse execution after configuration reassignment. Split HOME and `service.shared_source: true` refuse card updates before mutation and require terminal maintenance. Integrity fences are not cleared automatically.

Upgrade through the original installer, rerun setup, then restart sidecar, Gateway and Desktop through their existing service owners. Each independent Gateway needs separate HFC config, env file, private state and port. Every sidecar sharing source, including the default HOME, must set `service.shared_source: true`. Drain all source users before upgrades; cross-instance automatic coordination is not provided.

Verify `readiness=ready`, `generation_match=true` and `drain_home_verified=true`. See the [user guide](user-guide.en.md) for configuration and precedence. Old releases reject new HOME-bearing maintenance jobs; finish maintenance before downgrading.

## Validation boundaries

Regression covers persisted config, PM child interpreters, signed HTTP identity isolation, replay, restart and legacy-job refusal. Two actual sidecar processes from an ordinary wheel reject wrong HOME and become ready for the correct owner. Child interpreters using actual Hermes v0.21.6 constants verify that task-local overrides do not alter process binding. Full platform CI, exact merge, assets and public installation remain release gates; final evidence is published with the GitHub Release.

No card layout changes. Reporter NAS/WSL devices and real Feishu messages are not claimed as tested. Upstream gates pin Hermes v0.21.6 (`818c13be1dc4`) and main (`c57331677d7f`), not arbitrary future main.

Thanks to @lanx214, @Lite-G and @7360403-coder for separate-layout, shared-source profile and NAS Docker evidence. Prior credits and release history remain intact; reports are not attributed as code authorship.
