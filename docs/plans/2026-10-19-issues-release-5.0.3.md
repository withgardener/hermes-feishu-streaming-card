# HFC v5.0.3 combined issue/PR release plan

Authorization: Bailey asked on 2026-10-19 to resolve the current batch together and publish. Earlier instruction assigns implementation/testing to Sol subagents. Preferred checkout is the preferred HFC project checkout; baseline main 304afc8e5cd36793c29d1d832f55a767f84bbf6d, version 5.0.2. Two unrelated untracked August documents are preserved.

1. Review and reproduce #437/#438 strict channel-pin AST compatibility, #392/#436 optional per-invocation token rate, and #430 expired-interaction continuation. Preserve authors and original PR commits. Fix concrete defects with focused regressions, private HOME/state, and source-bound upstream evidence. Never touch production.
2. Review pending Dependabot PRs #388/#389/#390/#439 against official metadata, runtime requirements and existing CI contracts. Integrate eligible changes into one candidate. Keep optional output_rate off by default; do not infer generation speed from turn wall-clock or text length.
3. Run focused regression, Ruff/mypy, full preflight with verified fixed-tag Git fixture, separate pinned upstream matrix, and ordinary wheel/child-process install/repeat/restore acceptance. Record source/local HTTP/platform API/client evidence separately. Actual mobile/iOS/client gaps cannot become claimed passes.
4. Update version metadata, changelog, bilingual README credits, release notes and affected docs. Open one integration PR, require all release CI checks, merge verified tree, create annotated v5.0.3 tag, verify tag CI/assets/checksums and isolated public installation.
5. Reply to relevant issues/PRs with released scope and evidence. Close only resolved, supported claims; keep missing reporter/client evidence explicit. Clean only task-owned unused worktrees/envs/temp artifacts after reference audits; retain deliverables, logs, hashes, shared fixtures and original files.

Independent tasks: Sol A owns #438 installer/source contract review; Sol B owns #436 metrics/config/render/checkpoint contract review; Sol C owns #430 interaction/continuation review. Root owns integration, dependency metadata, full/release gates and publication.

