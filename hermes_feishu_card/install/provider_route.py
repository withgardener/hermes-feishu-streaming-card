"""Optional, reversible capture at Hermes' actual agent-result construction.

LOCAL PATCH (PATCH-038): the capture has to follow the result dict when Hermes
moves it. v0.22.5 split ``TurnRunner.run_sync`` and left the ``usage = {...}``
construction in the extracted ``TurnRunner._run_sync_scoped`` body, so a
validator that only accepted ``run_sync``/``_run_agent_inner`` found no
candidate, returned the source unchanged, and let the card footer fall back to
the runtime provider bucket (``custom/CLAUDE/Sonnet-5.5``) instead of the named
channel (``OKHEMA/CLAUDE/Sonnet-5.5``).

``RESULT_BUILDING_FUNCTIONS`` is the complete set of result-building functions
this deployment has seen. The predicate itself stays strict: exactly one
candidate with the exact upstream ``model`` expression, otherwise the source is
returned untouched. Silence there is not acceptance — the marker is a declared
decomposed anchor (``patcher.DECOMPOSED_LAYOUT_MARKERS``), so a tree where the
capture cannot be placed fails the install/doctor anchor check instead of
degrading the footer quietly.
"""
from __future__ import annotations

import ast
import re

# LOCAL PATCH (PATCH-038): v0.22.2 = run_sync, older = _run_agent_inner,
# v0.22.5+ = _run_sync_scoped (run_sync delegates to it).
RESULT_BUILDING_FUNCTIONS = frozenset({"run_sync", "_run_agent_inner", "_run_sync_scoped"})

PROVIDER_USAGE_BEGIN = "# HERMES_FEISHU_CARD_PROVIDER_USAGE_BEGIN"
PROVIDER_USAGE_END = "# HERMES_FEISHU_CARD_PROVIDER_USAGE_END"
PROVIDER_RESOLVED_BEGIN = "# HERMES_FEISHU_CARD_PROVIDER_RESOLVED_BEGIN"
PROVIDER_RESOLVED_END = "# HERMES_FEISHU_CARD_PROVIDER_RESOLVED_END"

OWNED_MARKERS = (
    (PROVIDER_USAGE_BEGIN, PROVIDER_USAGE_END),
    (PROVIDER_RESOLVED_BEGIN, PROVIDER_RESOLVED_END),
)

_MODEL_EXPRESSION = ('getattr(agent, "model", None) if agent else None', "USAGE")
_RESOLVED_EXPRESSION = ('getattr(_agent, "model", None) if _agent else None', "RESOLVED")


def _marker(mode: str, edge: str) -> str:
    return f"# HERMES_FEISHU_CARD_PROVIDER_{mode}_{edge}"


def _block(indent: str, newline: str, mode: str) -> str:
    target, agent = ("usage[\"model\"]", "agent") if mode == "USAGE" else ("_resolved_model", "_agent")
    return newline.join([
        f"{indent}{_marker(mode, 'BEGIN')}",
        f"{indent}try:",
        f"{indent}    from hermes_feishu_card.hook_runtime import effective_response_model as _hfc_effective_model",
        f"{indent}    {target} = _hfc_effective_model({agent}) or {target}",
        f"{indent}except Exception:",
        f"{indent}    pass",
        f"{indent}{_marker(mode, 'END')}",
        "",
    ])


def remove_provider_route_patch(content: str) -> str:
    for mode in ("USAGE", "RESOLVED"):
        begin = _marker(mode, "BEGIN")
        end = _marker(mode, "END")
        if begin not in content and end not in content:
            continue
        lines = content.splitlines(keepends=True)
        starts = [i for i, line in enumerate(lines) if line.strip() == begin]
        ends = [i for i, line in enumerate(lines) if line.strip() == end]
        if len(starts) != 1 or len(ends) != 1 or ends[0] < starts[0]:
            raise ValueError("corrupt provider route patch markers")
        a, b = starts[0], ends[0]
        indent = re.match(r"[ \t]*", lines[a]).group()
        newline = "\r\n" if lines[a].endswith("\r\n") else "\n"
        if "".join(lines[a:b + 1]) != _block(indent, newline, mode):
            raise ValueError("modified provider route patch")
        content = "".join(lines[:a] + lines[b + 1:])
    return content


def _candidates(content: str) -> list[tuple[ast.AST, str]]:
    tree = ast.parse(content)
    candidates: list[tuple[ast.AST, str]] = []
    for owner in ast.walk(tree):
        if (not isinstance(owner, (ast.FunctionDef, ast.AsyncFunctionDef))
                or owner.name not in RESULT_BUILDING_FUNCTIONS):
            continue
        for node in owner.body:
            if not isinstance(node, ast.Assign) or len(node.targets) != 1 or not isinstance(node.targets[0], ast.Name):
                continue
            name = node.targets[0].id
            if name == "_resolved_model":
                if ast.dump(node.value) == ast.dump(ast.parse(_RESOLVED_EXPRESSION[0], mode="eval").body):
                    candidates.append((node, "RESOLVED"))
            elif name == "usage" and isinstance(node.value, ast.Dict):
                for key, value in zip(node.value.keys, node.value.values):
                    if (isinstance(key, ast.Constant) and key.value == "model"
                            and ast.dump(value) == ast.dump(ast.parse(_MODEL_EXPRESSION[0], mode="eval").body)):
                        candidates.append((node, "USAGE"))
    return candidates


def provider_route_location(content: str) -> tuple[int, str] | None:
    """(1-based line to insert AFTER, mode) for this source, or None if ambiguous/unknown."""
    clean = remove_provider_route_patch(content)
    candidates = _candidates(clean)
    if len(candidates) != 1:
        return None  # Older/unknown result shape: do not invent provenance.
    node, mode = candidates[0]
    lines = clean.splitlines(keepends=True)
    if not lines[node.end_lineno - 1].endswith(("\n", "\r")):
        return None
    return node.end_lineno, mode


def has_provider_route_capture(content: str) -> bool:
    """True only when the capture can be rendered into exactly this source."""
    try:
        return provider_route_location(content) is not None
    except (SyntaxError, ValueError):
        return False


def apply_provider_route_patch(content: str) -> str:
    clean = remove_provider_route_patch(content)
    located = provider_route_location(clean)
    if located is None:
        return clean
    index, mode = located
    lines = clean.splitlines(keepends=True)
    indent = re.match(r"[ \t]*", lines[index - 1]).group()
    newline = "\r\n" if lines[index - 1].endswith("\r\n") else "\n"
    return "".join(lines[:index]) + _block(indent, newline, mode) + "".join(lines[index:])
