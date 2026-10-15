"""Bounded Git identity evidence shared by read-only ownership consumers."""
from __future__ import annotations

from pathlib import Path
import re
import subprocess

from .errors import IntegrityRepairRefused

_GIT_HASH_RE = re.compile(r"^[0-9a-f]{40}(?:[0-9a-f]{24})?$")


def _exact_git_root(root: Path) -> Path:
    resolved = root.resolve()
    result = _run_git(resolved, "rev-parse", "--show-toplevel")
    try:
        toplevel = Path(result.stdout.decode("utf-8").strip()).resolve()
    except UnicodeError as exc:
        raise IntegrityRepairRefused("git_root_invalid") from exc
    if toplevel != resolved:
        raise IntegrityRepairRefused("git_root_invalid")
    return resolved


def _git_head(root: Path) -> str:
    result = _run_git(root, "rev-parse", "HEAD")
    head = result.stdout.decode("ascii", errors="ignore").strip().lower()
    if _GIT_HASH_RE.fullmatch(head) is None:
        raise IntegrityRepairRefused("git_head_invalid")
    return head


def _is_ancestor(root: Path, ancestor: str, descendant: str) -> bool:
    result = subprocess.run(
        ["git", "-C", str(root), "merge-base", "--is-ancestor", ancestor, descendant],
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        timeout=5,
    )
    if result.returncode not in {0, 1}:
        raise IntegrityRepairRefused("git_history_unavailable")
    return result.returncode == 0


def _git_blob(root: Path, revision: str, relative: str) -> str:
    result = _run_git(root, "show", f"{revision}:{relative}")
    try:
        return result.stdout.decode("utf-8")
    except UnicodeError as exc:
        raise IntegrityRepairRefused("git_blob_invalid") from exc


def _git_target_status(root: Path, relative: str) -> str:
    result = _run_git(
        root,
        "status",
        "--porcelain=v1",
        "--untracked-files=no",
        "--",
        relative,
    )
    return result.stdout.decode("utf-8", errors="replace").strip()


def _run_git(root: Path, *args: str) -> subprocess.CompletedProcess[bytes]:
    try:
        result = subprocess.run(
            ["git", "-C", str(root), *args],
            check=False,
            capture_output=True,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise IntegrityRepairRefused("git_evidence_unavailable") from exc
    if result.returncode != 0:
        raise IntegrityRepairRefused("git_evidence_unavailable")
    return result


