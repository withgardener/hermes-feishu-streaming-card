"""Native Feishu table elements (``card.native_tables``).

Markdown tables cannot set a column width, so a long value column gets
squeezed into mid-word breaks. ``card.native_tables: true`` renders body
tables as the card's native ``table`` element instead, which supports
``row_height: auto`` (row grows to fit wrapped content) and per-column
``width``. These tests pin the payload contract and the Markdown fallback.
"""
import json
import time

import pytest

from hermes_feishu_card.card_limits import inspect_card_limits
from hermes_feishu_card.native_tables import (
    build_main_content_elements,
    column_widths,
    normalize_cell,
)
from hermes_feishu_card.render import render_card, render_card_result
from hermes_feishu_card.render_options import card_render_options
from hermes_feishu_card.session import CardSession
from hermes_feishu_card.text import scan_markdown_blocks

CHUNK_CHARS = 2400


def build_main_content_elements_chunked(text, **kwargs):
    """Module entry point with the renderer's chunk budget applied."""
    return build_main_content_elements(text, chunk_chars=CHUNK_CHARS, **kwargs)

STATUS_TABLE = (
    "| 指标 | 值 |\n"
    "| --- | --- |\n"
    "| status | healthy |\n"
    "| delivery | live |\n"
    "| bot_count | 1 |\n"
    "| send_failures | 0 |\n"
    "| readiness | runtime_ready |\n"
    "| ctrl_events | 2（重启后开始增长） |\n"
    "| smoke-feishu-card | `smoke ok` + `message_id: message#0891bd7f54` |\n"
)


def _session(answer: str) -> CardSession:
    session = CardSession("c", "m", "c")
    session.created_at = time.time() - 20
    session.updated_at = time.time() - 1
    session.status = "completed"
    session.duration = 12.5
    session.model = "deepseek-v4-flash"
    session.answer_text = answer
    return session


def _main_elements(card):
    return [
        element
        for element in card["body"]["elements"]
        if str(element.get("element_id", "")).startswith("main_content")
    ]


def _table_element(card):
    return next(
        element for element in card["body"]["elements"] if element.get("tag") == "table"
    )


def test_native_tables_default_is_off():
    assert card_render_options({})["native_tables"] is False
    assert card_render_options({"native_tables": True})["native_tables"] is True
    assert card_render_options({"native_tables": "yes"})["native_tables"] is True
    assert card_render_options({"native_tables": "off"})["native_tables"] is False


def test_markdown_table_is_untouched_when_disabled():
    card = render_card(_session(STATUS_TABLE))
    elements = _main_elements(card)
    assert [element["tag"] for element in elements] == ["markdown"]
    assert "| 指标 | 值 |" in elements[0]["content"]
    assert not [e for e in card["body"]["elements"] if e.get("tag") == "table"]


def test_native_table_replaces_markdown_table():
    card = render_card(_session(STATUS_TABLE), native_tables=True)
    table = _table_element(card)
    assert table["element_id"] == "main_content_t0"
    assert table["row_height"] == "auto"
    assert table["row_max_height"] == "999px"
    assert table["page_size"] == 7
    assert table["header_style"]["background_style"] == "grey"
    assert [column["display_name"] for column in table["columns"]] == ["指标", "值"]
    assert [column["data_type"] for column in table["columns"]] == [
        "markdown",
        "markdown",
    ]
    assert table["rows"][0] == {"c0": "status", "c1": "healthy"}
    assert table["rows"][-1]["c0"] == "smoke-feishu-card"
    assert "message#0891bd7f54" in table["rows"][-1]["c1"]
    # The Markdown copy must be gone, or the table would render twice.
    assert "| 指标 | 值 |" not in "".join(
        element.get("content", "") for element in _main_elements(card)
    )


def test_prose_around_table_keeps_its_order_and_ids():
    answer = "结论见下表。\n\n" + STATUS_TABLE + "\n补充说明。\n"
    card = render_card(_session(answer), native_tables=True)
    elements = _main_elements(card)
    assert [element["tag"] for element in elements] == ["markdown", "table", "markdown"]
    assert elements[0]["element_id"] == "main_content"
    assert elements[1]["element_id"] == "main_content_t0"
    assert elements[2]["element_id"] == "main_content_1"
    assert "结论见下表" in elements[0]["content"]
    assert "补充说明" in elements[2]["content"]


