# V3.2 Multi Bot Group Chat Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add V3.2 multi-bot binding and formal group chat support through chat-based routing while keeping existing single-bot installs compatible.

**Architecture:** Keep the sidecar-only model. Add a small bot registry and routing layer that resolves `chat_id -> bot_id -> FeishuClient`; the server stores the resolved bot per Hermes message so send and update operations use the same bot for the entire stream. Event schema remains version `1`; optional routing context fields are accepted but not required.

**Tech Stack:** Python 3.9+, aiohttp sidecar server, PyYAML config, pytest/pytest-asyncio, existing Feishu CardKit client.

---

## File Structure

- Create `hermes_feishu_card/bots.py`: bot config normalization, registry, routing context, route result, lazy client factory, safe diagnostics.
- Modify `hermes_feishu_card/config.py`: add `bots` and `bindings` defaults, validate known mapping sections, preserve legacy `feishu` behavior.
- Modify `hermes_feishu_card/events.py`: accept optional `data.chat_type`, `data.tenant_key`, `data.agent_id`, and `data.profile_id` without requiring them.
- Modify `hermes_feishu_card/server.py`: route `message.started` to a bot client, store `message_id -> bot_id`, update cards through the same client, expose routing health diagnostics.
- Modify `hermes_feishu_card/runner.py`: build either a single legacy Feishu client or a multi-bot client factory from loaded config.
- Modify `hermes_feishu_card/cli.py`: add `bots list/add/bind-chat/unbind-chat/test` commands and include bot diagnostics in `doctor`.
- Modify `config.yaml.example`: document multi-bot and chat binding sections with secrets left empty.
- Modify `README.md`, `README.en.md`, `docs/testing.md`, `docs/testing.en.md`, `docs/e2e-verification.md`, `docs/e2e-verification.en.md`: document V3.2 behavior, group checklist, troubleshooting, and test coverage.
- Create `tests/unit/test_bots.py`: registry, routing, validation, and redaction tests.
- Modify `tests/unit/test_config.py`: multi-bot config load tests and legacy compatibility tests.
- Modify `tests/integration/test_server.py`: routed send/update lifecycle tests.
- Modify `tests/integration/test_cli.py`: bot CLI command tests.
- Modify `tests/unit/test_docs.py`: V3.2 doc guards.

## Task 1: Config Schema And Bot Registry

**Files:**
- Create: `hermes_feishu_card/bots.py`
- Modify: `hermes_feishu_card/config.py`
- Test: `tests/unit/test_bots.py`
- Test: `tests/unit/test_config.py`

- [ ] **Step 1: Write failing bot registry tests**

Add `tests/unit/test_bots.py`:

```python
import pytest

from hermes_feishu_card.bots import BotRegistry, RoutingContext


def test_legacy_feishu_config_becomes_implicit_default_bot():
    registry = BotRegistry.from_config(
        {
            "feishu": {
                "app_id": "cli_default",
                "app_secret": "secret",
                "base_url": "https://open.feishu.cn/open-apis",
                "timeout_seconds": 30,
            }
        }
    )

    bot = registry.get("default")
    assert registry.default_bot_id == "default"
    assert bot.app_id == "cli_default"
    assert bot.app_secret == "secret"


def test_named_chat_binding_wins_before_fallback():
    registry = BotRegistry.from_config(
        {
            "feishu": {"app_id": "cli_default", "app_secret": "default-secret"},
            "bots": {
                "default": "default",
                "items": {
                    "sales": {"app_id": "cli_sales", "app_secret": "sales-secret"},
                },
            },
            "bindings": {
                "fallback_bot": "default",
                "chats": {"oc_sales": "sales"},
            },
        }
    )

    result = registry.resolve(RoutingContext(chat_id="oc_sales"))

    assert result.bot_id == "sales"
    assert result.reason == "bindings.chats"


def test_unbound_chat_uses_fallback_bot():
    registry = BotRegistry.from_config(
        {
            "feishu": {"app_id": "cli_default", "app_secret": "default-secret"},
            "bindings": {"fallback_bot": "default"},
        }
    )

    result = registry.resolve(RoutingContext(chat_id="oc_unknown"))

    assert result.bot_id == "default"
    assert result.reason == "bindings.fallback_bot"


def test_unknown_binding_target_is_rejected():
    with pytest.raises(ValueError, match="unknown bot.*ghost"):
        BotRegistry.from_config(
            {
                "feishu": {"app_id": "cli_default", "app_secret": "default-secret"},
                "bindings": {"chats": {"oc_bad": "ghost"}},
            }
        )


def test_safe_diagnostics_redact_secrets():
    registry = BotRegistry.from_config(
        {
            "feishu": {"app_id": "cli_default", "app_secret": "super-secret"},
            "bots": {
                "items": {
                    "sales": {"app_id": "cli_sales", "app_secret": "sales-secret"},
                }
            },
            "bindings": {"chats": {"oc_sales": "sales"}},
        }
    )

    diagnostics = registry.safe_diagnostics()
    text = str(diagnostics)

    assert diagnostics["bot_count"] == 2
    assert diagnostics["chat_binding_count"] == 1
    assert "super-secret" not in text
    assert "sales-secret" not in text
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
python3 -m pytest tests/unit/test_bots.py -q
```

