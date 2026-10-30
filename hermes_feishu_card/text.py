from __future__ import annotations

from dataclasses import dataclass
import re

THINK_TAG_RE = re.compile(r"</?think>|</?thinking>", re.IGNORECASE)
SENTENCE_END_RE = re.compile(r"[。！？!?\.]$")
THINK_TAGS = ("<think>", "</think>", "<thinking>", "</thinking>")
FENCE_RE = re.compile(r"^(?P<indent> {0,3})(?P<marker>`{3,}|~{3,})(?P<info>.*)$")
LIST_BOUNDARY_RE = re.compile(r"\n(?:[-*]|\d+\.) ")
TABLE_SEPARATOR_CELL_RE = re.compile(r"^:?-{3,}:?$")

MAX_CARD_TABLES = 5
TABLE_COMPACT_NOTE = (
    "> 后续表格已转换为紧凑字段列表，以兼容飞书卡片限制；内容完整保留。"
)
TABLE_TRUNCATE_NOTE = "> 内容含超过 5 个表格，超出部分已省略。"


@dataclass(frozen=True)
class MarkdownTable:
    headers: tuple[str, ...]
    rows: tuple[tuple[str, ...], ...]
    raw: str


@dataclass(frozen=True)
class MarkdownBlock:
    kind: str
    text: str
    start: int
    end: int
    table: MarkdownTable | None = None


@dataclass(frozen=True)
class TableOverflowResult:
    text: str
    source_table_count: int
    compacted_table_count: int = 0
    truncated_table_count: int = 0


def normalize_stream_text(text: str) -> str:
    """移除模型 thinking 标签，保留用户可读内容。"""
    return THINK_TAG_RE.sub("", text or "")


class StreamingTextNormalizer:
    """Filter thinking tags that may be split across streaming chunks."""

    def __init__(self) -> None:
        self._pending = ""

    def feed(self, delta: str) -> str:
        text = self._pending + (delta or "")
        safe_text, self._pending = self._split_safe_text(text)
        return normalize_stream_text(safe_text)

    @staticmethod
    def _split_safe_text(text: str) -> tuple[str, str]:
        lower_text = text.lower()
        pending_len = 0

        for tag in THINK_TAGS:
            for prefix_len in range(1, len(tag)):
                if lower_text.endswith(tag[:prefix_len]):
                    pending_len = max(pending_len, prefix_len)

        if not pending_len:
            return text, ""
        return text[:-pending_len], text[-pending_len:]


def should_flush_text(
    buffer: str,
    *,
    elapsed_ms: int,
    max_wait_ms: int,
    max_chars: int,
    force: bool = False,
) -> bool:
    if force:
        return True
    if not buffer:
        return False
    if len(buffer) >= max_chars:
        return True
    if elapsed_ms >= max_wait_ms:
        return True
    if buffer.endswith(("\n", "\r\n")):
        return True
    return bool(SENTENCE_END_RE.search(buffer.rstrip()))


def count_markdown_tables(text: str) -> int:
    """Count real Markdown tables outside fenced code blocks."""
    source = text or ""
    # The row parser requires a literal pipe delimiter. Avoid allocating and
    # scanning block/row objects for the common plain-text and code-only case.
    if "|" not in source:
        return 0
    return sum(block.kind == "table" for block in scan_markdown_blocks(source))


