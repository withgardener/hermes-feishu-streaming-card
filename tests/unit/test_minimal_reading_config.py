"""Minimal YAML replaces reading fields in the same scope, without exporting context."""
import copy
import json
import socket
import time

import pytest
import yaml

from hermes_feishu_card import cli, process
from hermes_feishu_card.config_snapshot import minimal_reading_config
from hermes_feishu_card.preview import build_preview
from hermes_feishu_card.reading import READING_FIELDS, explain_reading_config


PROFILE, BOT = "PRIVATE_PROFILE", "PRIVATE_BOT"
SECRET = "PRIVATE_SYNTHETIC_SECRET"


def example(scope, preset="task", legacy_hide=None):
    selected = {"reading_preset": preset, "show_reasoning": False, "timeline_expanded": False,
                "max_reasoning_chars": 1234, "text_sizes": {"body": "normal"}, "title": SECRET}
    if legacy_hide is not None:
        selected["hide_completed_tool_activity"] = legacy_hide
    raw = {"card": {"reading_preset": "task", "show_reasoning": False,
                    "timeline_expanded": False, "max_reasoning_chars": 9876,
                    "text_sizes": {"body": "large", "footer": "normal"}},
           "feishu": {"app_id": SECRET, "app_secret": SECRET}}
    if scope == "global":
        raw["card"] = selected
        return raw, (), {}
    raw["profiles"] = {PROFILE: {"card": selected, "feishu": {"app_id": SECRET, "app_secret": SECRET}}}
    if scope == "profile":
        return raw, ("profiles", PROFILE), {"profile_id": PROFILE}
    raw["profiles"][PROFILE]["card"] = {"reading_preset": "focused", "text_sizes": {"body": "large"}}
    raw["profiles"][PROFILE]["bots"] = {"items": {BOT: {"app_id": SECRET, "app_secret": SECRET, "card": selected}}}
    raw["profiles"][PROFILE]["bindings"] = {"fallback_bot": BOT}
    return raw, ("profiles", PROFILE, "bots", "items", BOT), {"profile_id": PROFILE, "bot_id": BOT}


def replace_reading_fields(raw, path, card):
    edited = copy.deepcopy(raw)
    scope = edited
    for key in path:
        scope = scope[key]
    scope["card"] = {**{key: value for key, value in scope.get("card", {}).items() if key not in READING_FIELDS}, **card}
    return edited


def normalized_markdown_sizes(value):
    """An explicit normal Markdown size and the platform default render alike."""
    if isinstance(value, list):
        return [normalized_markdown_sizes(item) for item in value]
    if isinstance(value, dict):
        return {key: normalized_markdown_sizes(item) for key, item in value.items()
                if not (key == "text_size" and item == "normal" and value.get("tag") == "markdown")}
    return value


@pytest.mark.parametrize("scope", ["global", "profile", "bot"])
@pytest.mark.parametrize("preset", ["classic", "focused", "detailed", "task"])
@pytest.mark.parametrize("legacy_hide", [None, False, True])
def test_minimal_yaml_roundtrips_under_unchanged_parents_without_private_fields(scope, preset, legacy_hide):
    raw, path, selectors = example(scope, preset, legacy_hide)
    before = copy.deepcopy(raw)
    expected = explain_reading_config(raw, **selectors)
    kind, snippet = minimal_reading_config(raw, **selectors)
    assert kind == scope and raw == before
    assert set(snippet) == {"card"}
    assert set(snippet["card"]) <= set(READING_FIELDS)
    assert not any(secret in yaml.safe_dump(snippet) for secret in (PROFILE, BOT, SECRET))
    restored = replace_reading_fields(raw, path, yaml.safe_load(yaml.safe_dump(snippet))["card"])
    actual = explain_reading_config(restored, **selectors)
    assert actual["values"] == expected["values"]
    assert actual["values"]["max_reasoning_chars"] == 1234
    assert actual["values"]["text_sizes"]["body"] == "normal"
    assert actual["values"]["timeline_expanded"] is False
    if legacy_hide is False:
        assert actual["values"]["terminal_tool_activity"] == "visible"
    elif legacy_hide is None and preset in {"focused", "task"}:
        assert actual["values"]["terminal_tool_activity"] == "failed_only"
    # Every remaining optional field must be necessary in the unchanged parents.
    for field in snippet["card"]:
        if field == "reading_preset":
            continue
        shorter = copy.deepcopy(snippet["card"])
        del shorter[field]
        assert explain_reading_config(replace_reading_fields(raw, path, shorter), **selectors)["values"] != expected["values"], field


@pytest.mark.parametrize("scope", ["global", "profile", "bot"])
def test_minimal_cli_is_read_only_offline_private_and_matches_preview(tmp_path, monkeypatch, capsys, scope):
    monkeypatch.setattr(time, "time", lambda: 1777017600.0)
    raw, selected_path, selectors = example(scope, legacy_hide=False)
    path, preview = tmp_path / "PRIVATE_CONFIG.yaml", tmp_path / "preview"
    path.write_text(yaml.safe_dump(raw))
    before = path.read_bytes()
    monkeypatch.setattr(socket.socket, "connect", lambda *args, **kwargs: pytest.fail("minimal YAML attempted network"))
    monkeypatch.setattr(process, "fetch_loaded_card_config", lambda *args, **kwargs: pytest.fail("minimal YAML read a live process"))
    args = ["card-config", "--config", str(path), "--minimal-yaml", "--preview-dir", str(preview)]
    for key, value in selectors.items():
        args += ["--" + key.replace("_", "-"), value]
    assert cli.main(args) == 0
    output = capsys.readouterr()
    for secret in (PROFILE, BOT, SECRET, str(path)):
        assert secret not in output.out + output.err
    assert f"selected {scope} card block" in output.out
    snippet = yaml.safe_load(output.out)
    restored = replace_reading_fields(raw, selected_path, snippet["card"])
    expected = explain_reading_config(restored, **selectors)
    artifact = json.loads((preview / "cards.json").read_text())
    assert artifact["configuration"]["values"] == expected["values"]
    # Pin the animation frame while comparing the two equivalent configurations.
    before_cards = build_preview(explain_reading_config(raw, **selectors))
    after_cards = build_preview(expected)
    before_payloads = [s["cards"] for s in before_cards["scenarios"]]
    after_payloads = [s["cards"] for s in after_cards["scenarios"]]
    assert normalized_markdown_sizes(before_payloads) == normalized_markdown_sizes(after_payloads)
    # The selected task rendering also remains byte-for-byte equal as JSON.
    assert [s["task"] for s in before_payloads] == [s["task"] for s in after_payloads]
    assert path.read_bytes() == before
    for artifact_path in preview.iterdir():
        text = artifact_path.read_text()
        assert all(secret not in text for secret in (PROFILE, BOT, SECRET, str(path)))


def test_running_and_json_modes_cannot_mix_with_minimal_yaml(tmp_path, monkeypatch, capsys):
    path = tmp_path / "config.yaml"
    path.write_text("card: {}")
    monkeypatch.setattr(process, "fetch_loaded_card_config", lambda *args, **kwargs: pytest.fail("invalid combination read live config"))
    assert cli.main(["card-config", "--config", str(path), "--minimal-yaml", "--running"]) == 2
    assert "Use --running separately" in capsys.readouterr().err
    with pytest.raises(SystemExit) as error:
        cli.main(["card-config", "--config", str(path), "--minimal-yaml", "--json"])
    assert error.value.code == 2