Expected: fail with `ModuleNotFoundError` or missing `BotRegistry`.

- [ ] **Step 3: Implement `hermes_feishu_card/bots.py`**

Create `hermes_feishu_card/bots.py`:

```python
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Callable

from .feishu_client import FeishuClient, FeishuClientConfig

BOT_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")


@dataclass(frozen=True)
class BotConfig:
    bot_id: str
    name: str
    app_id: str
    app_secret: str
    base_url: str = "https://open.feishu.cn/open-apis"
    timeout_seconds: int | float = 30


@dataclass(frozen=True)
class RoutingContext:
    chat_id: str
    chat_type: str = ""
    tenant_key: str = ""
    agent_id: str = ""
    profile_id: str = ""


@dataclass(frozen=True)
class RouteResult:
    bot_id: str
    reason: str


class BotRegistry:
    def __init__(
        self,
        *,
        bots: dict[str, BotConfig],
        default_bot_id: str,
        chat_bindings: dict[str, str] | None = None,
    ):
        if not bots:
            raise ValueError("at least one bot is required")
        if default_bot_id not in bots:
            raise ValueError(f"default bot {default_bot_id!r} is not defined")
        self._bots = dict(bots)
        self.default_bot_id = default_bot_id
        self.chat_bindings = dict(chat_bindings or {})
        for chat_id, bot_id in self.chat_bindings.items():
            if bot_id not in self._bots:
                raise ValueError(f"chat binding {chat_id!r} references unknown bot {bot_id!r}")

    @classmethod
    def from_config(cls, config: dict[str, Any]) -> "BotRegistry":
        feishu = config.get("feishu")
        bots_section = config.get("bots") if isinstance(config.get("bots"), dict) else {}
        bindings = config.get("bindings") if isinstance(config.get("bindings"), dict) else {}
        items = bots_section.get("items") if isinstance(bots_section.get("items"), dict) else {}
        default_bot_id = str(
            bots_section.get("default") or bindings.get("fallback_bot") or "default"
        )

        bots: dict[str, BotConfig] = {}
        if isinstance(feishu, dict) and (feishu.get("app_id") or feishu.get("app_secret")):
            bots["default"] = _bot_from_mapping("default", "Default", feishu)

        for raw_bot_id, value in items.items():
            bot_id = _normalize_bot_id(raw_bot_id)
            if bot_id in bots:
                raise ValueError(f"duplicate bot id: {bot_id}")
            if not isinstance(value, dict):
                raise ValueError(f"bot {bot_id} must be a mapping")
            bots[bot_id] = _bot_from_mapping(bot_id, str(value.get("name") or bot_id), value)

        chat_bindings = bindings.get("chats") if isinstance(bindings.get("chats"), dict) else {}
        return cls(
            bots=bots,
            default_bot_id=_normalize_bot_id(default_bot_id),
            chat_bindings={str(chat_id): _normalize_bot_id(bot_id) for chat_id, bot_id in chat_bindings.items()},
        )

    def get(self, bot_id: str) -> BotConfig:
        normalized = _normalize_bot_id(bot_id)
        try:
            return self._bots[normalized]
        except KeyError as exc:
            raise KeyError(f"unknown bot: {normalized}") from exc

    def list_bots(self) -> list[BotConfig]:
        return [self._bots[bot_id] for bot_id in sorted(self._bots)]

    def resolve(self, context: RoutingContext) -> RouteResult:
        if context.chat_id in self.chat_bindings:
            return RouteResult(self.chat_bindings[context.chat_id], "bindings.chats")
        return RouteResult(self.default_bot_id, "bindings.fallback_bot")

    def safe_diagnostics(self) -> dict[str, Any]:
        return {
            "default_bot": self.default_bot_id,
            "bot_count": len(self._bots),
            "chat_binding_count": len(self.chat_bindings),
            "bots": [
                {"bot_id": bot.bot_id, "name": bot.name, "app_id": bot.app_id}
                for bot in self.list_bots()
            ],
        }


class FeishuClientFactory:
    def __init__(
        self,
        registry: BotRegistry,
        client_builder: Callable[[FeishuClientConfig], Any] | None = None,
    ):
        self.registry = registry
        self._client_builder = client_builder or FeishuClient
        self._clients: dict[str, Any] = {}

    def get_client(self, bot_id: str) -> Any:
        normalized = _normalize_bot_id(bot_id)
        if normalized not in self._clients:
            bot = self.registry.get(normalized)
            self._clients[normalized] = self._client_builder(
                FeishuClientConfig(
                    app_id=bot.app_id,
                    app_secret=bot.app_secret,
                    base_url=bot.base_url,
                    timeout_seconds=bot.timeout_seconds,
                )
            )
        return self._clients[normalized]


def _bot_from_mapping(bot_id: str, name: str, value: dict[str, Any]) -> BotConfig:
    normalized = _normalize_bot_id(bot_id)
    app_id = str(value.get("app_id") or "").strip()
    app_secret = str(value.get("app_secret") or "").strip()
    if not app_id:
        raise ValueError(f"bot {normalized} app_id is required")
    if not app_secret:
        raise ValueError(f"bot {normalized} app_secret is required")
    return BotConfig(
        bot_id=normalized,
        name=name,
        app_id=app_id,
        app_secret=app_secret,
        base_url=str(value.get("base_url") or "https://open.feishu.cn/open-apis"),
        timeout_seconds=value.get("timeout_seconds", 30),
    )


def _normalize_bot_id(value: object) -> str:
    bot_id = str(value).strip()
    if not BOT_ID_PATTERN.fullmatch(bot_id):
        raise ValueError(f"invalid bot id: {bot_id!r}")
    return bot_id
```

