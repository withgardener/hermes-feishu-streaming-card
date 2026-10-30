from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any

from .render import MAIN_CONTENT_CHUNK_CHARS
from .text import split_markdown_blocks


SAFE_QUICK_COMMANDS: tuple[str, ...] = (
    "status",
    "context",
    "usage",
    "agents",
    "sessions",
    "model",
    "resume",
    "reasoning",
    "profile",
    "version",
)

_CATEGORY_LABELS = {
    "Session": "会话与任务",
    "Configuration": "模型与配置",
    "Tools & Skills": "工具与技能",
    "Info": "状态与信息",
    "Plugins": "插件命令",
    "Skills": "技能命令",
    "Exit": "退出",
}

_RESULT_TITLES = {
    "status": "Hermes 运行状态",
    "context": "上下文视图",
    "usage": "用量与限额",
    "agents": "活跃 Agents",
    "sessions": "历史会话",
    "profile": "当前 Profile",
    "version": "Hermes 版本",
    "reasoning": "推理配置",
    "fast": "推理速度",
    "busy": "忙碌时交互",
    "skills": "Hermes Skills",
    "memory": "Hermes Memory",
    "bundles": "Skill Bundles",
}

NATIVE_RESULT_COMMANDS = frozenset(_RESULT_TITLES)

_VISUAL_RESULT_COMMANDS = frozenset(
    {
        "status",
        "context",
        "usage",
        "agents",
        "sessions",
        "profile",
        "reasoning",
        "fast",
        "busy",
    }
)

_METRIC_LINE_RE = re.compile(
    r"^\s*(?:[-*]\s*)?(?:\*\*)?([^:：\n]{1,24}?)(?:\*\*)?\s*[:：]\s*(.+?)\s*$"
)


def _load_hermes_commands() -> Any:
    from hermes_cli import commands

    return commands


def _plugin_command_entries() -> list[dict[str, Any]]:
    try:
        from hermes_cli.plugins import get_plugin_commands

        commands = get_plugin_commands() or {}
    except Exception:
        return []
    result: list[dict[str, Any]] = []
    if not isinstance(commands, Mapping):
        return result
    for name in sorted(commands):
        metadata = commands.get(name)
        if not isinstance(name, str) or not isinstance(metadata, Mapping):
            continue
        normalized = name.strip().lstrip("/")
        if not normalized:
            continue
        result.append(
            {
                "name": normalized,
                "category": "Plugins",
                "description": str(metadata.get("description") or f"Run /{normalized}"),
                "args_hint": str(metadata.get("args_hint") or "").strip(),
                "aliases": (),
                "subcommands": (),
                "busy_policy": "reject",
                "argument_mode": None,
                "source": "plugin",
            }
        )
    return result


def _skill_command_entries() -> list[dict[str, Any]]:
    try:
        from agent.skill_commands import get_skill_commands

        commands = get_skill_commands() or {}
    except Exception:
        return []
    result: list[dict[str, Any]] = []
    if not isinstance(commands, Mapping):
        return result
    for raw_name in sorted(commands):
        metadata = commands.get(raw_name)
        if not isinstance(raw_name, str) or not isinstance(metadata, Mapping):
            continue
        name = raw_name.strip().lstrip("/")
        if not name:
            continue
        result.append(
            {
                "name": name,
                "category": "Skills",
                "description": str(metadata.get("description") or f"Run /{name}"),
                "args_hint": "",
                "aliases": (),
                "subcommands": (),
                "busy_policy": "reject",
                "argument_mode": None,
                "source": "skill",
            }
        )
    return result


