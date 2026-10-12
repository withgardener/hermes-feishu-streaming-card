from hermes_feishu_card.render import MAIN_CONTENT_CHUNK_CHARS
from hermes_feishu_card.text import (
    StreamingTextNormalizer,
    count_markdown_tables,
    normalize_stream_text,
    scan_markdown_blocks,
    should_flush_text,
    split_markdown_blocks,
    transform_table_overflow,
)


def test_normalize_removes_think_tags():
    raw = "<think>我在分析</think>\n最终不会出现标签"
    assert normalize_stream_text(raw) == "我在分析\n最终不会出现标签"


def test_normalize_removes_mixed_case_think_tags():
    raw = "<THINK>我在分析</Think>\n最终不会出现标签"
    assert normalize_stream_text(raw) == "我在分析\n最终不会出现标签"


def test_normalize_handles_empty_input():
    assert normalize_stream_text("") == ""
    assert normalize_stream_text(None) == ""


def test_streaming_normalizer_removes_split_think_tags():
    normalizer = StreamingTextNormalizer()

    chunks = ["<thi", "nk>分片</thi", "nk>"]
    result = "".join(normalizer.feed(chunk) for chunk in chunks)

    assert result == "分片"


def test_streaming_normalizer_removes_mixed_case_split_think_tags():
    normalizer = StreamingTextNormalizer()

    chunks = ["<TH", "INK>分片</Th", "ink>"]
    result = "".join(normalizer.feed(chunk) for chunk in chunks)

    assert result == "分片"


def test_flushes_on_chinese_sentence_end():
    assert should_flush_text("我先分析这个问题。", elapsed_ms=50, max_wait_ms=800, max_chars=200)


def test_flushes_on_newline_boundary():
    assert should_flush_text("第一段\n", elapsed_ms=50, max_wait_ms=800, max_chars=200)


def test_flushes_on_wait_threshold():
    assert should_flush_text("半句话", elapsed_ms=801, max_wait_ms=800, max_chars=200)


def test_flushes_on_equal_wait_threshold():
    assert should_flush_text("半句话", elapsed_ms=800, max_wait_ms=800, max_chars=200)


def test_flushes_on_equal_max_chars():
    assert should_flush_text("四个字", elapsed_ms=50, max_wait_ms=800, max_chars=3)


def test_force_flushes_empty_buffer():
    assert should_flush_text("", elapsed_ms=0, max_wait_ms=800, max_chars=200, force=True)


def test_does_not_flush_tiny_fragment_too_early():
    assert not should_flush_text("半句话", elapsed_ms=100, max_wait_ms=800, max_chars=200)


def test_normalize_removes_thinking_tags():
    assert normalize_stream_text("<thinking>推理中</thinking>结果") == "推理中结果"
    assert normalize_stream_text("<THINKING>推理</THINKING>") == "推理"


def test_streaming_normalizer_handles_thinking_split_across_chunks():
    normalizer = StreamingTextNormalizer()
    assert normalizer.feed("hello<think") == "hello"
    assert normalizer.feed("ing>world") == "world"


def test_normalize_does_not_remove_plain_think_word():
    assert normalize_stream_text("I think so") == "I think so"
    assert normalize_stream_text("I am thinking") == "I am thinking"


# —— 表格统计 ————————————————————————————————

def test_count_markdown_tables_zero():
    from hermes_feishu_card.text import count_markdown_tables
    assert count_markdown_tables("hello world") == 0
    assert count_markdown_tables("| name | age |") == 0  # no separator


def test_count_markdown_tables_normal():
    text = "| a | b |\n| --- | --- |\n| 1 | 2 |\n\n| x | y |\n| --- | --- |\n| 3 | 4 |"
    assert count_markdown_tables(text) == 2


def test_count_markdown_tables_seven():
    text = "\n\n".join([f"| col |\n| --- |\n| {i} |" for i in range(7)])
    assert count_markdown_tables(text) == 7


def test_scanner_ignores_backtick_and_tilde_fenced_fake_tables():
    text = """before

```markdown
| fake |
| --- |
| one |
```

~~~
fake | value
--- | ---
one | two
~~~

real | value
--- | ---
one | two
"""

    blocks = scan_markdown_blocks(text)

    assert count_markdown_tables(text) == 1
    assert [block.kind for block in blocks].count("table") == 1
    table = next(block.table for block in blocks if block.kind == "table")
    assert table is not None
    assert table.headers == ("real", "value")
    assert table.rows == (("one", "two"),)


def test_scanner_handles_outer_pipes_escaped_pipes_inline_code_and_ragged_rows():
    text = """| Name | Value |  |
| :--- | ---: | --- |
| escaped | left\\|right | tail |
| inline | `a|b` |
"""

    table = next(
        block.table for block in scan_markdown_blocks(text) if block.kind == "table"
    )

    assert table is not None
    assert table.headers == ("Name", "Value", "")
    assert table.rows == (
        ("escaped", "left\\|right", "tail"),
        ("inline", "`a|b`"),
    )


def test_compact_overflow_preserves_all_cells_with_stable_header_fallbacks():
    tables = [
        f"| H |\n| --- |\n| {index} |" for index in range(5)
    ]
    tables.extend(
        [
            "| Name | Name |  |\n| --- | --- | --- |\n| alice | alias | extra |\n| bob |",
            "A | B\n--- | ---\nlast-a | last-b",
        ]
    )
    source = "\n\n".join(tables) + "\n\nTAIL MUST LIVE"

    result = transform_table_overflow(source, mode="compact")

    assert result.source_table_count == 7
    assert result.compacted_table_count == 2
    assert result.truncated_table_count == 0
    assert count_markdown_tables(result.text) == 5
    assert result.text.count("已转换为紧凑字段列表") == 1
    assert "**Table 6 · Row 1**" in result.text
    assert "- Name: alice" in result.text
    assert "- Name (2): alias" in result.text
    assert "- Column 3: extra" in result.text
    assert "**Table 6 · Row 2**" in result.text
    assert "- Name: bob" in result.text
    assert "**Table 7 · Row 1**" in result.text
    assert "- A: last-a" in result.text
    assert "- B: last-b" in result.text
    assert result.text.endswith("TAIL MUST LIVE")


