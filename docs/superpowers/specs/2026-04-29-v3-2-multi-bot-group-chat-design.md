# V3.2 Multi Bot Binding And Group Chat Design

## Goal

V3.2.0 adds stable multi-bot routing and formal group chat support while preserving the current sidecar-only architecture and the existing single-bot configuration. The first implementation target is chat-based binding: a Feishu chat, group, or conversation can be bound to a named bot, and all card send/update operations for that chat use that bot's credentials.

## Decisions

- Use progressive routing context.
- V3.2 implements `chat_id -> bot_id -> FeishuClient`.
- V3.2 does not implement Hermes Agent/Profile routing, but reserves optional context fields for future use.
- V3.2 does not implement group trigger filtering. Hermes remains responsible for deciding whether a group message should invoke the Agent.
- Existing single-bot installs continue to work without config changes.

## User-Facing Behavior

Single-bot users keep the current config:

```yaml
feishu:
  app_id: "cli_default"
  app_secret: "..."
```

Multi-bot users can add named bots and bind chats:

```yaml
feishu:
  app_id: "cli_default"
  app_secret: "..."

bots:
  default: default
  items:
    default:
      name: "默认机器人"
      app_id: "cli_default"
      app_secret: "..."
      base_url: "https://open.feishu.cn/open-apis"
      timeout_seconds: 30
    sales:
      name: "销售群机器人"
      app_id: "cli_sales"
      app_secret: "..."

bindings:
  fallback_bot: default
  chats:
    oc_sales_group: sales
    oc_support_group: default
  group_rules:
    enabled: false
```

The current `feishu` section is treated as the implicit `default` bot when `bots.items.default` is absent. This keeps V3.1 configs valid and avoids forcing users through a migration step.

## CLI Experience

The config file remains the source of truth. CLI commands are convenience tools for ordinary users:

```bash
python3 -m hermes_feishu_card.cli bots list --config ~/.hermes_feishu_card/config.yaml
python3 -m hermes_feishu_card.cli bots add sales --config ~/.hermes_feishu_card/config.yaml
python3 -m hermes_feishu_card.cli bots bind-chat oc_sales_group sales --config ~/.hermes_feishu_card/config.yaml
python3 -m hermes_feishu_card.cli bots unbind-chat oc_sales_group --config ~/.hermes_feishu_card/config.yaml
python3 -m hermes_feishu_card.cli bots test sales --chat-id oc_sales_group --config ~/.hermes_feishu_card/config.yaml
```

`bots add` writes app credentials only to the local user config selected by `--config`; it never writes credentials to repository files. Environment variables continue to override the legacy `feishu` section for single-bot use. Multi-bot credentials come from local YAML in V3.2; environment-variable expansion for named bots can be added later without changing the routing model.

## Architecture

### Bot registry

Add a focused registry module responsible for parsing bot config and producing bot clients:

- `BotConfig`: normalized bot id, display name, app id, app secret, base URL, timeout.
- `BotRegistry`: validates config, exposes `get(bot_id)`, `default_bot_id`, and `list_bots()`.
- `FeishuClientFactory`: lazily creates one `FeishuClient` per bot id so each bot has an independent tenant token cache.

The registry rejects invalid bot ids, missing credentials for used bots, unknown binding targets, and duplicate normalized bot ids. It redacts app secrets in all diagnostics.

### Router

Add a small routing layer:

- Build `RoutingContext` from `SidecarEvent`.
- Resolve bot id in this order:
  1. `bindings.chats[event.chat_id]`
  2. future reserved `bindings.agents[event.data.agent_id]` if implemented later
  3. `bindings.fallback_bot`
  4. `bots.default`
  5. implicit `default` bot from the legacy `feishu` section
- Return a route result containing `bot_id`, route reason, and safe diagnostics.

V3.2 only uses chat bindings. Reserved fields must not change behavior until a later release intentionally enables them.

### Event protocol

Keep schema version `1` and add optional data fields rather than requiring a breaking event schema change:

```json
{
  "chat_id": "oc_xxx",
  "data": {
    "chat_type": "group",
    "tenant_key": "tenant_a",
    "agent_id": "reserved",
    "profile_id": "reserved"
  }
}
```