- [ ] **Step 4: Extend config defaults**

Modify `hermes_feishu_card/config.py` so `DEFAULT_CONFIG` includes empty `bots` and `bindings` sections:

```python
DEFAULT_CONFIG: dict[str, dict[str, Any]] = {
    "server": {"host": "127.0.0.1", "port": 8765},
    "feishu": {"app_id": "", "app_secret": ""},
    "bots": {"default": "default", "items": {}},
    "bindings": {"fallback_bot": "default", "chats": {}, "group_rules": {"enabled": False}},
    "card": {
        "max_wait_ms": 800,
        "max_chars": 240,
        "title": "Hermes Agent",
        "footer_fields": [
            "duration",
            "model",
            "input_tokens",
            "output_tokens",
            "context",
        ],
    },
}
```

Add config tests in `tests/unit/test_config.py`:

```python
def test_load_config_defaults_include_multi_bot_sections(tmp_path):
    config = load_config(tmp_path / "missing.yaml")

    assert config["bots"] == {"default": "default", "items": {}}
    assert config["bindings"] == {
        "fallback_bot": "default",
        "chats": {},
        "group_rules": {"enabled": False},
    }


def test_load_config_accepts_multi_bot_sections(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text(
        """
feishu:
  app_id: cli_default
  app_secret: default-secret
bots:
  default: default
  items:
    sales:
      app_id: cli_sales
      app_secret: sales-secret
bindings:
  fallback_bot: default
  chats:
    oc_sales: sales
""",
        encoding="utf-8",
    )

    config = load_config(path)

    assert config["bots"]["items"]["sales"]["app_id"] == "cli_sales"
    assert config["bindings"]["chats"] == {"oc_sales": "sales"}
```

- [ ] **Step 5: Run focused tests**

Run:

```bash
python3 -m pytest tests/unit/test_bots.py tests/unit/test_config.py -q
```

Expected: pass.

- [ ] **Step 6: Commit**

```bash
git add hermes_feishu_card/bots.py hermes_feishu_card/config.py tests/unit/test_bots.py tests/unit/test_config.py
git commit -m "feat: add multi-bot registry"
```

## Task 2: Server Routing And Health Diagnostics

**Files:**
- Modify: `hermes_feishu_card/server.py`
- Test: `tests/integration/test_server.py`

