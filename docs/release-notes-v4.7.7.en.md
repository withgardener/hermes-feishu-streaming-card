# V4.7.7: preserve complete table content

This release integrates the opt-in native tables from PR #391 and fixes long-cell truncation found before merging. `card.native_tables` defaults to `false`; enabling it gives eligible body tables native column widths and automatic row height.

- If any normalized header or cell exceeds 1,200 characters, keep the complete table as Markdown. Never replace its tail with an ellipsis. Other eligible tables still convert.
- When a Markdown header or row cannot be safely split, retain the whole table rather than a fold notice. Shared byte, element and table budgets still route oversized cards to the existing full-content handoff.
- Native conversion remains disabled by default. Profile/bot overrides are supported; restart the sidecar after configuration changes. Older clients have different native-component capabilities; the default Markdown path remains available.

Regression coverage includes 1,199/1,200/1,201/5,000 characters, Chinese/ASCII, headers/data, classic/task presentation, mixed tables and oversized full-content handoff. Full CI, exact-merge verification, release assets and ordinary public-package installation remain release gates. Platform and client acceptance are reported separately from unit tests.

Thanks to [ywarmy](https://github.com/ywarmy) for the native-table implementation and CardKit API evidence in [PR #391](https://github.com/baileyh8/hermes-feishu-streaming-card/pull/391). Original authorship and historical contributor credits are preserved.

Real Feishu CardKit create/update passed. Feishu 8.1.17 desktop light/dark-theme inspection confirmed readable native tables and a scrollable Markdown cell reaching its tail marker; a 5,000-character header passed API validation. Android/iOS and a new Gateway/model round trip are unverified. See the [acceptance record](reviews/2026-10-12-native-tables-acceptance.md).

Release scope explicitly approved: desktop/API verification, native tables off by default, Android/iOS unverified. Column percentages now sum to 100% for every supported column count, including one and seven or more columns.
