from __future__ import annotations

from types import SimpleNamespace

from hermes_feishu_card.native_commands import (
    build_command_center_card,
    build_native_result_card,
    collect_hermes_command_catalog,
)


def _entry(
    name: str,
    category: str = "Session",
    *,
    description: str = "description",
    args_hint: str = "",
    aliases: tuple[str, ...] = (),
    subcommands: tuple[str, ...] = (),
    busy_policy: str = "reject",
    argument_mode: str | None = None,
    source: str = "core",
) -> dict[str, object]:
    return {
        "name": name,
        "category": category,
        "description": description,
        "args_hint": args_hint,
        "aliases": aliases,
        "subcommands": subcommands,
        "busy_policy": busy_policy,
        "argument_mode": argument_mode,
        "source": source,
    }


def test_catalog_reads_latest_hermes_registry_without_a_fixed_allowlist(monkeypatch):
    registry = [
        SimpleNamespace(
            name="bg",
            category="Session",
            description="Run a separate background session",
            args_hint="<prompt>",
            aliases=(),
            subcommands=(),
            busy_policy="dispatch",
            argument_mode="text",
            cli_only=False,
            gateway_config_gate=None,
        ),
        SimpleNamespace(
            name="btw",
            category="Session",
            description="Ask a side question",
            args_hint="<question>",
            aliases=(),
            subcommands=(),
            busy_policy="dispatch",
            argument_mode="text",
            cli_only=False,
            gateway_config_gate=None,
        ),
        SimpleNamespace(
            name="plan",
            category="Session",
            description="Write a markdown plan",
            args_hint="[task]",
            aliases=(),
            subcommands=(),
            busy_policy="reject",
            argument_mode=None,
            cli_only=False,
            gateway_config_gate=None,
        ),
        SimpleNamespace(
            name="terminal-only",
            category="Info",
            description="CLI only",
            args_hint="",
            aliases=(),
            subcommands=(),
            busy_policy="reject",
            argument_mode=None,
            cli_only=True,
            gateway_config_gate=None,
        ),
    ]
    commands = SimpleNamespace(
        COMMAND_REGISTRY=registry,
        _resolve_config_gates=lambda: set(),
        _is_gateway_available=lambda command, _gates: not command.cli_only,
        infer_argument_mode=lambda command: command.argument_mode
        or ("text" if command.args_hint else None),
    )

    monkeypatch.setattr(
        "hermes_feishu_card.native_commands._load_hermes_commands",
        lambda: commands,
    )
    monkeypatch.setattr(
        "hermes_feishu_card.native_commands._plugin_command_entries",
        lambda: [],
    )
    monkeypatch.setattr(
        "hermes_feishu_card.native_commands._skill_command_entries",
        lambda: [],
    )

    catalog = collect_hermes_command_catalog()

    assert [item["name"] for item in catalog] == ["bg", "btw", "plan"]
    assert catalog[0]["busy_policy"] == "dispatch"
    assert catalog[0]["argument_mode"] == "text"
    assert catalog[2]["args_hint"] == "[task]"


def test_command_center_card_supports_category_detail_and_safe_quick_actions():
    entries = [
        _entry("status", description="Show status", busy_policy="dispatch"),
        _entry("context", description="Show context", busy_policy="dispatch"),
        _entry("model", "Configuration", description="Switch model"),
        _entry("plan", description="Write a plan", args_hint="[task]"),
        _entry("update", "Info", description="Update Hermes"),
    ]

    overview = build_command_center_card(entries, center_id="center-1")
    category = build_command_center_card(
        entries,
        center_id="center-1",
        selected_category="Session",
    )
    detail = build_command_center_card(
        entries,
        center_id="center-1",
        selected_category="Session",
        selected_command="status",
    )

    assert overview["header"]["title"]["content"] == "Hermes 原生能力中心"
    assert "5 个原生命令" in overview["elements"][0]["content"]
    category_select = overview["elements"][1]["actions"][0]
    assert category_select["value"]["hfc_action"] == "command_center"
    assert {option["value"] for option in category_select["options"]} == {
        "Session",
        "Configuration",
        "Info",
    }

    quick_actions = overview["elements"][2]["actions"]
    assert [action["value"]["hfc_command_center_command"] for action in quick_actions] == [
        "status",
        "context",
        "model",
    ]
    assert all(
        action["value"]["hfc_command_center_nav"] == "run"
        for action in quick_actions
    )

    assert "`/status`" in category["elements"][1]["content"]
    command_select = category["elements"][2]["actions"][0]
    assert command_select["value"]["hfc_command_center_nav"] == "detail"
    assert "`/status`" in detail["elements"][0]["content"]
    detail_actions = detail["elements"][1]["actions"]
    assert detail_actions[0]["value"]["hfc_command_center_nav"] == "run"
    assert detail_actions[1]["value"]["hfc_command_center_nav"] == "category"


def test_native_result_card_adds_kpi_columns_and_keeps_exact_full_text():
    content = (
        "Model: openai/gpt-5.6\n"
        "Context: 64%\n"
        "Tokens: 12,345\n"
        "Session: active\n\n"
        "Detailed diagnostic line that must remain visible."
    )

    card = build_native_result_card("status", content)

    assert card["header"]["title"]["content"] == "Hermes 运行状态"
    assert card["header"]["template"] == "blue"
    columns = card["elements"][0]["columns"]
    assert [column["elements"][0]["content"] for column in columns] == [
        "**Model**\nopenai/gpt-5.6",
        "**Context**\n64%",
        "**Tokens**\n12,345",
        "**Session**\nactive",
    ]
    markdown = "".join(
        element["content"]
        for element in card["elements"]
        if element.get("tag") == "markdown"
    )
    assert markdown == content


def test_native_result_card_falls_back_to_full_markdown_without_metrics():
    content = "Hermes Agent v0.20.6 (v2026.8.27)"

    card = build_native_result_card("version", content)

    assert card["header"]["title"]["content"] == "Hermes 版本"
    assert card["elements"] == [{"tag": "markdown", "content": content}]
