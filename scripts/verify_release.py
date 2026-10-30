from __future__ import annotations

import argparse
from pathlib import Path
import re
import subprocess
import sys


_TAG_RE = re.compile(r"^v([0-9]+\.[0-9]+\.[0-9]+)$")
_COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
_MARKERS = {
    "pyproject": (
        "pyproject.toml",
        re.compile(r'^version = "([0-9]+\.[0-9]+\.[0-9]+)"$', re.MULTILINE),
    ),
    "package": (
        "hermes_feishu_card/__init__.py",
        re.compile(
            r'^__version__ = "([0-9]+\.[0-9]+\.[0-9]+)"$',
            re.MULTILINE,
        ),
    ),
    "config": (
        "config.yaml.example",
        re.compile(
            r"^# Hermes Feishu Streaming Card V([0-9]+\.[0-9]+\.[0-9]+) "
            r"sidecar configuration$",
            re.MULTILINE,
        ),
    ),
    "compose": (
        "docker-compose.example.yml",
        re.compile(
            r'^\s*HFC_VERSION: "\$\{HFC_VERSION:-v'
            r'([0-9]+\.[0-9]+\.[0-9]+)\}"$',
            re.MULTILINE,
        ),
    ),
    "ci": (
        ".github/workflows/tests.yml",
        re.compile(
            r"^\s*HFC_VERSION: v([0-9]+\.[0-9]+\.[0-9]+)$",
            re.MULTILINE,
        ),
    ),
}


class ReleaseGateError(ValueError):
    pass


def parse_release_tag(tag: str) -> str:
    match = _TAG_RE.fullmatch(str(tag or ""))
    if match is None:
        raise ReleaseGateError("invalid_tag")
    return match.group(1)


def read_release_markers(root: Path) -> dict[str, str]:
    selected_root = Path(root).resolve(strict=False)
    markers: dict[str, str] = {}
    for name, (relative, pattern) in _MARKERS.items():
        try:
            text = (selected_root / relative).read_text(encoding="utf-8")
        except OSError as exc:
            raise ReleaseGateError("metadata_mismatch") from exc
        matches = pattern.findall(text)
        if len(matches) != 1:
            raise ReleaseGateError("metadata_mismatch")
        markers[name] = matches[0]
    return markers


def resolve_annotated_tag_commit(root: Path, tag: str) -> str:
    parse_release_tag(tag)
    tag_ref = f"refs/tags/{tag}"
    object_type = _git(root, "cat-file", "-t", tag_ref, check=False)
    if object_type.returncode != 0:
        raise ReleaseGateError("tag_missing")
    if object_type.stdout.strip() != "tag":
        raise ReleaseGateError("tag_not_annotated")
    peeled = _git(root, "rev-parse", f"{tag_ref}^{{commit}}", check=False)
    commit = peeled.stdout.strip().lower()
    if peeled.returncode != 0 or _COMMIT_RE.fullmatch(commit) is None:
        raise ReleaseGateError("tag_missing")
    return commit


def verify_release_metadata(root: Path, tag: str) -> None:
    expected_version = parse_release_tag(tag)
    markers = read_release_markers(root)
    if any(value != expected_version for value in markers.values()):
        raise ReleaseGateError("metadata_mismatch")


def verify_release_tag(
    root: Path,
    tag: str,
    expected_commit: str,
    require_main_ancestor: bool,
) -> None:
    verify_release_metadata(root, tag)
    normalized_commit = str(expected_commit or "").lower()
    if _COMMIT_RE.fullmatch(normalized_commit) is None:
        raise ReleaseGateError("expected_commit_invalid")
    head = _git(root, "rev-parse", "HEAD", check=False)
    if head.returncode != 0 or head.stdout.strip().lower() != normalized_commit:
        raise ReleaseGateError("head_mismatch")
    tagged_commit = resolve_annotated_tag_commit(root, tag)
    if tagged_commit != normalized_commit:
        raise ReleaseGateError("tag_commit_mismatch")
    if require_main_ancestor:
        ancestry = _git(
            root,
            "merge-base",
            "--is-ancestor",
            normalized_commit,
            "origin/main",
            check=False,
        )
        if ancestry.returncode != 0:
            raise ReleaseGateError("tag_not_on_main")


def _git(root: Path, *args: str, check: bool) -> subprocess.CompletedProcess[str]:
    selected_root = Path(root).resolve(strict=False)
    try:
        return subprocess.run(
            ["git", "-C", str(selected_root), *args],
            check=check,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        raise ReleaseGateError("tag_missing") from exc


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="verify_release.py")
    parser.add_argument("--tag", required=True)
    parser.add_argument("--expected-commit", default="")
    parser.add_argument("--require-main-ancestor", action="store_true")
    parser.add_argument("--metadata-only", action="store_true")
    args = parser.parse_args(argv)
    root = Path(__file__).resolve().parents[1]
    try:
        if args.metadata_only:
            verify_release_metadata(root, args.tag)
            print(f"release gate ok: {args.tag} metadata")
        else:
            verify_release_tag(
                root,
                args.tag,
                args.expected_commit,
                args.require_main_ancestor,
            )
            print(f"release gate ok: {args.tag} -> {args.expected_commit.lower()}")
    except ReleaseGateError as exc:
        print(f"release gate failed: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