def scan_markdown_blocks(text: str) -> list[MarkdownBlock]:
    """Scan plain, fenced-code, and Markdown-table blocks without data loss."""
    if not text:
        return [MarkdownBlock(kind="plain", text="", start=0, end=0)]

    lines = text.splitlines(keepends=True)
    offsets: list[int] = []
    cursor = 0
    for line in lines:
        offsets.append(cursor)
        cursor += len(line)

    blocks: list[MarkdownBlock] = []
    paragraph: list[str] = []
    paragraph_start = 0

    def flush_paragraph(end: int) -> None:
        nonlocal paragraph
        if paragraph:
            blocks.append(
                MarkdownBlock(
                    kind="plain",
                    text="".join(paragraph),
                    start=paragraph_start,
                    end=end,
                )
            )
            paragraph = []

    index = 0
    while index < len(lines):
        line = lines[index]
        opening = _fence_opening(line)
        if opening is not None:
            flush_paragraph(offsets[index])
            fence_start = offsets[index]
            fence_lines = [line]
            marker_char, marker_size = opening
            index += 1
            while index < len(lines):
                candidate = lines[index]
                fence_lines.append(candidate)
                index += 1
                if _is_fence_closing(candidate, marker_char, marker_size):
                    break
            fence_text = "".join(fence_lines)
            blocks.append(
                MarkdownBlock(
                    kind="fence",
                    text=fence_text,
                    start=fence_start,
                    end=fence_start + len(fence_text),
                )
            )
            continue

        if index + 1 < len(lines):
            headers = _parse_markdown_row(line.rstrip("\r\n"))
            separator = _parse_table_separator(lines[index + 1].rstrip("\r\n"))
            if (
                headers is not None
                and separator is not None
                and len(headers) == len(separator)
            ):
                flush_paragraph(offsets[index])
                table_start = offsets[index]
                table_lines = [line, lines[index + 1]]
                rows: list[tuple[str, ...]] = []
                index += 2
                while index < len(lines):
                    row = _parse_markdown_row(lines[index].rstrip("\r\n"))
                    if row is None:
                        break
                    table_lines.append(lines[index])
                    rows.append(tuple(row))
                    index += 1
                table_text = "".join(table_lines)
                blocks.append(
                    MarkdownBlock(
                        kind="table",
                        text=table_text,
                        start=table_start,
                        end=table_start + len(table_text),
                        table=MarkdownTable(
                            headers=tuple(headers),
                            rows=tuple(rows),
                            raw=table_text,
                        ),
                    )
                )
                continue

        if not paragraph:
            paragraph_start = offsets[index]
        paragraph.append(line)
        index += 1
        if line.strip() == "":
            flush_paragraph(offsets[index - 1] + len(line))

    flush_paragraph(len(text))
    return blocks or [MarkdownBlock(kind="plain", text=text, start=0, end=len(text))]


def transform_table_overflow(
    text: str,
    *,
    mode: str = "compact",
    max_tables: int = MAX_CARD_TABLES,
) -> TableOverflowResult:
    """Compact or remove overflow table blocks while retaining surrounding prose."""
    normalized_mode = str(mode or "").strip().lower()
    if normalized_mode not in {"compact", "truncate"}:
        raise ValueError("table overflow mode must be compact or truncate")
    blocks = scan_markdown_blocks(text or "")
    table_count = sum(block.kind == "table" for block in blocks)
    overflow_count = max(0, table_count - max(0, max_tables))
    if overflow_count == 0:
        return TableOverflowResult(text=text or "", source_table_count=table_count)

    transformed: list[str] = []
    table_index = 0
    note_written = False
    for block in blocks:
        if block.kind != "table":
            transformed.append(block.text)
            continue
        table_index += 1
        if table_index <= max_tables:
            transformed.append(block.text)
            continue
        if not note_written:
            note = (
                TABLE_COMPACT_NOTE
                if normalized_mode == "compact"
                else TABLE_TRUNCATE_NOTE
            )
            transformed.append(note + "\n\n")
            note_written = True
        if normalized_mode == "compact" and block.table is not None:
            transformed.append(_compact_table(block.table, table_index))

    return TableOverflowResult(
        text="".join(transformed),
        source_table_count=table_count,
        compacted_table_count=(
            overflow_count if normalized_mode == "compact" else 0
        ),
        truncated_table_count=(
            overflow_count if normalized_mode == "truncate" else 0
        ),
    )


def _compact_table(table: MarkdownTable, table_index: int) -> str:
    column_count = max(
        [len(table.headers), *(len(row) for row in table.rows)],
        default=len(table.headers),
    )
    headers = _stable_table_headers(table.headers, column_count)
    if not table.rows:
        return (
            f"**Table {table_index}**\n"
            f"- Columns: {', '.join(headers)}\n"
            "- Rows: （空）\n\n"
        )
    sections: list[str] = []
    for row_index, row in enumerate(table.rows, start=1):
        fields = [
            f"- {headers[cell_index]}: {cell}"
            for cell_index, cell in enumerate(row)
        ]
        sections.append(
            f"**Table {table_index} · Row {row_index}**\n"
            + "\n".join(fields)
        )
    return "\n\n".join(sections) + "\n\n"


def _stable_table_headers(headers: tuple[str, ...], column_count: int) -> list[str]:
    occurrences: dict[str, int] = {}
    result: list[str] = []
    for index in range(column_count):
        raw = headers[index].strip() if index < len(headers) else ""
        base = raw or f"Column {index + 1}"
        occurrences[base] = occurrences.get(base, 0) + 1
        occurrence = occurrences[base]
        result.append(base if occurrence == 1 else f"{base} ({occurrence})")
    return result