def collect_hermes_command_catalog() -> list[dict[str, Any]]:
    """Read the live Hermes registry without importing gateway internals.

    Hermes 0.20+ owns command availability and metadata in
    ``hermes_cli.commands.COMMAND_REGISTRY``. Older or partially upgraded
    installs fail closed to an empty catalog so ordinary text feedback remains
    available.
    """
    try:
        commands = _load_hermes_commands()
        registry = list(getattr(commands, "COMMAND_REGISTRY", ()) or ())
    except Exception:
        return []

    try:
        config_gates = set(commands._resolve_config_gates())
    except Exception:
        config_gates = set()
    available = getattr(commands, "_is_gateway_available", None)
    infer_argument_mode = getattr(commands, "infer_argument_mode", None)

    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for command in registry:
        name = str(getattr(command, "name", "") or "").strip().lstrip("/")
        if not name or name in seen:
            continue
        try:
            is_available = (
                bool(available(command, config_gates))
                if callable(available)
                else not bool(getattr(command, "cli_only", False))
                or (
                    bool(getattr(command, "gateway_config_gate", None))
                    and name in config_gates
                )
            )
        except Exception:
            is_available = not bool(getattr(command, "cli_only", False))
        if not is_available:
            continue
        try:
            argument_mode = (
                infer_argument_mode(command)
                if callable(infer_argument_mode)
                else getattr(command, "argument_mode", None)
            )
        except Exception:
            argument_mode = getattr(command, "argument_mode", None)
        result.append(
            {
                "name": name,
                "category": str(getattr(command, "category", "Info") or "Info"),
                "description": str(getattr(command, "description", "") or f"Run /{name}"),
                "args_hint": str(getattr(command, "args_hint", "") or "").strip(),
                "aliases": _bounded_strings(getattr(command, "aliases", ()), 12),
                "subcommands": _bounded_strings(
                    getattr(command, "subcommands", ()), 40
                ),
                "busy_policy": str(
                    getattr(command, "busy_policy", "reject") or "reject"
                ),
                "argument_mode": str(argument_mode or "") or None,
                "source": "core",
            }
        )
        seen.add(name)

    for entry in [*_plugin_command_entries(), *_skill_command_entries()]:
        name = str(entry.get("name") or "")
        if name and name not in seen:
            result.append(entry)
            seen.add(name)
    return result