- [ ] **Step 1: Write failing server routing tests**

Add to `tests/integration/test_server.py`:

```python
class FakeFeishuClientFactory:
    def __init__(self):
        self.clients = {
            "default": FakeFeishuClient(),
            "sales": FakeFeishuClient(),
        }

    def get_client(self, bot_id):
        return self.clients[bot_id]


def routed_event(event, sequence, data=None, *, chat_id, message_id):
    return event_payload(event, sequence, data, chat_id=chat_id, message_id=message_id)


async def test_started_routes_card_to_bound_bot():
    factory = FakeFeishuClientFactory()
    app = create_app(
        factory,
        bot_router=lambda event: ("sales", "bindings.chats"),
    )
    server = TestServer(app)
    test_client = TestClient(server)
    await test_client.start_server()
    try:
        response = await test_client.post(
            "/events",
            json=routed_event("message.started", 0, chat_id="oc_sales", message_id="msg-sales"),
        )
        health = await test_client.get("/health")
    finally:
        await test_client.close()

    assert response.status == 200
    assert factory.clients["sales"].sent[0][0] == "oc_sales"
    assert factory.clients["default"].sent == []
    routing = (await health.json())["routing"]
    assert routing["last_route"]["bot_id"] == "sales"


async def test_updates_reuse_original_bot_for_message():
    factory = FakeFeishuClientFactory()
    routes = iter([("sales", "bindings.chats"), ("default", "bindings.fallback_bot")])

    app = create_app(factory, bot_router=lambda event: next(routes))
    server = TestServer(app)
    test_client = TestClient(server)
    await test_client.start_server()
    try:
        await test_client.post(
            "/events",
            json=routed_event("message.started", 0, chat_id="oc_sales", message_id="msg-sales"),
        )
        await test_client.post(
            "/events",
            json=routed_event(
                "message.completed",
                1,
                {"answer": "完成"},
                chat_id="oc_sales",
                message_id="msg-sales",
            ),
        )
    finally:
        await test_client.close()

    assert len(factory.clients["sales"].sent) == 1
    assert len(factory.clients["sales"].updated) >= 1
    assert factory.clients["default"].sent == []
    assert factory.clients["default"].updated == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
python3 -m pytest tests/integration/test_server.py::test_started_routes_card_to_bound_bot tests/integration/test_server.py::test_updates_reuse_original_bot_for_message -q
```

Expected: fail because `create_app()` has no `bot_router` and treats the first argument as a single client.

- [ ] **Step 3: Extend server app state**

Modify `hermes_feishu_card/server.py`:

```python
BOT_IDS_KEY = web.AppKey("bot_ids", dict)
BOT_ROUTER_KEY = web.AppKey("bot_router", Any)
ROUTING_DIAGNOSTICS_KEY = web.AppKey("routing_diagnostics", dict)
```

Update `create_app()` signature:

```python
def create_app(
    feishu_client: Any,
    process_token: str = "",
    card_config: dict[str, Any] | None = None,
    bot_router: Any | None = None,
) -> web.Application:
```

Inside `create_app()` initialize:

```python
app[BOT_IDS_KEY] = {}
app[BOT_ROUTER_KEY] = bot_router
app[ROUTING_DIAGNOSTICS_KEY] = {
    "default_bot": "default",
    "bot_count": 1,
    "chat_binding_count": 0,
    "last_route": {},
    "last_route_error": "",
}
```

- [ ] **Step 4: Add helper functions**

Add to `hermes_feishu_card/server.py`:

```python
def _resolve_bot(request: web.Request, event: SidecarEvent) -> tuple[str, str]:
    router = request.app[BOT_ROUTER_KEY]
    if router is None:
        return "default", "legacy"
    result = router(event)
    if isinstance(result, tuple):
        return str(result[0]), str(result[1])
    return str(result.bot_id), str(result.reason)


def _client_for_bot(request: web.Request, bot_id: str) -> Any:
    client_or_factory = request.app[FEISHU_CLIENT_KEY]
    get_client = getattr(client_or_factory, "get_client", None)
    if callable(get_client):
        return get_client(bot_id)
    return client_or_factory


def _record_route(request: web.Request, event: SidecarEvent, bot_id: str, reason: str) -> None:
    request.app[ROUTING_DIAGNOSTICS_KEY]["last_route"] = {
        "chat_id": event.chat_id,
        "message_id": event.message_id,
        "bot_id": bot_id,
        "reason": reason,
    }
    request.app[ROUTING_DIAGNOSTICS_KEY]["last_route_error"] = ""
```