def test_no_table_keeps_the_markdown_layout():
    assert build_main_content_elements_chunked("只有正文，没有表格。") is None
    card = render_card(_session("只有正文，没有表格。"), native_tables=True)
    assert [element["tag"] for element in _main_elements(card)] == ["markdown"]


def test_column_widths_are_content_driven_and_sum_to_100():
    table = next(
        block.table
        for block in scan_markdown_blocks(STATUS_TABLE)
        if block.kind == "table"
    )
    widths = column_widths(table.headers, table.rows, 2)
    assert widths == ["30%", "70%"]

    symmetric = "| 检查项 | 结果 |\n| --- | --- |\n| 配置解析 | 通过 |\n| 文档链接 | 通过 |\n"
    table = next(
        block.table
        for block in scan_markdown_blocks(symmetric)
        if block.kind == "table"
    )
    assert column_widths(table.headers, table.rows, 2) == ["50%", "50%"]

    for text, columns in ((STATUS_TABLE, 2), (symmetric, 2)):
        table = next(
            block.table
            for block in scan_markdown_blocks(text)
            if block.kind == "table"
        )
        percents = [
            int(width.rstrip("%"))
            for width in column_widths(table.headers, table.rows, columns)
        ]
        assert sum(percents) == 100
        assert all(15 <= percent <= 70 for percent in percents)


def test_ragged_rows_and_escaped_pipes_are_normalized():
    text = (
        "| a | b | c |\n"
        "| --- | --- | --- |\n"
        "| 1 | 2 |\n"
        "| x\\|y | `z` | 3 |\n"
    )
    table = next(
        block.table for block in scan_markdown_blocks(text) if block.kind == "table"
    )
    elements = build_main_content_elements_chunked(text)
    native = elements[0]
    assert [column["name"] for column in native["columns"]] == ["c0", "c1", "c2"]
    assert native["rows"][0] == {"c0": "1", "c1": "2", "c2": ""}
    assert native["rows"][1]["c0"] == "x|y"


@pytest.mark.parametrize("columns", range(1, 51))
def test_column_widths_fill_available_width_for_all_supported_column_counts(columns):
    headers = tuple("h" for _ in range(columns))
    rows = (tuple("long value" * (index + 1) for index in range(columns)),)
    widths = [int(value[:-1]) for value in column_widths(headers, rows, columns)]
    assert len(widths) == columns
    assert sum(widths) == 100
    assert all(0 < width <= 100 for width in widths)


def test_cell_normalization_is_lossless_and_single_line():
    assert normalize_cell(None) == ""
    assert normalize_cell("  a\nb  ") == "a b"
    assert normalize_cell("x\\|y") == "x|y"
    long = normalize_cell("字" * 5000)
    assert long == "字" * 5000


@pytest.mark.parametrize("length", [1199, 1200, 1201, 5000])
@pytest.mark.parametrize("character", ["x", "字"])
@pytest.mark.parametrize("position", ["header", "body"])
@pytest.mark.parametrize("presentation", ["default", "task"])
def test_long_cells_preserve_complete_content(length, character, position, presentation):
    marker = "TAIL_MUST_SURVIVE"
    value = character * (length - len(marker)) + marker
    header = value if position == "header" else "value"
    body = value if position == "body" else "data"
    text = f"| key | {header} |\n| --- | --- |\n| item | {body} |\n"
    session = _session(text)
    card = (
        render_card(session, native_tables=True)
        if presentation == "default"
        else render_card_result(session, native_tables=True, presentation="task").card
    )
    elements = _main_elements(card)
    if length <= 1200:
        table = _table_element(card)
        actual = (
            table["columns"][1]["display_name"]
            if position == "header" else table["rows"][0]["c1"]
        )
        assert actual == value
    else:
        assert all(element["tag"] == "markdown" for element in elements)
        markdown = "".join(element["content"] for element in elements)
        if position == "header":
            assert value in markdown
        else:
            # Markdown may repeat headers while splitting an oversized data row.
            tables = [block.table for element in elements
                      for block in scan_markdown_blocks(element["content"])
                      if block.table is not None]
            assert "".join(row[1] for table in tables for row in table.rows) == value
    assert inspect_card_limits(card).safe


