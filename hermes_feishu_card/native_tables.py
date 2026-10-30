"""Native Feishu card ``table`` elements built from body Markdown tables.

The Markdown rich-text component cannot set a table column width (Feishu docs:
"表格的富文本语法不支持设置列宽等"), so a long value column is squeezed into
mid-word breaks and the client owns the layout. The card's native ``table``
element supports ``row_height: auto`` — the row grows to fit wrapped content
instead of clipping the cell with an ellipsis — plus a per-column ``width``.

This module owns that conversion and its payload contract. It is opt-in
(``card.native_tables``), preserves answer text byte for byte, and returns
``None`` whenever no table can be represented natively so the caller keeps the
existing Markdown layout. Element ids keep the ``main_content`` prefix used by
``render._render_main_content_elements`` so task-presentation cleanup and the
CardKit text partition keep working unchanged.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from .text import MarkdownTable, _stable_table_headers, scan_markdown_blocks, split_markdown_blocks

MAX_COLUMNS = 50
MAX_PAGE_SIZE = 10
MIN_COLUMN_PERCENT = 15
MAX_COLUMN_PERCENT = 70
MAX_CELL_CHARS = 1200
ROW_MAX_HEIGHT_PX = 999


def normalize_cell(value: Any) -> str:
    """Normalize one Markdown table cell into a native table cell string."""
    text = "" if value is None else str(value)
    text = text.replace("\\|", "|").replace("\r", " ").replace("\n", " ").strip()
    return text


def column_widths(
    headers: tuple[str, ...],
    rows: tuple[tuple[str, ...], ...],
    column_count: int,
) -> list[str]:
    """Percent widths derived from the content, clamped for readability.

    Markdown tables cannot set column widths at all, which is exactly why a
    narrow label column squeezes a long value column into mid-word breaks. A
    native table can, so derive the split from the observed cell lengths: the
    mean and upper quartile keep a column of medium cells honest, the longest
    cell keeps a genuine outlier from being cut, and the clamps stop one column
    from owning the whole canvas.
    """
    if column_count == 1:
        return ["100%"]
    # Seven or more columns cannot all occupy at least 15%. Lower the floor
    # for wide tables so rounding can still produce exactly 100% in total.
    min_percent = min(MIN_COLUMN_PERCENT, 100 // column_count)
    weights: list[int] = []
    for index in range(column_count):
        lengths = [len(headers[index]) if index < len(headers) else 0]
        lengths.extend(len(row[index]) if index < len(row) else 0 for row in rows)
        ordered = sorted(lengths)
        probe = ordered[min(len(ordered) - 1, int(len(ordered) * 0.75))]
        mean = sum(lengths) / len(lengths)
        weights.append(max(6, min(48, round(max(mean, probe, 0.75 * ordered[-1])))))
    total = sum(weights) or column_count
    percents = [
        max(min_percent, min(MAX_COLUMN_PERCENT, round(weight * 100 / total)))
        for weight in weights
    ]
    drift = sum(percents) - 100
    if drift:
        for index in sorted(
            range(column_count), key=lambda position: percents[position], reverse=drift > 0
        ):
            if drift > 0:
                step = min(drift, percents[index] - min_percent)
                percents[index] -= step
                drift -= step
            else:
                step = min(-drift, MAX_COLUMN_PERCENT - percents[index])
                percents[index] += step
                drift += step
            if drift == 0:
                break
    return [f"{percent}%" for percent in percents]


def build_table_element(table: MarkdownTable, index: int) -> Optional[Dict[str, Any]]:
    """Build one native ``table`` element from a parsed Markdown table.

    ``row_height: auto`` is the point of the conversion: it grows the row to fit
    wrapped content instead of clipping the cell. Returns ``None`` when the
    table cannot be represented natively (no data rows, too many columns, or
    a header/cell beyond our native display limit), so the caller keeps the
    original Markdown text for it. Final answer content must never be truncated.
    """
    column_count = max(
        [len(table.headers), *(len(row) for row in table.rows)],
        default=len(table.headers),
    )
    if column_count < 1 or column_count > MAX_COLUMNS or not table.rows:
        return None
    headers = _stable_table_headers(table.headers, column_count)
    if any(len(normalize_cell(value)) > MAX_CELL_CHARS for value in headers) or any(
        len(normalize_cell(value)) > MAX_CELL_CHARS
        for row in table.rows for value in row
    ):
        return None
    names = [f"c{position}" for position in range(column_count)]
    widths = column_widths(table.headers, table.rows, column_count)
    columns = [
        {
            "name": names[position],
            "display_name": normalize_cell(headers[position]),
            "data_type": "markdown",
            "width": widths[position],
            "horizontal_align": "left",
            "vertical_align": "top",
        }
        for position in range(column_count)
    ]
    rows = [
        {
            names[position]: normalize_cell(row[position] if position < len(row) else "")
            for position in range(column_count)
        }
        for row in table.rows
    ]
    return {
        "tag": "table",
        "element_id": f"main_content_t{index}",
        "page_size": max(1, min(len(rows), MAX_PAGE_SIZE)),
        "row_height": "auto",
        "row_max_height": f"{ROW_MAX_HEIGHT_PX}px",
        "header_style": {
            "text_align": "left",
            "text_size": "normal",
            "background_style": "grey",
            "text_color": "grey",
            "bold": True,
            "lines": 1,
        },
        "columns": columns,
        "rows": rows,
    }


def _markdown_elements(
    text: str,
    index: int,
    *,
    chunk_chars: int,
    text_size: Optional[str],
) -> tuple[list[Dict[str, Any]], int]:
    """Chunk one Markdown span and return ``(elements, next_index)``."""
    if not text.strip():
        return [], index
    elements: list[Dict[str, Any]] = []
    for chunk in split_markdown_blocks(text, chunk_chars):
        element: Dict[str, Any] = {
            "tag": "markdown",
            "element_id": "main_content" if index == 0 else f"main_content_{index}",
            "content": chunk,
        }
        if text_size is not None:
            element["text_size"] = text_size
        elements.append(element)
        index += 1
    return elements, index


def build_main_content_elements(
    text: str,
    *,
    chunk_chars: int,
    text_size: Optional[str] = None,
) -> Optional[list[Dict[str, Any]]]:
    """Interleave Markdown elements with native table elements, in order.

    Returns ``None`` when no table in the text can be converted, so the caller
    keeps the Markdown-only layout (byte-identical to the pre-feature output).
    """
    blocks = scan_markdown_blocks(text)
    if not any(block.kind == "table" and block.table is not None for block in blocks):
        return None
    elements: list[Dict[str, Any]] = []
    buffer = ""
    markdown_index = 0
    table_index = 0
    converted_tables = 0
    for block in blocks:
        element = (
            build_table_element(block.table, table_index)
            if block.kind == "table" and block.table is not None
            else None
        )
        if element is None:
            buffer += block.text
            continue
        chunked, markdown_index = _markdown_elements(
            buffer, markdown_index, chunk_chars=chunk_chars, text_size=text_size
        )
        elements.extend(chunked)
        buffer = ""
        elements.append(element)
        table_index += 1
        converted_tables += 1
    if not converted_tables:
        return None
    chunked, markdown_index = _markdown_elements(
        buffer, markdown_index, chunk_chars=chunk_chars, text_size=text_size
    )
    elements.extend(chunked)
    return elements or None
