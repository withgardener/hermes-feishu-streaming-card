"""Bounded local support reports, reusing the established diagnostic allowlist."""
from __future__ import annotations

from hashlib import sha256
import json
import math
import os
from pathlib import Path
import platform
from typing import Any

from . import __version__
from .diagnostics import redacted_diagnostic_snapshot

MAX_SUPPORT_REPORT_BYTES = 128 * 1024


def build_support_report(source: dict[str, Any]) -> dict[str, Any]:
    """Keep diagnostic facts; omit machine locations and arbitrary raw messages.

    A support report is for manual sharing, so its projection is stricter than
    the local diagnostic card. It contains no raw config, logs, transcript,
    endpoint, command, environment variable or source code.
    """
    snapshot = redacted_diagnostic_snapshot(source)
    snapshot.pop("sidecar", None)
    config = snapshot.get("config")
    if isinstance(config, dict):
        config.pop("server", None)
    routing = snapshot.get("routing")
    if isinstance(routing, dict):
        routing.pop("event_endpoint", None)
    created_at = snapshot.get("created_at")
    if isinstance(created_at, (int, float)) and not math.isfinite(created_at):
        snapshot.pop("created_at", None)
    report: dict[str, Any] = {
        "schema_version": "hfc-support-report-v1",
        "package_version": __version__,
        "python_version": platform.python_version(),
        "platform": platform.system() if platform.system() in {"Darwin", "Linux", "Windows"} else "other",
        "scope": "read_only_diagnostics",
        "excluded": ["config_contents", "logs", "chat_contents", "credentials", "paths", "endpoints"],
        "diagnostics": snapshot,
    }
    canonical = json.dumps(report, sort_keys=True, ensure_ascii=False, allow_nan=False)
    report["report_id"] = sha256(canonical.encode("utf-8")).hexdigest()
    # Reject excess data rather than silently dropping useful failure evidence.
    serialize_support_report(report)
    return report


def serialize_support_report(report: dict[str, Any]) -> str:
    text = json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False) + "\n"
    if len(text.encode("utf-8")) > MAX_SUPPORT_REPORT_BYTES:
        raise ValueError("support report exceeds local export limit")
    return text


def write_support_report(path: Path, source: dict[str, Any]) -> None:
    """Create one private report exclusively; never overwrite another file.

    Rebuild the allowlisted projection here as well as in the preview path so
    callers cannot accidentally export a raw doctor response. On write failure
    retain the private partial file for local inspection; do not unlink a path
    that another process might have replaced.
    """
    contents = serialize_support_report(build_support_report(source))
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(path, flags, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as output:
        output.write(contents)
        output.flush()
        os.fsync(output.fileno())