Change `_send_card()` and `_update_card_for_app()` so they receive `bot_id` and call `_client_for_bot()` before `send_card()` / `update_card_message()`.

- [ ] **Step 5: Save bot id per message**

In `_apply_event_locked()` for `message.started`:

```python
bot_ids: Dict[str, str] = request.app[BOT_IDS_KEY]
bot_id, route_reason = _resolve_bot(request, event)
_record_route(request, event, bot_id, route_reason)
message_id = await _send_card(request, bot_id, event.chat_id, _render_session_card(request, session))
bot_ids[event.message_id] = bot_id
```

For update events:

```python
bot_id = request.app[BOT_IDS_KEY].get(event.message_id, "default")
updated = await _update_card(request, bot_id, feishu_message_id, _render_session_card(request, session))
```

- [ ] **Step 6: Include routing in health**

In `_health()` include:

```python
"routing": request.app[ROUTING_DIAGNOSTICS_KEY],
```

When the passed client/factory has `registry.safe_diagnostics()`, merge those values into the routing diagnostics at app creation.

- [ ] **Step 7: Run focused and full server tests**

Run:

```bash
python3 -m pytest tests/integration/test_server.py -q
```

Expected: pass.

- [ ] **Step 8: Commit**

```bash
git add hermes_feishu_card/server.py tests/integration/test_server.py
git commit -m "feat: route cards by bot"
```

## Task 3: Runner Integration

**Files:**
- Modify: `hermes_feishu_card/runner.py`
- Test: `tests/unit/test_runner.py`

- [ ] **Step 1: Write failing runner tests**

Add to `tests/unit/test_runner.py`:

```python
from hermes_feishu_card.bots import FeishuClientFactory
from hermes_feishu_card.runner import build_feishu_boundary


def test_build_feishu_boundary_returns_factory_for_named_bots():
    config = {
        "feishu": {"app_id": "cli_default", "app_secret": "default-secret"},
        "bots": {
            "default": "default",
            "items": {"sales": {"app_id": "cli_sales", "app_secret": "sales-secret"}},
        },
        "bindings": {"chats": {"oc_sales": "sales"}},
    }

    boundary = build_feishu_boundary(config)

    assert isinstance(boundary.client, FeishuClientFactory)
    result = boundary.router(type("Event", (), {"chat_id": "oc_sales", "data": {}})())
    assert result.bot_id == "sales"
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
python3 -m pytest tests/unit/test_runner.py::test_build_feishu_boundary_returns_factory_for_named_bots -q
```

Expected: fail because `build_feishu_boundary` does not exist.

- [ ] **Step 3: Implement runner boundary helper**

In `hermes_feishu_card/runner.py`, add:

```python
from dataclasses import dataclass

from .bots import BotRegistry, FeishuClientFactory, RoutingContext


@dataclass(frozen=True)
class FeishuBoundary:
    client: object
    router: object | None


def build_feishu_boundary(config: dict[str, object]) -> FeishuBoundary:
    registry = BotRegistry.from_config(config)
    factory = FeishuClientFactory(registry)

    def route_event(event):
        data = getattr(event, "data", {})
        data = data if isinstance(data, dict) else {}
        return registry.resolve(
            RoutingContext(
                chat_id=getattr(event, "chat_id", ""),
                chat_type=str(data.get("chat_type") or ""),
                tenant_key=str(data.get("tenant_key") or ""),
                agent_id=str(data.get("agent_id") or ""),
                profile_id=str(data.get("profile_id") or ""),
            )
        )

    return FeishuBoundary(client=factory, router=route_event)
```

Update runner app creation to pass:

```python
boundary = build_feishu_boundary(config)
app = create_app(
    boundary.client,
    process_token=...,
    card_config=config.get("card"),
    bot_router=boundary.router,
)
```

Keep no-op/fake client behavior for missing credentials in advanced `start` paths by creating a boundary only when credentials exist; otherwise pass the no-op client with `bot_router=None`.

- [ ] **Step 4: Run runner tests**

Run:

```bash
python3 -m pytest tests/unit/test_runner.py -q
```

Expected: pass.

- [ ] **Step 5: Commit**

```bash
git add hermes_feishu_card/runner.py tests/unit/test_runner.py
git commit -m "feat: wire bot registry into runner"
```

