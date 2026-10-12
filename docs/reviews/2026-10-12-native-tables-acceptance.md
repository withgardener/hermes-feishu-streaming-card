# Native tables / #391 acceptance

- Source: PR #391 `18cd440dbe5c` plus the v4.7.7 lossless fallback changes.
- Failing reproduction: 18 failures before the fix in the expanded native-table tests (long header/data, Chinese/ASCII, default/task and mixed tables). These are rendering tests, not platform evidence.
- Focused implementation checks: 499 passed across native tables, text, render, presentation, config and reading-preset HTTP tests. Release/docs/server batch: 782 passed and one newline-normalization expectation corrected; the targeted handoff rerun passed both cases. Full cross-platform CI remains required before publishing.
- Real Feishu API: synthetic mixed native/Markdown card sent only to the existing dedicated test group; CardKit update succeeded. A separate 5,000-character Markdown header card entity was accepted without sending another message.
- Real desktop: native header/rows and surrounding prose were readable in the light and dark themes on Feishu 8.1.17. The long Markdown cell had an internal scrollbar; scrolling to its end visibly showed `TAIL_391_OK`, followed by the outside `END_391_OK` marker. Source payload retained the entire cell.
- Scope: this proves the direct card-render/CardKit/display path, not a new Gateway/model round trip. Android/iOS and narrow-window coverage are not implied. Bailey explicitly approved a desktop/API-scoped v4.7.7 release on 2026-10-12, with native tables disabled by default and mobile limitations documented. The original light theme and 100% window scale were restored; no further foreground UI automation is used. Test messages are recalled after inspection; private identifiers and credentials are not stored in repository evidence.

- Width regression: 1–50 supported columns now always sum to 100%; the original 15% minimum produced 105% for seven columns and 750% for fifty, while a single column stopped at 70%.
