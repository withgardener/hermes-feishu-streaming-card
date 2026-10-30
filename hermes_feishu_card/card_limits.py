from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import json
from typing import Any

from .text import count_markdown_tables


FEISHU_MAX_TABLES = 5
FEISHU_MAX_ELEMENTS = 200
SAFE_CARD_JSON_BYTES = 28_000


class CardLimitExceeded(ValueError):
    def __init__(self, violations: tuple[str, ...]):
        self.violations = violations
        reasons = ",".join(violations) or "unknown"
        super().__init__(f"card exceeds safe Feishu limits: {reasons}")


@dataclass(frozen=True)
class CardLimitInspection:
    json_bytes: int
    element_count: int
    table_count: int
    violations: tuple[str, ...]

    @property
    def safe(self) -> bool:
        return not self.violations

    @property
    def primary_reason(self) -> str:
        return self.violations[0] if self.violations else ""


def serialize_card_json(card: Mapping[str, Any]) -> str:
    """Serialize exactly as Feishu send/update does."""
    return json.dumps(card, ensure_ascii=False)


def inspect_card_limits(card: Mapping[str, Any]) -> CardLimitInspection:
    serialized = serialize_card_json(card)
    element_count, table_count = _count_card_nodes(card)
    json_bytes = len(serialized.encode("utf-8"))
    violations: list[str] = []
    if json_bytes > SAFE_CARD_JSON_BYTES:
        violations.append("json_bytes")
    if element_count > FEISHU_MAX_ELEMENTS:
        violations.append("elements")
    if table_count > FEISHU_MAX_TABLES:
        violations.append("tables")
    return CardLimitInspection(
        json_bytes=json_bytes,
        element_count=element_count,
        table_count=table_count,
        violations=tuple(violations),
    )


def serialize_card_for_delivery(card: Mapping[str, Any]) -> str:
    inspection = inspect_card_limits(card)
    if not inspection.safe:
        raise CardLimitExceeded(inspection.violations)
    return serialize_card_json(card)


def _count_card_nodes(value: Any) -> tuple[int, int]:
    element_count = 0
    table_count = 0
    if isinstance(value, Mapping):
        tag = value.get("tag")
        if isinstance(tag, str):
            element_count += 1
            if tag == "table":
                table_count += 1
            elif tag == "markdown":
                content = value.get("content")
                if isinstance(content, str):
                    table_count += count_markdown_tables(content)
        for nested in value.values():
            nested_elements, nested_tables = _count_card_nodes(nested)
            element_count += nested_elements
            table_count += nested_tables
    elif isinstance(value, Sequence) and not isinstance(
        value, (str, bytes, bytearray)
    ):
        for nested in value:
            nested_elements, nested_tables = _count_card_nodes(nested)
            element_count += nested_elements
            table_count += nested_tables
    return element_count, table_count