## Task 4: Bot CLI Commands

**Files:**
- Modify: `hermes_feishu_card/cli.py`
- Test: `tests/integration/test_cli.py`

- [ ] **Step 1: Write failing CLI tests**

Add to `tests/integration/test_cli.py`:

```python
def test_bots_list_prints_named_bots(tmp_path, capsys):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        """
feishu:
  app_id: cli_default
  app_secret: default-secret
bots:
  items:
    sales:
      app_id: cli_sales
      app_secret: sales-secret
""",
        encoding="utf-8",
    )

    exit_code = main(["bots", "list", "--config", str(config_path)])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "default" in captured.out
    assert "sales" in captured.out
    assert "sales-secret" not in captured.out


def test_bots_bind_chat_updates_config(tmp_path, capsys):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        """
feishu:
  app_id: cli_default
  app_secret: default-secret
bots:
  items:
    sales:
      app_id: cli_sales
      app_secret: sales-secret
""",
        encoding="utf-8",
    )

    exit_code = main(["bots", "bind-chat", "oc_sales", "sales", "--config", str(config_path)])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "bound" in captured.out.lower()
    assert "oc_sales: sales" in config_path.read_text(encoding="utf-8")


def test_bots_unbind_chat_updates_config(tmp_path, capsys):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        """
feishu:
  app_id: cli_default
  app_secret: default-secret
bots:
  items:
    sales:
      app_id: cli_sales
      app_secret: sales-secret
bindings:
  chats:
    oc_sales: sales
""",
        encoding="utf-8",
    )

    exit_code = main(["bots", "unbind-chat", "oc_sales", "--config", str(config_path)])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "unbound" in captured.out.lower()
    assert "oc_sales" not in config_path.read_text(encoding="utf-8")
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
python3 -m pytest tests/integration/test_cli.py::test_bots_list_prints_named_bots tests/integration/test_cli.py::test_bots_bind_chat_updates_config tests/integration/test_cli.py::test_bots_unbind_chat_updates_config -q
```

Expected: fail because `bots` subcommand does not exist.

- [ ] **Step 3: Add parser commands**

In `_build_parser()` add:

```python
bots = subparsers.add_parser("bots")
bots_subparsers = bots.add_subparsers(dest="bots_command")
for subcommand in ("list", "add", "bind-chat", "unbind-chat", "test"):
    bot_parser = bots_subparsers.add_parser(subcommand)
    bot_parser.add_argument("--config", default=str(Path.home() / ".hermes_feishu_card" / "config.yaml"))
bots_subparsers.choices["add"].add_argument("bot_id")
bots_subparsers.choices["bind-chat"].add_argument("chat_id")
bots_subparsers.choices["bind-chat"].add_argument("bot_id")
bots_subparsers.choices["unbind-chat"].add_argument("chat_id")
bots_subparsers.choices["test"].add_argument("bot_id")
bots_subparsers.choices["test"].add_argument("--chat-id", required=True)
```

If `argparse` choices mutation is awkward, create each parser explicitly. Keep command behavior simple and testable.

- [ ] **Step 4: Add config read/write helpers**

In `hermes_feishu_card/cli.py` add:

```python
def _read_local_yaml(path: Path) -> dict[str, object]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as file:
        loaded = yaml.safe_load(file) or {}
    if not isinstance(loaded, dict):
        raise ValueError("config top-level YAML value must be a mapping")
    return loaded


def _write_local_yaml(path: Path, data: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    _atomic_write_text(path, yaml.safe_dump(data, allow_unicode=True, sort_keys=False))
```

- [ ] **Step 5: Implement `bots list`, `bind-chat`, and `unbind-chat`**

Add `_run_bots(args)` and dispatch from `main()`:

```python
if args.command == "bots":
    return _run_bots(args)
```

Implementation outline:

```python
def _run_bots(args: argparse.Namespace) -> int:
    config_path = Path(args.config).expanduser()
    try:
        raw = _read_local_yaml(config_path)
        config = load_config(config_path)
        registry = BotRegistry.from_config(config)
        if args.bots_command == "list":
            for bot in registry.list_bots():
                print(f"{bot.bot_id}\t{bot.name}\t{bot.app_id}")
            return 0
        if args.bots_command == "bind-chat":
            registry.get(args.bot_id)
            raw.setdefault("bindings", {}).setdefault("chats", {})[args.chat_id] = args.bot_id
            raw.setdefault("bindings", {}).setdefault("fallback_bot", registry.default_bot_id)
            _write_local_yaml(config_path, raw)
            print(f"bound {args.chat_id} -> {args.bot_id}")
            return 0
        if args.bots_command == "unbind-chat":
            raw.setdefault("bindings", {}).setdefault("chats", {}).pop(args.chat_id, None)
            _write_local_yaml(config_path, raw)
            print(f"unbound {args.chat_id}")
            return 0
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print("error: missing bots subcommand", file=sys.stderr)
    return 2
```