def split_markdown_blocks(text: str, max_block_size: int) -> list[str]:
    """Split markdown without cutting tables or fenced code blocks in half."""
    if not text:
        return [""]
    if max_block_size <= 0 or len(text) <= max_block_size:
        return [text]

    blocks = _markdown_structure_blocks(text)
    chunks: list[str] = []
    current = ""
    for block in blocks:
        if len(block) > max_block_size and _is_fenced_code_block(block):
            if current:
                chunks.append(current)
                current = ""
            chunks.extend(_split_fenced_code_block(block, max_block_size))
            continue

        if len(block) > max_block_size and _is_table_block(block):
            if current:
                chunks.append(current)
                current = ""
            chunks.extend(_split_table_block(block, max_block_size))
            continue

        if len(block) > max_block_size and not _is_structured_markdown_block(block):
            if current:
                chunks.append(current)
                current = ""
            chunks.extend(_split_plain_block(block, max_block_size))
            continue

        if current and len(current) + len(block) > max_block_size:
            chunks.append(current)
            current = block
        else:
            current += block

    if current:
        chunks.append(current)
    return chunks or [""]


def _markdown_structure_blocks(text: str) -> list[str]:
    return [block.text for block in scan_markdown_blocks(text)]


def _is_structured_markdown_block(block: str) -> bool:
    return any(
        candidate.kind in {"fence", "table"}
        for candidate in scan_markdown_blocks(block)
    )


def _is_fenced_code_block(block: str) -> bool:
    lines = block.splitlines(keepends=True)
    return bool(lines) and _fence_opening(lines[0]) is not None


def _is_table_block(block: str) -> bool:
    candidates = scan_markdown_blocks(block)
    return len(candidates) == 1 and candidates[0].kind == "table"


def _fence_opening(line: str) -> tuple[str, int] | None:
    match = FENCE_RE.match(line.rstrip("\r\n"))
    if match is None:
        return None
    marker = match.group("marker")
    return marker[0], len(marker)


def _is_fence_closing(line: str, marker_char: str, marker_size: int) -> bool:
    stripped = line.rstrip("\r\n")
    return re.fullmatch(
        rf" {{0,3}}{re.escape(marker_char)}{{{marker_size},}}\s*", stripped
    ) is not None


def _parse_table_separator(row: str) -> list[str] | None:
    cells = _parse_markdown_row(row)
    if cells is None or not cells:
        return None
    if not all(TABLE_SEPARATOR_CELL_RE.fullmatch(cell.strip()) for cell in cells):
        return None
    return cells


def _split_fenced_code_block(block: str, max_block_size: int) -> list[str]:
    lines = block.splitlines(keepends=True)
    if len(lines) < 2:
        return _split_plain_block(block, max_block_size)
    opening = lines[0]
    opening_fence = _fence_opening(opening)
    if opening_fence is None:
        return _split_plain_block(block, max_block_size)
    marker_char, marker_size = opening_fence
    default_closing = marker_char * marker_size + "\n"
    closing = (
        lines[-1]
        if _is_fence_closing(lines[-1], marker_char, marker_size)
        else default_closing
    )
    body_lines = lines[1:-1] if closing == lines[-1] else lines[1:]
    overhead = len(opening) + len(closing)
    if overhead >= max_block_size:
        return _split_plain_block(block, max_block_size)
    body_limit = max_block_size - overhead
    chunks: list[str] = []
    current = ""
    for line in body_lines:
        if current and len(current) + len(line) > body_limit:
            chunks.append(_wrap_code_chunk(opening, current, closing))
            current = ""
        if len(line) > body_limit:
            for piece in _split_plain_block(line, body_limit):
                chunks.append(_wrap_code_chunk(opening, piece, closing))
            continue
        current += line
    if current or not chunks:
        chunks.append(_wrap_code_chunk(opening, current, closing))
    return chunks


def _wrap_code_chunk(opening: str, body: str, closing: str) -> str:
    if body and not body.endswith("\n"):
        body += "\n"
    return opening + body + closing


def _split_table_block(block: str, max_block_size: int) -> list[str]:
    lines = block.splitlines(keepends=True)
    if len(lines) < 2:
        return _split_plain_block(block, max_block_size)
    header = "".join(lines[:2])
    if len(header) >= max_block_size:
        # The chunk target is not a license to discard an answer. Preserve an
        # indivisible table and let the final card budget trigger full handoff.
        return [block]
    if len(lines) == 2:
        return [block]
    rows = lines[2:]
    row_limit = max_block_size - len(header)
    chunks: list[str] = []
    current = ""
    for row in rows:
        if current and len(current) + len(row) > row_limit:
            chunks.append(header + current)
            current = ""
        if len(row) > row_limit:
            if current:
                chunks.append(header + current)
                current = ""
            split_rows = _split_oversized_table_row(row, row_limit)
            if split_rows is None:
                return [block]
            else:
                chunks.extend(header + piece for piece in split_rows)
            continue
        current += row
    if current or not chunks:
        chunks.append(header + current)
    return chunks


