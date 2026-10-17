# V5.0.2: localized transient-notice recall

This patch fixes [#434](https://github.com/baileyh8/hermes-feishu-streaming-card/issues/434): known busy receipts did not reach HFC's recall scheduling when Hermes used its simplified-Chinese language pack. Installable availability is determined by the GitHub Release tag and assets.

## Changes

- Share complete-template recognition between the busy entry point and recall decision for redirect, interrupt, steer and active-subagent steer receipts. Cover the pinned English and simplified-Chinese wording, including native single-line activity details. Successful sends retain the existing 15-second recall on the original profile/chat/thread route.
- Apply the existing bare English compression-status policy to `⏳ 正在压缩上下文` and its `...` form.
- Narrow the old English redirect prefix match to a full receipt, preserving appended content and onboarding guidance. Unknown translations, custom wording and similar emoji do not authorize recall.

Wording and send-path evidence come from Hermes `e06df9c2eae6901f4c88f464e0ae6e753c0428b8`, specifically `gateway/run_busy.py` and `locales/{en,zh}.yaml`. This patch does not load Hermes i18n dynamically or claim support for every language pack.

## Preserved behavior

That upstream revision appends important queued-message, later-processing and `/stop` guidance to subagent-working and compression-demotion notices. Those complete messages stay visible; bare subagent-working status is also outside the recall list. Queue receipts, onboarding, appended content and unknown content remain visible. Hermes continues to edit ongoing Working heartbeats in place and clean them up at the end of the turn; HFC adds no periodic recall.

The 15-second delay, send-success checks, route identity, duplicate registration and deletion boundaries remain unchanged. Python support, card layout and configuration defaults are unchanged. Use the official installation flow to update to `v5.0.2`, retaining your config, env file, Hermes HOME and service ownership. See the [upgrade guide](upgrade-v4-to-v5.en.md) and [notice lifecycle](wiki/notice-lifecycle.md).

## Verification boundaries

Candidate `74f409e` passed **146 focused tests**, local full regression with **6687 passed / 33 skipped**, and all **18 CI checks**. Local skips comprise 21 opt-in pinned-source checks, one PM fixture, six SDK checks including a collection skip, one Windows-sharing check and four PowerShell checks; they are not local passes. Candidate CI separately exercises the pinned-source and platform gates.

Tests execute minimal SHA/digest-bound upstream compose-method slices and the generated busy send hook, covering both languages, activity details, failures and retained text. Coverage also includes the real adapter text egress, loopback HTTP, repeated scheduling and default/work routes. An independent `-I` child executes the new classifier and busy entry point from an ordinary non-editable wheel; all 136 package resources match candidate source bytes. Version 5.0.2 metadata, the exact merge/tag, asset checksums and isolated public installation follow the [release playbook](wiki/release-playbook.md).

Fixed-source slices do not establish complete execution of that Hermes/Gateway version. This patch adds no real Feishu, desktop, Android or iOS acceptance; automation is not a substitute for those results.

## Credits

Thanks to [Timeral](https://github.com/Timeral) for the Chinese-environment reproduction, English classifier comparison and source analysis in [#434](https://github.com/baileyh8/hermes-feishu-streaming-card/issues/434).
