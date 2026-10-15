"""Complete source survives native conversion, overflow projection and admission."""
import copy
from dataclasses import FrozenInstanceError
import json

import pytest

from hermes_feishu_card.content_plan import plan_main_content, render_content_plan
from hermes_feishu_card.render import render_card_result
from hermes_feishu_card.session import CardSession
from hermes_feishu_card.text import TABLE_COMPACT_NOTE, TABLE_TRUNCATE_NOTE, scan_markdown_blocks


def table(index, value=None):
    return f"| KEY_{index} | VALUE_{index} |\n| --- | --- |\n| ROW_{index} | {value or f'CELL_{index}_END'} |\n"


def session_snapshot(session):
    return copy.deepcopy({key: vars(value) if key.endswith("_normalizer") else value for key, value in vars(session).items()})


def test_mixed_native_code_long_cell_and_seven_tables_preserve_all_source_and_order():
    long_value = "字" * 2600 + "LONG_CELL_END"
    code = "```python\nprint('LITERAL_CODE')\n| NOT | A_TABLE |\n| --- | --- |\n| x | y |\n```"
    source = "INTRO\n\n" + "\n".join(table(index, long_value if index == 1 else None) + f"\nAFTER_{index}\n\n" for index in range(7)) + code + "\n\nFINAL_END"
    plan = plan_main_content(source, native_tables=True)
    before = copy.deepcopy(plan)
    elements = render_content_plan(plan, text_size="normal")
    assert plan == before and plan.source_text == source
    assert plan.complete
    assert plan.table_overflow.source_table_count == 7
    assert plan.table_overflow.compacted_table_count == 2
    assert plan.table_overflow.truncated_table_count == 0
    assert sum(element["tag"] == "table" for element in elements) == 4
    payload = json.dumps(elements, ensure_ascii=False)
    assert TABLE_COMPACT_NOTE in payload and TABLE_TRUNCATE_NOTE not in payload
    for index in range(7):
        assert f"KEY_{index}" in payload and f"ROW_{index}" in payload and f"AFTER_{index}" in payload
        if index != 1:
            assert payload.count(f"CELL_{index}_END") == 1
    markdown = [element["content"] for element in elements if element["tag"] == "markdown"]
    tables = [block.table for chunk in markdown for block in scan_markdown_blocks(chunk) if block.table]
    assert "".join(row[1] for item in tables if item.headers == ("KEY_1", "VALUE_1") for row in item.rows) == long_value
    assert code in "\n".join(markdown)
    assert payload.index("INTRO") < payload.index("KEY_0") < payload.index("LONG_CELL_END") < payload.index("KEY_6") < payload.index("FINAL_END")
    ids = [element["element_id"] for element in elements]
    assert len(set(ids)) == len(ids) and all(len(value) <= 20 for value in ids)
    with pytest.raises(FrozenInstanceError):
        plan.source_text = "shortened"


@pytest.mark.parametrize("native_tables", [False, True])
def test_explicit_truncate_marks_only_display_projection_and_retains_source(native_tables):
    source = "\n\n".join(table(index) + f"\nAFTER_{index}" for index in range(7))
    plan = plan_main_content(source, table_overflow_mode="truncate", native_tables=native_tables)
    assert plan.source_text == source
    assert not plan.complete
    assert plan.table_overflow.truncated_table_count == 2
    elements = render_content_plan(plan)
    payload = json.dumps(elements, ensure_ascii=False)
    assert payload.count(TABLE_TRUNCATE_NOTE) == 1
    for index in range(7):
        assert f"AFTER_{index}" in payload
        assert (f"CELL_{index}_END" in payload) is (index < 5)
        assert f"CELL_{index}_END" in plan.source_text


@pytest.mark.parametrize("kind", ["wide", "long_header", "empty"])
def test_unrepresentable_native_table_falls_back_to_complete_markdown(kind):
    if kind == "wide":
        headers = [f"H{index}" for index in range(51)]
        source = "| " + " | ".join(headers) + " |\n| " + " | ".join(["---"] * 51) + " |\n| " + " | ".join(f"V{index}_END" for index in range(51)) + " |\n"
    elif kind == "long_header":
        source = "| " + "字" * 1201 + "HEADER_END | V |\n| --- | --- |\n| row | VALUE_END |\n"
    else:
        source = "| EMPTY_HEADER | V |\n| --- | --- |\n"
    plan = plan_main_content(source, native_tables=True, chunk_chars=10000)
    elements = render_content_plan(plan)
    assert plan.complete and plan.source_text == source
    assert all(element["tag"] == "markdown" for element in elements)
    assert "".join(element["content"] for element in elements).strip() == source.strip()


@pytest.mark.parametrize("native_tables", [False, True])
def test_whole_card_capacity_can_reject_complete_plan_without_mutating_session(native_tables):
    source = table(0, "字" * 40000 + "COMPLETE_ANSWER_END")
    session = CardSession("fixture-conversation", "fixture-message", "fixture-chat")
    session.status = "completed"
    session.answer_text = source
    before = session_snapshot(session)
    plan = plan_main_content(source, native_tables=native_tables)
    assert plan.complete and plan.source_text == source
    result = render_card_result(session, native_tables=native_tables, presentation="task")
    assert result.disposition == "native"
    assert not result.inspection.safe
    assert session_snapshot(session) == before


@pytest.mark.parametrize("chunk_chars", [0, -1, True, 1.5, "2400"])
def test_invalid_chunk_budget_fails_before_content_projection(chunk_chars):
    with pytest.raises(ValueError, match="positive integer"):
        plan_main_content("KEEP_COMPLETE", chunk_chars=chunk_chars)