def _split_oversized_table_row(row: str, max_row_size: int) -> list[str] | None:
    row_text = row.rstrip("\n")
    cells = _parse_markdown_row(row_text)
    if not cells:
        return None
    split_index = max(range(len(cells)), key=lambda index: len(cells[index]))
    first_template = list(cells)
    first_template[split_index] = ""
    continuation_template = ["" for _ in cells]
    continuation_template[split_index] = ""
    first_capacity = max_row_size - len(_format_markdown_row(first_template))
    continuation_capacity = max_row_size - len(_format_markdown_row(continuation_template))
    if first_capacity <= 0 or continuation_capacity <= 0:
        return None

    parts: list[str] = []
    remaining = cells[split_index]
    first_row = True
    while remaining:
        capacity = first_capacity if first_row else continuation_capacity
        piece, remaining = _take_plain_piece(remaining, capacity)
        row_cells = list(cells) if first_row else ["" for _ in cells]
        row_cells[split_index] = piece.strip()
        parts.append(_format_markdown_row(row_cells))
        first_row = False
    return parts or None


def _parse_markdown_row(row: str) -> list[str] | None:
    stripped = row.strip()
    if not stripped or "|" not in stripped:
        return None
    cells: list[str] = []
    current: list[str] = []
    delimiter_count = 0
    inline_code_size = 0
    index = 0
    while index < len(stripped):
        char = stripped[index]
        if char == "\\" and index + 1 < len(stripped):
            current.append(char)
            current.append(stripped[index + 1])
            index += 2
            continue
        if char == "`":
            run_end = index + 1
            while run_end < len(stripped) and stripped[run_end] == "`":
                run_end += 1
            run_size = run_end - index
            current.append(stripped[index:run_end])
            if inline_code_size == 0:
                inline_code_size = run_size
            elif inline_code_size == run_size:
                inline_code_size = 0
            index = run_end
            continue
        if char == "|" and inline_code_size == 0:
            cells.append("".join(current).strip())
            current = []
            delimiter_count += 1
            index += 1
            continue
        current.append(char)
        index += 1
    cells.append("".join(current).strip())
    if delimiter_count == 0:
        return None
    if stripped.startswith("|"):
        cells = cells[1:]
    if stripped.endswith("|") and cells:
        cells = cells[:-1]
    return cells or None


def _format_markdown_row(cells: list[str], trailing_newline: bool = True) -> str:
    row = "| " + " | ".join(cell.strip() for cell in cells) + " |"
    if trailing_newline:
        row += "\n"
    return row


def _take_plain_piece(text: str, max_size: int) -> tuple[str, str]:
    if len(text) <= max_size:
        return text, ""
    split_at = _safe_plain_split_index(text, max_size)
    piece = text[:split_at].rstrip()
    remaining = text[split_at:].lstrip()
    if not piece:
        piece = text[:max_size]
        remaining = text[max_size:]
    return piece, remaining


def _split_plain_block(block: str, max_block_size: int) -> list[str]:
    chunks: list[str] = []
    remaining = block
    while len(remaining) > max_block_size:
        split_at = _safe_plain_split_index(remaining, max_block_size)
        chunks.append(remaining[:split_at])
        remaining = remaining[split_at:]
    if remaining:
        chunks.append(remaining)
    return chunks


def _safe_plain_split_index(text: str, max_block_size: int) -> int:
    window = text[: max_block_size + 1]
    candidate_groups = (
        sorted({match.start() + 1 for match in LIST_BOUNDARY_RE.finditer(window)}, reverse=True),
        [_separator_split_index(window, "\n")],
        [_separator_split_index(window, " ")],
    )
    for candidates in candidate_groups:
        for split_at in candidates:
            if split_at <= 0:
                continue
            safe_split = _adjust_split_for_inline_code(window, split_at)
            if safe_split > 0:
                return safe_split
    return max_block_size


def _separator_split_index(text: str, separator: str) -> int:
    index = text.rfind(separator)
    if index <= 0:
        return 0
    return index + len(separator)


def _adjust_split_for_inline_code(text: str, split_at: int) -> int:
    prefix = text[:split_at]
    if prefix.count("`") % 2 == 0:
        return split_at
    before_code = text.rfind("`", 0, split_at)
    while before_code > 0:
        if text[:before_code].count("`") % 2 == 0:
            return before_code
        before_code = text.rfind("`", 0, before_code)
    return 0
