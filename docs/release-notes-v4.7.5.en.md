# V4.7.5: PM runtime binding and DM card actions

- **#382:** CLI detection and plugin binding share the isolated Hermes PM `committed_venv()` probe. External managed environments take precedence over stale checkout venvs. Failed, malformed or missing committed runtimes refuse installation; only absent/unselected PM preserves legacy selection.
- **#374 follow-up:** DM confirmations, model/resume pickers and command-center actions retain the admitted request's exact actor/chat instead of applying group-only policy. Wrong actors/chats and missing proof are rejected; confirmation remains single-use. Token-backed forms/operations use native DM admission only with real platform metadata; sidecar token, permission and expiry checks remain. Unresolved confirmations emit a sanitized WARNING.
- **#384 limitation:** Gateway maintenance ownership currently requires process HOME to match the source directory's parent. A system source install separated from `HERMES_HOME` may deliver cards while reporting `runtime_owner_unverified`. This release does not relax that protection: full support needs a common HOME binding across install, heartbeat, drain markers and update subprocesses.

## Upgrade

Use the existing installer, rerun setup/install, and restart sidecar, Gateway and Desktop through their existing owners. Test fresh cards; old cards do not regain authorization. Ordinary DM users do not need platform-admin privileges as a workaround.

`uv run --frozen` does not provision HFC into Gateway's runtime. `no install spec is available` is a separate package-source prerequisite: use the official installer or provide a verified same-version wheel through `HFC_INSTALL_SPEC`. Version and provenance checks remain strict.

## Validation boundaries

Regression covers real child interpreters, failed/stale PM selection, DM admission, wrong actors/chats, duplicate confirmation and group denial. Ordinary wheels, cross-platform CI, exact merge verification and public assets remain release gates; final evidence is recorded on the GitHub Release.

No card layout changes. Automated callbacks do not establish Personal Edition / Termux device acceptance; #374 remains open for field follow-up. #344 still lacks a complete reproduction; #361 real long-task/mobile acceptance is not claimed.

Thanks to @yulong-ge for the PM report and @ffdxdynotable for DM callback evidence and the earlier Termux security retest. @Nevoker's Python 3.14 contribution remains credited; it shipped in v4.7.2.

Upstream gates now pin Hermes v0.21.6 (`818c13be1dc4`) and 2026-10-11 main (`c57331677d7f`): install, repeat install, doctor, byte-for-byte restore and generated ledger execution order. This does not promise compatibility with arbitrary future main.