Add `bots add` minimally:

```python
raw.setdefault("bots", {}).setdefault("items", {})[args.bot_id] = {
    "name": args.bot_id,
    "app_id": "",
    "app_secret": "",
    "base_url": "https://open.feishu.cn/open-apis",
    "timeout_seconds": 30,
}
```

Add `bots test` by reusing the smoke flow with a selected bot client and the selected chat id.

- [ ] **Step 6: Run CLI tests**

Run:

```bash
python3 -m pytest tests/integration/test_cli.py -q
```

Expected: pass.

- [ ] **Step 7: Commit**

```bash
git add hermes_feishu_card/cli.py tests/integration/test_cli.py
git commit -m "feat: add bot management cli"
```

## Task 5: Group Context And Event Compatibility

**Files:**
- Modify: `hermes_feishu_card/events.py`
- Modify: `hermes_feishu_card/hook_runtime.py`
- Test: `tests/unit/test_events.py`
- Test: `tests/unit/test_hook_runtime.py`

- [ ] **Step 1: Write optional context tests**

Add to `tests/unit/test_events.py`:

```python
def test_event_accepts_optional_group_routing_context():
    payload = valid_payload()
    payload["data"] = {
        "chat_type": "group",
        "tenant_key": "tenant_a",
        "agent_id": "reserved-agent",
        "profile_id": "reserved-profile",
    }

    event = SidecarEvent.from_dict(payload)

    assert event.data["chat_type"] == "group"
    assert event.data["tenant_key"] == "tenant_a"
```

Add to `tests/unit/test_hook_runtime.py` a test that when local vars include `chat_type`, `tenant_key`, `agent_id`, or `profile_id`, `build_event()` includes them inside `data`.

- [ ] **Step 2: Run tests**

Run:

```bash
python3 -m pytest tests/unit/test_events.py tests/unit/test_hook_runtime.py -q
```

Expected: event test likely already passes because `data` accepts arbitrary mappings; hook test fails until extraction is added.

- [ ] **Step 3: Add optional extraction in hook runtime**

In `_event_data()` in `hermes_feishu_card/hook_runtime.py`, append optional strings when present:

```python
for source_key, data_key in (
    ("chat_type", "chat_type"),
    ("tenant_key", "tenant_key"),
    ("agent_id", "agent_id"),
    ("profile_id", "profile_id"),
):
    value = _first_string(local_vars, (source_key,)) or _first_attr_string(message_obj, (source_key,))
    if value:
        data[data_key] = value
```

Do not reject events when these fields are absent.

- [ ] **Step 4: Run hook/event tests**

Run:

```bash
python3 -m pytest tests/unit/test_events.py tests/unit/test_hook_runtime.py tests/integration/test_hook_runtime_integration.py -q
```

Expected: pass.

- [ ] **Step 5: Commit**

```bash
git add hermes_feishu_card/events.py hermes_feishu_card/hook_runtime.py tests/unit/test_events.py tests/unit/test_hook_runtime.py
git commit -m "feat: preserve optional routing context"
```

## Task 6: Docs, Examples, And Version Bump

**Files:**
- Modify: `pyproject.toml`
- Modify: `hermes_feishu_card/__init__.py`
- Modify: `config.yaml.example`
- Modify: `README.md`
- Modify: `README.en.md`
- Modify: `docs/testing.md`
- Modify: `docs/testing.en.md`
- Modify: `docs/e2e-verification.md`
- Modify: `docs/e2e-verification.en.md`
- Test: `tests/unit/test_docs.py`
- Test: `tests/unit/test_package_metadata.py`

- [ ] **Step 1: Write doc/package guards**

Update `tests/unit/test_docs.py` to assert:

```python
assert "V3.2.0" in readme
assert "多 bot" in readme
assert "群聊" in readme
assert "bindings.chats" in readme
assert "group_rules" in readme
assert "Multi-bot" in english_readme
assert "group chat" in english_readme
```

