"""Bounded per-turn display metrics from official lifecycle observations.

No response text, credentials, execution ownership or token estimates are kept.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from math import isfinite
import re


_LABEL = re.compile(r"[A-Za-z0-9_./:+-]{1,192}\Z")


def metric_count(value: object) -> int | None:
    return value if type(value) is int and 0 <= value <= 2**63 - 1 else None


def metric_label(value: object) -> str:
    if type(value) is not str or not _LABEL.fullmatch(value) or "://" in value:
        return ""
    return value


@dataclass
class TurnMetrics:
    started_at: float
    model: str = ""
    provider: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    has_usage: bool = False
    usage_complete: bool = True
    context_used: int | None = None
    context_limit: int | None = None
    request_ids: set[str] = field(default_factory=set, repr=False)

    def observe_api(self, values: dict[str, object]) -> None:
        request_id = values.get("api_request_id")
        if type(request_id) is not str or not 0 < len(request_id) <= 256 or not request_id.strip():
            self.usage_complete = False
            self.context_used = None
            return
        if request_id in self.request_ids:
            return
        if len(self.request_ids) >= 256:
            self.usage_complete = False
            self.context_used = None
            return
        self.request_ids.add(request_id)
        self.context_used = None
        model = metric_label(values.get("response_model")) or metric_label(values.get("model"))
        if model:
            self.model = model
            self.provider = metric_label(values.get("provider"))
        usage = values.get("usage")
        if type(usage) is not dict:
            self.usage_complete = False
            return
        prompt = metric_count(usage.get("prompt_tokens"))
        if prompt is None:
            base = metric_count(usage.get("input_tokens"))
            read = metric_count(usage.get("cache_read_tokens", 0))
            write = metric_count(usage.get("cache_write_tokens", 0))
            if base is not None and read is not None and write is not None:
                prompt = metric_count(base + read + write)
        output = metric_count(usage.get("output_tokens"))
        if prompt is not None:
            self.context_used = prompt
        if prompt is None or output is None:
            self.usage_complete = False
            return
        total_input = metric_count(self.input_tokens + prompt)
        total_output = metric_count(self.output_tokens + output)
        if total_input is None or total_output is None:
            self.usage_complete = False
            return
        self.input_tokens, self.output_tokens = total_input, total_output
        self.has_usage = True

    def payload(self, now: float) -> dict[str, object]:
        result: dict[str, object] = {}
        if self.model:
            result["model"] = self.model
        if self.provider:
            result["provider"] = self.provider
        duration = now - self.started_at
        if isfinite(duration) and duration >= 0:
            result["duration"] = duration
        if self.has_usage and self.usage_complete:
            result["tokens"] = {"input_tokens": self.input_tokens, "output_tokens": self.output_tokens}
        context = {}
        if self.context_used is not None:
            context["used_tokens"] = self.context_used
        if self.context_limit is not None and self.context_limit > 0:
            context["max_tokens"] = self.context_limit
        if context:
            result["context"] = context
        return result
