"""Validate the bounded reading-value control protocol."""
import copy

import pytest

from hermes_feishu_card.config_snapshot import compare_reading_values, validated_reading_values
from hermes_feishu_card.reading import explain_reading_config


@pytest.mark.parametrize("before,after", [("auto", "callback"), ("callback", "auto"), ("text", "markdown"), ("reply", "text")])
def test_interaction_syntax_aliases_do_not_report_running_differences(before, after):
    loaded = explain_reading_config({})["values"]
    next_load = copy.deepcopy(loaded)
    loaded["interaction_mode"], next_load["interaction_mode"] = before, after
    assert compare_reading_values(next_load, loaded) == []
    next_load["timeline_expanded"] = not loaded["timeline_expanded"]
    assert compare_reading_values(next_load, loaded) == [{"field": "timeline_expanded", "loaded": loaded["timeline_expanded"], "next_load": next_load["timeline_expanded"]}]


@pytest.mark.parametrize("mutate", [
    lambda value: value.update(secret="untrusted-control-extra"),
    lambda value: value.pop("show_reasoning"),
    lambda value: value.update(timeline_expanded="false"),
    lambda value: value.update(max_timeline_items=float("nan")),
    lambda value: value.update(text_sizes={"answer": "untrusted-size"}),
    lambda value: value.update(footer_fields=["duration", "private-token"]),
    lambda value: value.update(presentation="unknown"),
    lambda value: value.update(terminal_tool_activity="unknown"),
])
def test_control_values_reject_unknown_or_noncanonical_values_without_mutation(mutate):
    value = explain_reading_config({"card": {"reading_preset": "task"}})["values"]
    mutate(value)
    before = repr(value)
    assert validated_reading_values(value) is None
    assert repr(value) == before


@pytest.mark.parametrize("preset", ["classic", "focused", "detailed", "task"])
def test_validated_control_values_preserve_canonical_values_and_explicit_false(preset):
    value = explain_reading_config({"card": {"reading_preset": preset, "timeline_expanded": False, "show_reasoning": False}})["values"]
    before = copy.deepcopy(value)
    assert validated_reading_values(value) == value == before
