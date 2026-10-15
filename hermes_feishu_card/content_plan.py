"""Complete source text and its bounded card-body representation.

The plan never changes canonical session text. Table overflow is an explicit
display policy; native conversion failure retains the corresponding Markdown.
The whole card is still admitted by the shared serializer after rendering.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .native_tables import build_main_content_elements
from .text import TableOverflowResult, split_markdown_blocks, transform_table_overflow


@dataclass(frozen=True, repr=False)
class ContentPlan:
    source_text: str
    table_overflow: TableOverflowResult
    native_tables: bool
    chunk_chars: int

    @property
    def complete(self) -> bool:
        """False only for the user's explicit legacy truncate display policy."""
        return self.table_overflow.truncated_table_count == 0


def plan_main_content(
    text: str, *, table_overflow_mode: str = "compact",
    native_tables: bool = False, chunk_chars: int = 2400,
) -> ContentPlan:
    if type(chunk_chars) is not int or chunk_chars <= 0:
        raise ValueError("content chunk size must be a positive integer")
    return ContentPlan(
        source_text=text,
        table_overflow=transform_table_overflow(text, mode=table_overflow_mode),
        native_tables=native_tables,
        chunk_chars=chunk_chars,
    )


def render_content_plan(
    plan: ContentPlan, *, text_size: str | None = None,
) -> list[dict[str, Any]]:
    """Choose a representation, never a shorter substitute for the answer."""
    text = plan.table_overflow.text
    if plan.native_tables:
        native = build_main_content_elements(
            text, chunk_chars=plan.chunk_chars, text_size=text_size,
        )
        if native is not None:
            return native
    elements: list[dict[str, Any]] = []
    for index, chunk in enumerate(split_markdown_blocks(text, plan.chunk_chars)):
        element: dict[str, Any] = {
            "tag": "markdown",
            "element_id": "main_content" if index == 0 else f"main_content_{index}",
            "content": chunk,
        }
        if text_size is not None:
            element["text_size"] = text_size
        elements.append(element)
    return elements