def test_truncate_overflow_removes_only_tables_and_preserves_later_prose():
    source = "\n\n".join(
        f"| H |\n| --- |\n| {index} |" for index in range(7)
    ) + "\n\nTAIL MUST LIVE"

    result = transform_table_overflow(source, mode="truncate")

    assert result.source_table_count == 7
    assert result.compacted_table_count == 0
    assert result.truncated_table_count == 2
    assert count_markdown_tables(result.text) == 5
    assert result.text.count("超出部分已省略") == 1
    assert result.text.endswith("TAIL MUST LIVE")


def test_compact_overflow_preserves_trailing_prose_whitespace_verbatim():
    source = "\n\n".join(
        f"| H |\n| --- |\n| {index} |" for index in range(6)
    ) + "\n\nTAIL  "

    result = transform_table_overflow(source, mode="compact")

    assert result.text.endswith("TAIL  ")


def test_compact_empty_overflow_table_preserves_its_headers():
    source = "\n\n".join(
        [f"| H |\n| --- |\n| {index} |" for index in range(5)]
        + ["| Name |  |\n| --- | --- |"]
    )

    result = transform_table_overflow(source, mode="compact")

    assert "**Table 6**" in result.text
    assert "- Columns: Name, Column 2" in result.text
    assert "- Rows: （空）" in result.text


def test_max_card_tables_constant():
    from hermes_feishu_card.text import MAX_CARD_TABLES
    assert MAX_CARD_TABLES == 5


def test_split_markdown_blocks_preserves_table_structure():
    table = "| 功能 | 说明 |\n| --- | --- |\n| ASR | 中文识别 |\n| VAD | 静音切割 |"
    text = "A" * 1000 + "\n\n" + table + "\n\n" + "B" * 1000

    chunks = split_markdown_blocks(text, 1200)

    table_chunks = [chunk for chunk in chunks if "| ASR |" in chunk]
    assert len(table_chunks) == 1
    assert table in table_chunks[0]


def test_split_markdown_blocks_preserves_fenced_code_block():
    code = "```python\nprint('hello')\nprint('world')\n```"
    text = "X" * 1000 + "\n\n" + code + "\n\n" + "Y" * 1000

    chunks = split_markdown_blocks(text, 1100)

    code_chunks = [chunk for chunk in chunks if "```python" in chunk]
    assert len(code_chunks) == 1
    assert code in code_chunks[0]


def test_split_markdown_blocks_splits_oversized_plain_text():
    text = "Hello world " * 500

    chunks = split_markdown_blocks(text, 1000)

    assert len(chunks) > 1
    assert "".join(chunks).replace("\n", "") == text.replace("\n", "")
    assert all(len(chunk) <= 1000 for chunk in chunks)


def test_split_markdown_blocks_prefers_list_item_boundaries():
    text = "\n".join(f"1. item {index} {'甲' * 40}" for index in range(80))

    chunks = split_markdown_blocks(text, 120)

    assert len(chunks) > 1
    assert all(len(chunk) <= 120 for chunk in chunks)
    assert all(chunk.startswith("1. ") for chunk in chunks[1:])
    assert "".join(chunks).replace("\n", "") == text.replace("\n", "")


def test_split_markdown_blocks_avoids_inline_code_split_when_possible():
    text = "前言\n\n" + " ".join("`alpha beta gamma delta epsilon`" for _ in range(80))

    chunks = split_markdown_blocks(text, 120)

    assert len(chunks) > 1
    assert all(len(chunk) <= 120 for chunk in chunks)
    for chunk in chunks:
        assert chunk.count("`") % 2 == 0


def test_split_markdown_blocks_handles_oversized_table_row_without_plain_fragments():
    oversized_value = "超长字段" * 700
    table = f"| 字段 | 内容 |\n| --- | --- |\n| key | {oversized_value} |\n"

    chunks = split_markdown_blocks(table, MAIN_CONTENT_CHUNK_CHARS)

    assert len(chunks) > 1
    assert all(len(chunk) <= MAIN_CONTENT_CHUNK_CHARS for chunk in chunks)
    for chunk in chunks:
        if "| --- | --- |" in chunk:
            lines = [line for line in chunk.splitlines() if line.strip()]
            assert len(lines) >= 3
            assert lines[0].startswith("|")
            assert lines[1].startswith("|")
            assert all(line.startswith("|") and line.endswith("|") for line in lines[2:])


def test_split_markdown_blocks_preserves_table_when_row_structure_cannot_fit():
    headers = [f"H{index}" for index in range(10)]
    header = "| " + " | ".join(headers) + " |\n"
    separator = "| " + " | ".join("---" for _ in headers) + " |\n"
    oversized_row = "| " + " | ".join(["VALUE" * 30, *(["x"] * 9)]) + " |\n"
    table = header + separator + oversized_row

    chunks = split_markdown_blocks(table, 130)

    assert chunks == [table]


def test_split_markdown_blocks_preserves_oversized_table_header():
    table = f"| {'H' * 300} |\n| --- |\n"

    chunks = split_markdown_blocks(table, 120)

    assert chunks == [table]
