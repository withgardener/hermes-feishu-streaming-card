"""Cron delivery source locations, independent of owned-block rendering.

Keep the established top-level/class and media-filter priority. The patcher
continues to own marker integrity, generation, application and removal.
"""
from __future__ import annotations

import ast
from typing import cast

from .ast_contracts import _body_location, _line_indent


_CRON_DELIVER_NAME = "_deliver_result"


def find_cron_deliver_body_location(tree: ast.Module, lines: list[str]) -> tuple[int, str] | None:
    node = _find_cron_deliver_node(tree)
    return _body_location(node, lines) if node is not None else None


def find_cron_media_delivery_location(tree: ast.Module, lines: list[str]) -> tuple[int, str] | None:
    node = _find_cron_deliver_node(tree)
    if node is None:
        return None

    extract_assignment = None
    filter_assignment = None
    for statement in node.body:
        if not isinstance(statement, ast.Assign):
            continue
        if _assigns_media_and_cleaned_content(statement):
            extract_assignment = statement
        if _assigns_filtered_media_files(statement):
            filter_assignment = statement
    target = filter_assignment or extract_assignment
    if target is None or target.lineno is None:
        return None
    end_lineno = getattr(target, "end_lineno", None) or target.lineno
    return end_lineno, _line_indent(lines, target.lineno - 1)


def _find_cron_deliver_node(tree: ast.Module) -> ast.FunctionDef | None:
    for node in tree.body:
        if _is_cron_deliver(node):
            return cast(ast.FunctionDef, node)
    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            for child in node.body:
                if _is_cron_deliver(child):
                    return cast(ast.FunctionDef, child)
    return None


def _assigns_media_and_cleaned_content(statement: ast.Assign) -> bool:
    names = {
        element.id
        for target in statement.targets
        if isinstance(target, (ast.Tuple, ast.List))
        for element in target.elts
        if isinstance(element, ast.Name)
    }
    if not {"media_files", "cleaned_delivery_content"}.issubset(names):
        return False
    value = statement.value
    return (
        isinstance(value, ast.Call)
        and isinstance(value.func, ast.Attribute)
        and value.func.attr == "extract_media"
    )


def _assigns_filtered_media_files(statement: ast.Assign) -> bool:
    if not any(
        isinstance(target, ast.Name) and target.id == "media_files"
        for target in statement.targets
    ):
        return False
    value = statement.value
    return (
        isinstance(value, ast.Call)
        and isinstance(value.func, ast.Attribute)
        and value.func.attr == "filter_media_delivery_paths"
    )


def _is_cron_deliver(node: ast.AST) -> bool:
    return isinstance(node, ast.FunctionDef) and node.name == _CRON_DELIVER_NAME