The current hook can continue sending only `chat_id`; the sidecar treats missing optional fields as unknown. The server must not reject events because optional routing context is absent.

### Server flow

On `message.started`:

1. Validate and apply the event to `CardSession`.
2. Resolve the bot for the event chat.
3. Save `message_id -> bot_id` together with `message_id -> feishu_message_id`.
4. Use that bot's client to send the first card.

On update or terminal events:

1. Reuse the saved bot id for that Hermes message.
2. Use the same bot client to update the existing Feishu card.
3. Do not re-route mid-message even if config changes while a message is streaming.

This avoids a class of bugs where the first card is sent by one bot but updates are attempted by another bot.

## Group Chat Support

Group support is defined as: if Hermes emits a Feishu group `chat_id` or `open_chat_id`, the sidecar sends and updates the card in that group using the configured bot route. V3.2 does not decide whether a group message should invoke Hermes. The plugin only renders the card for events Hermes already emits.

Documentation must tell users:

- Invite the target Feishu bot into the group.
- Grant the bot permissions required for sending and updating interactive cards.
- Bind the group chat id to the desired bot if using multi-bot routing.
- If the bot does not respond in a group, first check Hermes Gateway trigger behavior and Feishu app permissions, then check sidecar `/health`.

The reserved `bindings.group_rules` section is documented as inactive in V3.2. It exists to keep future filtering config from being invented ad hoc.

## Health And Diagnostics

`/health` should include safe multi-bot diagnostics:

```json
{
  "routing": {
    "default_bot": "default",
    "bot_count": 2,
    "chat_binding_count": 2,
    "last_route": {
      "chat_id": "oc_sales_group",
      "bot_id": "sales",
      "reason": "bindings.chats"
    },
    "last_route_error": ""
  }
}
```

It must never expose app secrets, tenant tokens, Authorization headers, or raw request bodies. Metrics should continue to count send/update attempts globally; per-bot counters are useful but not required for V3.2.

## Error Handling

- Unknown chat binding target: config load or `doctor` should fail with a clear local error.
- Missing default bot: config load or `doctor` should fail.
- Bot credentials missing for the selected bot: setup and runtime should fail closed for that route; the error should mention the bot id, not the secret.
- Send failure for a message start: keep current behavior, clear the local session and return a 502 to the hook.
- Update failure: keep current retry behavior and diagnostics, but include the bot id in safe diagnostics.
- Config changes during an active stream: existing sessions keep their originally resolved bot id.

## Testing Strategy

Automated tests use fake clients and mock Feishu servers. No real Feishu credentials are used in CI.

Required test coverage:

- Config loading keeps legacy `feishu` working as implicit default bot.
- Config loading accepts multiple named bots and chat bindings.
- Config loading rejects unknown binding bot ids.
- Router resolves chat binding before fallback.
- Router falls back to default for unbound chats.
- Server sends the first card with the routed bot client.
- Server updates the same card using the same bot client even if another chat is bound differently.
- `bots list/add/bind-chat/unbind-chat/test` CLI commands update or read the selected local config.
- `/health` exposes safe routing diagnostics and redacts secrets.
- Group chat ids are accepted as ordinary chat ids; no special trigger filtering is required.

Manual acceptance:

- One Feishu group bound to bot A receives a streaming card from bot A.
- Another group bound to bot B receives a streaming card from bot B.
- An unbound chat uses the fallback bot.
- Existing single-bot config still passes `setup`, `doctor`, and real Feishu smoke.

## Documentation

Update Chinese and English docs:

- README feature list and configuration section.
- Installation/setup guide for multi-bot local config.
- Feishu group setup checklist.
- Troubleshooting entries for "wrong bot replied", "group card not sent", and "unknown bot binding".
- Testing docs with mock coverage and manual group acceptance checklist.

## Non-Goals For V3.2

- No group mention or keyword filtering inside this plugin.
- No Hermes Agent/Profile routing activation.
- No web UI for bot management.
- No shared token cache across sidecar processes.
- No migration script that rewrites all existing single-bot configs; compatibility is handled at load time.