def _bounded_strings(value: Any, limit: int) -> tuple[str, ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return ()
    result: list[str] = []
    for item in value:
        text = str(item or "").strip()
        if text:
            result.append(text)
        if len(result) >= limit:
            break
    return tuple(result)


def command_is_safe_quick_action(entry: Mapping[str, Any]) -> bool:
    name = str(entry.get("name") or "")
    return name in SAFE_QUICK_COMMANDS and str(entry.get("source") or "core") == "core"


def build_command_center_card(
    entries: Sequence[Mapping[str, Any]],
    *,
    center_id: str,
    selected_category: str = "",
    selected_command: str = "",
) -> dict[str, Any]:
    catalog = [dict(entry) for entry in entries if str(entry.get("name") or "").strip()]
    categories = _categories(catalog)
    if selected_category not in categories:
        selected_category = ""
    selected_entry = next(
        (
            entry
            for entry in catalog
            if entry.get("name") == selected_command
            and (not selected_category or entry.get("category") == selected_category)
        ),
        None,
    )
    if selected_entry is None:
        selected_command = ""

    if selected_entry is not None:
        elements = _command_detail_elements(
            selected_entry,
            center_id=center_id,
            category=selected_category,
        )
    elif selected_category:
        elements = _category_elements(
            catalog,
            center_id=center_id,
            category=selected_category,
            categories=categories,
        )
    else:
        elements = _overview_elements(
            catalog,
            center_id=center_id,
            categories=categories,
        )

    return {
        "config": {"wide_screen_mode": True, "update_multi": True},
        "header": {
            "title": {"content": "Hermes 原生能力中心", "tag": "plain_text"},
            "template": "blue",
        },
        "elements": elements,
    }


def _categories(entries: Sequence[Mapping[str, Any]]) -> list[str]:
    result: list[str] = []
    for entry in entries:
        category = str(entry.get("category") or "Info")
        if category not in result:
            result.append(category)
    return result


def _category_label(category: str) -> str:
    return _CATEGORY_LABELS.get(category, category)


def _overview_elements(
    entries: list[dict[str, Any]],
    *,
    center_id: str,
    categories: list[str],
) -> list[dict[str, Any]]:
    core_count = sum(entry.get("source") == "core" for entry in entries)
    plugin_count = sum(entry.get("source") == "plugin" for entry in entries)
    skill_count = sum(entry.get("source") == "skill" for entry in entries)
    extras: list[str] = []
    if plugin_count:
        extras.append(f"{plugin_count} 个插件命令")
    if skill_count:
        extras.append(f"{skill_count} 个技能命令")
    suffix = f"，另含{'、'.join(extras)}" if extras else ""
    elements: list[dict[str, Any]] = [
        {
            "tag": "markdown",
            "content": (
                f"已从当前 Hermes 注册表同步 **{core_count} 个原生命令**{suffix}。\n\n"
                "分类、别名、参数和忙碌时策略均来自 Hermes；HFC 只负责卡片展现。"
            ),
        }
    ]
    if categories:
        elements.append(_category_select(center_id, categories, ""))
    quick_entries = [
        entry for name in SAFE_QUICK_COMMANDS for entry in entries
        if entry.get("name") == name and command_is_safe_quick_action(entry)
    ][:5]
    if quick_entries:
        elements.append(
            {
                "tag": "action",
                "actions": [
                    _button(
                        _quick_label(str(entry["name"])),
                        _action_value(
                            center_id,
                            nav="run",
                            command=str(entry["name"]),
                        ),
                        "primary" if index == 0 else "default",
                    )
                    for index, entry in enumerate(quick_entries)
                ],
            }
        )
    return elements


def _category_elements(
    entries: list[dict[str, Any]],
    *,
    center_id: str,
    category: str,
    categories: list[str],
) -> list[dict[str, Any]]:
    visible = [entry for entry in entries if entry.get("category") == category]
    lines = [f"**{_category_label(category)} · {len(visible)} 个命令**", ""]
    for entry in visible[:30]:
        args = f" {entry.get('args_hint')}" if entry.get("args_hint") else ""
        lines.append(
            f"- `/{entry['name']}{args}` — {str(entry.get('description') or '')[:160]}"
        )
    if len(visible) > 30:
        lines.append(f"- …另有 {len(visible) - 30} 个命令，请用 `/help` 检索。")
    elements: list[dict[str, Any]] = [
        _category_select(center_id, categories, category),
        {"tag": "markdown", "content": "\n".join(lines)},
    ]
    if visible:
        elements.append(
            {
                "tag": "action",
                "actions": [
                    _select(
                        "查看命令详情",
                        _action_value(center_id, nav="detail", category=category),
                        [
                            {
                                "label": f"/{entry['name']} · {str(entry.get('description') or '')[:48]}",
                                "value": str(entry["name"]),
                            }
                            for entry in visible[:30]
                        ],
                    )
                ],
            }
        )
    elements.append(
        {
            "tag": "action",
            "actions": [_button("返回首页", _action_value(center_id, nav="home"))],
        }
    )
    return elements


def _command_detail_elements(
    entry: Mapping[str, Any],
    *,
    center_id: str,
    category: str,
) -> list[dict[str, Any]]:
    name = str(entry.get("name") or "")
    args_hint = str(entry.get("args_hint") or "")
    lines = [
        f"**`/{name}{f' {args_hint}' if args_hint else ''}`**",
        "",
        str(entry.get("description") or ""),
        "",
        f"- 分类：{_category_label(category)}",
        f"- 来源：{_source_label(str(entry.get('source') or 'core'))}",
        f"- 忙碌时策略：`{str(entry.get('busy_policy') or 'reject')}`",
    ]
    aliases = tuple(entry.get("aliases") or ())
    subcommands = tuple(entry.get("subcommands") or ())
    argument_mode = str(entry.get("argument_mode") or "")
    if aliases:
        lines.append("- 别名：" + "、".join(f"`/{alias}`" for alias in aliases))
    if subcommands:
        lines.append("- 子命令：" + "、".join(f"`{item}`" for item in subcommands[:16]))
    if argument_mode:
        lines.append(f"- 参数交互：`{argument_mode}`")
    if not command_is_safe_quick_action(entry):
        lines.extend(["", "该命令需要显式输入或可能改变状态，请在消息框中发送完整命令。"])

    actions: list[dict[str, Any]] = []
    if command_is_safe_quick_action(entry):
        actions.append(
            _button(
                f"运行 /{name}",
                _action_value(center_id, nav="run", command=name, category=category),
                "primary",
            )
        )
    actions.append(
        _button(
            "返回分类",
            _action_value(center_id, nav="category", category=category),
        )
    )
    return [
        {"tag": "markdown", "content": "\n".join(lines)},
        {"tag": "action", "actions": actions},
    ]


def _category_select(
    center_id: str,
    categories: Sequence[str],
    selected: str,
) -> dict[str, Any]:
    return {
        "tag": "action",
        "actions": [
            _select(
                "选择能力分类",
                _action_value(center_id, nav="category"),
                [
                    {"label": _category_label(category), "value": category}
                    for category in categories[:20]
                ],
                initial_option=selected,
            )
        ],
    }


def _action_value(
    center_id: str,
    *,
    nav: str,
    command: str = "",
    category: str = "",
) -> dict[str, str]:
    value = {
        "hfc_action": "command_center",
        "hfc_command_center_id": center_id,
        "hfc_command_center_nav": nav,
    }
    if command:
        value["hfc_command_center_command"] = command
    if category:
        value["hfc_command_center_category"] = category
    return value


def _select(
    placeholder: str,
    value: Mapping[str, str],
    options: Sequence[Mapping[str, str]],
    *,
    initial_option: str = "",
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "tag": "select_static",
        "placeholder": {"tag": "plain_text", "content": placeholder},
        "value": dict(value),
        "options": [
            {
                "text": {
                    "tag": "plain_text",
                    "content": str(option.get("label") or "")[:80],
                },
                "value": str(option.get("value") or ""),
            }
            for option in options
            if option.get("label") and option.get("value")
        ],
    }
    if initial_option:
        result["initial_option"] = initial_option
    return result


def _button(
    label: str,
    value: Mapping[str, str],
    button_type: str = "default",
) -> dict[str, Any]:
    return {
        "tag": "button",
        "text": {"tag": "plain_text", "content": label},
        "type": button_type,
        "value": dict(value),
    }


def _quick_label(command: str) -> str:
    return {
        "status": "运行状态",
        "context": "上下文",
        "usage": "用量",
        "agents": "任务",
        "sessions": "会话",
        "model": "模型",
        "resume": "恢复会话",
        "reasoning": "推理",
        "profile": "Profile",
        "version": "版本",
    }.get(command, f"/{command}")


def _source_label(source: str) -> str:
    return {"core": "Hermes Core", "plugin": "Plugin", "skill": "Skill"}.get(
        source, source
    )


def build_native_result_card(command: str, content: str) -> dict[str, Any]:
    normalized_command = str(command or "").strip().lower()
    normalized_content = str(content or "").strip() or "已处理。"
    metrics = (
        _extract_metrics(normalized_content)
        if normalized_command in _VISUAL_RESULT_COMMANDS
        else []
    )
    elements: list[dict[str, Any]] = []
    if metrics:
        elements.append(
            {
                "tag": "column_set",
                "flex_mode": "none",
                "horizontal_spacing": "8px",
                "columns": [
                    {
                        "tag": "column",
                        "width": "weighted",
                        "weight": 1,
                        "vertical_align": "top",
                        "elements": [
                            {
                                "tag": "markdown",
                                "content": f"**{label}**\n{value}",
                            }
                        ],
                    }
                    for label, value in metrics
                ],
            }
        )
    elements.extend(
        {"tag": "markdown", "content": chunk}
        for chunk in split_markdown_blocks(
            normalized_content,
            MAIN_CONTENT_CHUNK_CHARS,
        )
    )
    return {
        "config": {"wide_screen_mode": True, "update_multi": True},
        "header": {
            "title": {
                "content": _RESULT_TITLES.get(
                    normalized_command,
                    f"/{normalized_command}" if normalized_command else "命令反馈",
                ),
                "tag": "plain_text",
            },
            "template": _result_template(normalized_content),
        },
        "elements": elements,
    }


def _extract_metrics(content: str) -> list[tuple[str, str]]:
    metrics: list[tuple[str, str]] = []
    seen: set[str] = set()
    for line in content.splitlines():
        match = _METRIC_LINE_RE.match(line)
        if match is None:
            continue
        label = match.group(1).strip().strip("*`")
        value = match.group(2).strip().strip("*`")
        if not label or not value or label.casefold() in seen or len(value) > 80:
            continue
        seen.add(label.casefold())
        metrics.append((label[:24], value[:80]))
        if len(metrics) >= 4:
            break
    return metrics


def _result_template(content: str) -> str:
    lowered = content.lower()
    if content.startswith("❌") or "失败" in content or "error:" in lowered:
        return "red"
    if content.startswith(("⏳", "正在")) or lowered.startswith(("running", "starting")):
        return "blue"
    if content.startswith("⚠️") or "warning" in lowered or "取消" in content:
        return "orange"
    return "blue"