def test_oversized_table_fallback_preserves_order_between_native_tables():
    value = "字" * 1200 + "TAIL_MUST_SURVIVE"
    oversized = f"| key | value |\n| --- | --- |\n| item | {value} |\n"
    text = STATUS_TABLE + "\nBEFORE\n\n" + oversized + "\nAFTER\n\n" + STATUS_TABLE
    elements = build_main_content_elements_chunked(text)
    assert [element["tag"] for element in elements] == ["table", "markdown", "table"]
    assert oversized in elements[1]["content"]
    assert elements[1]["content"].index("BEFORE") < elements[1]["content"].index(value)
    assert elements[1]["content"].index(value) < elements[1]["content"].index("AFTER")
    ids = [element["element_id"] for element in elements]
    assert len(ids) == len(set(ids))


@pytest.mark.parametrize("native_tables", [False, True])
@pytest.mark.parametrize("presentation", ["classic", "task"])
def test_indivisible_table_exceeding_card_budget_hands_off_complete_answer(native_tables, presentation):
    value = "字" * 10000 + "TAIL_MUST_SURVIVE"
    text = f"| key | {value} |\n| --- | --- |\n| item | data |\n"
    session = _session(text)
    result = render_card_result(session, native_tables=native_tables, presentation=presentation)
    assert result.disposition == "native"
    assert session.answer_text == text
    assert not result.inspection.safe


def test_wide_table_falls_back_to_markdown():
    header = "| " + " | ".join(f"h{index}" for index in range(51)) + " |"
    separator = "| " + " | ".join("---" for _ in range(51)) + " |"
    row = "| " + " | ".join("v" for _ in range(51)) + " |"
    text = "\n".join((header, separator, row)) + "\n"
    assert build_main_content_elements_chunked(text) is None
    card = render_card(_session(text), native_tables=True)
    assert [element["tag"] for element in _main_elements(card)] == ["markdown"]


def test_native_table_card_stays_inside_feishu_limits():
    card = render_card(_session(STATUS_TABLE), native_tables=True)
    inspection = inspect_card_limits(card)
    assert inspection.safe
    assert inspection.table_count == 1
    # Element ids must satisfy the CardKit 20-character / uniqueness contract.
    ids = [
        element["element_id"]
        for element in card["body"]["elements"]
        if "element_id" in element
    ]
    assert len(ids) == len(set(ids))
    assert all(len(element_id) <= 20 for element_id in ids)


def test_native_tables_survive_task_presentation_cleanup():
    session = _session(STATUS_TABLE)
    card = render_card_result(session, native_tables=True, presentation="task").card
    table = _table_element(card)
    assert table["tag"] == "table"
    assert table["element_id"].startswith("main_content")
    assert json.dumps(card, ensure_ascii=False)


def test_table_element_builder_payload_contract():
    from hermes_feishu_card.native_tables import build_table_element

    table = next(
        block.table
        for block in scan_markdown_blocks(STATUS_TABLE)
        if block.kind == "table"
    )
    element = build_table_element(table, 3)
    assert element["tag"] == "table"
    assert element["element_id"] == "main_content_t3"
    assert element["row_height"] == "auto"
    assert element["row_max_height"] == "999px"
    assert element["page_size"] == 7
    assert set(element) == {
        "tag", "element_id", "page_size", "row_height", "row_max_height",
        "header_style", "columns", "rows",
    }
    assert set(element["header_style"]) == {
        "text_align", "text_size", "background_style", "text_color", "bold", "lines",
    }
    assert set(element["columns"][0]) == {
        "name", "display_name", "data_type", "width", "horizontal_align", "vertical_align",
    }


def test_table_element_builder_rejects_unrepresentable_tables():
    from hermes_feishu_card.native_tables import MAX_COLUMNS, build_table_element
    from hermes_feishu_card.text import MarkdownTable

    empty = MarkdownTable(headers=("a", "b"), rows=(), raw="")
    assert build_table_element(empty, 0) is None

    header = tuple(f"h{index}" for index in range(MAX_COLUMNS + 1))
    row = tuple("v" for _ in header)
    wide = MarkdownTable(headers=header, rows=(row,), raw="")
    assert build_table_element(wide, 0) is None