Update `tests/unit/test_package_metadata.py` expected version to `3.2.0`.

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
python3 -m pytest tests/unit/test_docs.py tests/unit/test_package_metadata.py -q
```

Expected: fail on version/doc assertions.

- [ ] **Step 3: Update version**

Set version to `3.2.0` in:

```toml
# pyproject.toml
version = "3.2.0"
```

```python
# hermes_feishu_card/__init__.py
__version__ = "3.2.0"
```

- [ ] **Step 4: Update example config**

Extend `config.yaml.example`:

```yaml
# Optional V3.2 multi-bot config. Existing single-bot users can leave this empty.
bots:
  default: default
  items: {}

bindings:
  fallback_bot: default
  chats: {}
  # Reserved for a future release. V3.2 does not filter group triggers.
  group_rules:
    enabled: false
```

- [ ] **Step 5: Update README docs**

Add a V3.2 section to Chinese and English README:

```markdown
## V3.2 多 bot 与群聊

V3.2 支持一个 sidecar 管理多个飞书机器人，并按 `chat_id/open_chat_id` 把群聊或私聊绑定到指定 bot。未绑定会话使用 fallback/default bot。插件不接管群聊触发规则；Hermes 仍负责决定何时响应，插件只负责把 Hermes 已经产生的回复渲染到对应飞书会话。
```

Add troubleshooting:

- Wrong bot replied: check `bindings.chats`.
- Group card not sent: check bot is in group, permissions, Hermes trigger, and `/health.routing`.
- Unknown bot binding: run `doctor` or `bots list`.

- [ ] **Step 6: Run doc tests**

Run:

```bash
python3 -m pytest tests/unit/test_docs.py tests/unit/test_package_metadata.py -q
```

Expected: pass.

- [ ] **Step 7: Commit**

```bash
git add pyproject.toml hermes_feishu_card/__init__.py config.yaml.example README.md README.en.md docs/testing.md docs/testing.en.md docs/e2e-verification.md docs/e2e-verification.en.md tests/unit/test_docs.py tests/unit/test_package_metadata.py
git commit -m "docs: document V3.2 multi-bot group support"
```

## Task 7: Final Regression And Release Readiness

**Files:**
- Modify only if verification reveals issues.

- [ ] **Step 1: Run focused suite**

Run:

```bash
python3 -m pytest tests/unit/test_bots.py tests/unit/test_config.py tests/integration/test_server.py tests/integration/test_cli.py tests/unit/test_runner.py -q
```

Expected: pass.

- [ ] **Step 2: Run full regression**

Run:

```bash
python3 -m pytest -q -p no:cacheprovider
```

Expected: all tests pass.

- [ ] **Step 3: Check diff hygiene**

Run:

```bash
git diff --check
git status --short --branch
```

Expected: no whitespace errors; branch only contains intentional commits.

- [ ] **Step 4: Manual local smoke without credentials**

Run:

```bash
python3 -m hermes_feishu_card.cli doctor --config config.yaml.example --skip-hermes
python3 -m hermes_feishu_card.cli bots list --config config.yaml.example
```

Expected: doctor succeeds; bot list prints the default bot or a clear no-credential diagnostic without leaking secrets.

- [ ] **Step 5: Commit any verification doc count updates**

If full regression changes the documented test count, update README/testing docs and commit:

```bash
git add README.md README.en.md docs/testing.md docs/testing.en.md docs/e2e-verification.md docs/e2e-verification.en.md tests/unit/test_docs.py
git commit -m "docs: update V3.2 verification status"
```

## Implementation Notes

- Keep old single-bot config working. This is the most important compatibility requirement.
- Do not store app secrets in health output, logs, tests, or docs.
- Do not make group trigger decisions in this plugin for V3.2.
- Do not re-route active messages after the first card is sent.
- Keep `show_reasoning` guidance unchanged from PR #9; V3.2 does not change Hermes streaming requirements.
- Prefer small commits by task. If a task becomes too large, split it before coding further.

## Self-Review Checklist

- Spec coverage: chat-based multi-bot routing, group support, legacy compatibility, CLI management, health diagnostics, docs, tests.
- No required behavior depends on future Agent/Profile routing.
- No task requires real Feishu credentials in CI.
- No command writes outside the repo except normal local user config paths selected by tests in temporary directories.
- Existing `setup`, `doctor`, `start`, `status`, and `smoke-feishu-card` behavior remains covered by existing tests.

