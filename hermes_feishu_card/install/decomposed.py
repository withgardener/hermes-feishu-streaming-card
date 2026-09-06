"""Legacy-patch ownership for Hermes' September facade decomposition.

Mode selection stays in the CLI. This module owns only a verified source set;
all filesystem mutations reuse recovery's bound, rollback-capable transaction.
"""
from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
import stat

from . import patcher

MANIFEST_VERSION = 4
MANIFEST_NAME = ".hermes_feishu_card_manifest"
BACKUP_SUFFIX = ".hermes_feishu_card.bak"
SOURCE_TARGETS = ("gateway/run.py", *patcher.DECOMPOSED_GATEWAY_TARGETS,
                  "cron/scheduler.py", "cron/scheduler_delivery.py", "gateway/platforms/base.py")
SOURCE_TARGET_SET = frozenset(SOURCE_TARGETS)
VERSION_TARGETS = ("VERSION", "hermes_cli/__init__.py", ".git/HEAD", ".git/packed-refs")
LAYOUT_STRATEGY = "modern_split_gateway"


def _patch_groups_for_target(target: str, rendered: bytes) -> tuple[str, ...]:
    from .detect import _LAYOUT_MARKERS
    groups = [name for name, marker in _LAYOUT_MARKERS.items()
              if marker.encode("utf-8") in rendered]
    if patcher.CRON_PATCH_BEGIN.encode("utf-8") in rendered:
        groups.append("cron_delivery")
    if patcher.EXACT_BASE_NO_TEXT_PATCH_BEGIN.encode("utf-8") in rendered:
        groups.append("exact_base_no_text")
    if patcher.EXACT_BASE_FINAL_DELIVERY_PATCH_BEGIN.encode("utf-8") in rendered:
        groups.append("exact_base_final_delivery")
    if not groups:
        groups.append("source_ownership")
    return tuple(sorted(set(groups)))


def is_managed(root: Path) -> bool:
    try:
        value = json.loads((root / MANIFEST_NAME).read_bytes())
        return isinstance(value, dict) and value.get("manifest_version") == MANIFEST_VERSION
    except (OSError, ValueError):
        return False


def validate_manifest(manifest):
    from .manifest import ManifestStructureError
    if (not isinstance(manifest, dict)
            or type(manifest.get("manifest_version")) is not int
            or manifest.get("manifest_version") != MANIFEST_VERSION
            or manifest.get("layout") != "gateway-decomposed-v1"
            or manifest.get("integration_mode") != "legacy-patch"
            or not isinstance(manifest.get("targets"), dict)
            or set(manifest["targets"]) != SOURCE_TARGET_SET):
        raise ManifestStructureError("invalid decomposed ownership manifest")
    for target, row in manifest["targets"].items():
        if (not isinstance(row, dict)
                or set(row) != {"path", "backup", "original_sha256", "patched_sha256",
                                "patch_groups", "layout_strategy"}
                or row["path"] != target
                or row["backup"] != target + BACKUP_SUFFIX
                or row["layout_strategy"] != LAYOUT_STRATEGY
                or not isinstance(row["patch_groups"], list)
                or not row["patch_groups"]
                or any(not isinstance(group, str) or not group for group in row["patch_groups"])
                or any(not isinstance(row[k], str) or len(row[k]) != 64
                       or any(c not in "0123456789abcdef" for c in row[k])
                       for k in ("original_sha256", "patched_sha256"))):
            raise ManifestStructureError("invalid decomposed target ownership")


def _snapshot(root):
    """Bind every candidate, including absence, so a new file invalidates a plan."""
    result = {}
    for name in (*SOURCE_TARGETS, *(n + BACKUP_SUFFIX for n in SOURCE_TARGETS),
                 MANIFEST_NAME, *VERSION_TARGETS):
        path = root / name
        for parent in (path, *path.parents):
            if parent.is_symlink():
                raise ValueError("decomposed source ancestry must not contain symlinks")
            if parent == root:
                break
        try:
            metadata = path.lstat()
        except (FileNotFoundError, NotADirectoryError):
            result[name] = None
            continue
        if not stat.S_ISREG(metadata.st_mode):
            raise ValueError("decomposed ownership evidence must be a regular file")
        result[name] = path.read_bytes()
    return result


def _fingerprint(snapshot):
    evidence = [(key, None if value is None else sha256(value).hexdigest())
                for key, value in sorted(snapshot.items())]
    return sha256(json.dumps(evidence).encode()).hexdigest()


def render(sources, strategy="gateway_run_013_plus"):
    rendered = {}
    for target, raw in sources.items():
        text = raw.decode("utf-8")
        if target == "gateway/platforms/base.py":
            patched = patcher.apply_base_patch(text)
            restored = patcher.remove_base_patch(patched)
        elif target.startswith("cron/"):
            patched = patcher.apply_cron_patch(text)
            restored = patcher.remove_cron_patch(patched)
        else:
            patched = patcher.apply_gateway_fragment(text, target, strategy=strategy)
            restored = patcher.remove_patch(patched)
        compile(patched, target, "exec")
        if restored != text:
            raise ValueError(f"{target}: patch is not reversible")
        rendered[target] = patched.encode("utf-8")
    from .detect import _LAYOUT_MARKERS
    all_bytes = b"\n".join(rendered.values())
    for name, marker in _LAYOUT_MARKERS.items():
        count = all_bytes.count(marker.encode())
        if count != 1 and not (name == "status_callback" and count == 0):
            raise ValueError(f"decomposed patch group missing or ambiguous: {name}")
    for marker in (patcher.CRON_PATCH_BEGIN, patcher.EXACT_BASE_NO_TEXT_PATCH_BEGIN,
                   patcher.EXACT_BASE_FINAL_DELIVERY_PATCH_BEGIN):
        if all_bytes.count(marker.encode()) != 1:
            raise ValueError("decomposed delivery patch group missing or ambiguous")
    return rendered


def _inspect(root):
    snapshot = _snapshot(root)
    sources = {name: snapshot[name] for name in SOURCE_TARGETS if snapshot[name] is not None}
    raw_manifest = snapshot[MANIFEST_NAME]
    if raw_manifest is None:
        if any(snapshot[name + BACKUP_SUFFIX] is not None for name in SOURCE_TARGETS):
            raise ValueError("decomposed backup has no manifest; refusing mutation")
        if any(b"HERMES_FEISHU_CARD_" in raw for raw in sources.values()):
            raise ValueError("decomposed hooks have no manifest; refusing mutation")
        return snapshot, sources, None, "clean"
    manifest = json.loads(raw_manifest)
    validate_manifest(manifest)
    if set(manifest["targets"]) != set(sources):
        raise ValueError("decomposed source target set changed")
    originals = {}
    for target, row in manifest["targets"].items():
        backup = snapshot[target + BACKUP_SUFFIX]
        if backup is None or sha256(backup).hexdigest() != row["original_sha256"]:
            raise ValueError(f"{target}: backup missing or changed")
        originals[target] = backup
    if any(snapshot[name + BACKUP_SUFFIX] is not None for name in SOURCE_TARGETS if name not in originals):
        raise ValueError("unowned decomposed backup exists")
    rendered = render(originals)
    clean_targets = []
    replacements = {}
    for target, raw in sources.items():
        row = manifest["targets"][target]
        if sha256(rendered[target]).hexdigest() != row["patched_sha256"]:
            raise ValueError(f"{target}: patch implementation differs from owned manifest")
        if tuple(row["patch_groups"]) != _patch_groups_for_target(target, rendered[target]):
            raise ValueError(f"{target}: patch group ownership differs from rendered patch")
        if row["layout_strategy"] != LAYOUT_STRATEGY:
            raise ValueError(f"{target}: layout strategy is unsupported")
        if raw == rendered[target]:
            continue
        if raw == originals[target]:
            clean_targets.append(target)
        elif b"HERMES_FEISHU_CARD_" not in raw:
            replacements[target] = raw
        else:
            raise ValueError(f"{target}: source drift; refusing mutation")
    if replacements:
        originals = {**originals, **replacements}
        rendered = render(originals)
        return snapshot, originals, rendered, "stale_unpatched"
    return snapshot, originals, rendered, "owned_incomplete" if clean_targets else "installed"


def plan(detection, *, accept_hermes_upgrade=False):
    from .recovery import RecoveryFinding, RecoveryPlan
    try:
        snapshot, _, _, state = _inspect(detection.root)
        fingerprint = _fingerprint(snapshot)
        if state == "stale_unpatched":
            return RecoveryPlan(
                detection.root,
                state,
                bool(accept_hermes_upgrade and detection.supported),
                fingerprint,
                ("accept_hermes_upgrade",),
                (RecoveryFinding(
                    "hermes_upgrade_overwrote_hooks",
                    "error",
                    "Current Hermes sources are unpatched while HFC ownership evidence remains; "
                    "Hermes update or git autostash may have moved/overwritten the hooks. "
                    "Inspect and restore manually, or explicitly accept the upgrade.",
                ),),
            )
        executable = state == "owned_incomplete"
        actions = ("restore_owned_hooks",) if executable else ()
        return RecoveryPlan(detection.root, state, executable, fingerprint, actions, ())
    except ValueError as exc:
        try:
            fingerprint = _fingerprint(_snapshot(detection.root))
        except (OSError, ValueError):
            fingerprint = sha256(b"unsafe decomposed evidence").hexdigest()
        message = str(exc)
        code = "manifest_or_ownership_invalid"
        if "patch implementation differs" in message:
            code = "patch_implementation_drift"
        elif "source drift" in message or "user edit" in message:
            code = "user_modified"
        elif "manifest" in message or "ownership" in message:
            code = "manifest_unsupported"
        return RecoveryPlan(
            detection.root,
            "refused",
            False,
            fingerprint,
            (),
            (RecoveryFinding(code, "error", message),),
        )
    except (OSError, UnicodeError) as exc:
        try:
            fingerprint = _fingerprint(_snapshot(detection.root))
        except (OSError, ValueError):
            fingerprint = sha256(b"unsafe decomposed evidence").hexdigest()
        return RecoveryPlan(
            detection.root,
            "refused",
            False,
            fingerprint,
            (),
            (RecoveryFinding(
                "ownership_evidence_unreadable",
                "error",
                f"Decomposed ownership evidence could not be read safely: {exc.__class__.__name__}.",
            ),),
        )


def install(detection, *, no_repair=False, expected_fingerprint=None, accept_hermes_upgrade=False):
    from .detect import detect_hermes
    from .recovery import _root_lock, _commit_recovery_changes, _require_secure_dirfd_transactions
    _require_secure_dirfd_transactions()
    with _root_lock(detection.root):
        snapshot, originals, rendered, state = _inspect(detection.root)
        if expected_fingerprint and _fingerprint(snapshot) != expected_fingerprint:
            raise ValueError("recovery evidence changed; rerun diagnosis")
        detection = detect_hermes(detection.root)
        if not detection.supported:
            raise ValueError("unsupported decomposed Hermes: " + detection.reason)
        if state == "installed":
            return False
        if state == "owned_incomplete" and all(
            snapshot[name] == originals[name] for name in originals
        ):
            return False
        if state in {"owned_incomplete", "stale_unpatched"} and no_repair:
            raise ValueError("decomposed ownership needs repair; --no-repair set")
        if state == "stale_unpatched" and not (accept_hermes_upgrade and detection.supported):
            raise ValueError("decomposed source upgrade requires --accept-hermes-upgrade")
        fresh = plan(detection, accept_hermes_upgrade=accept_hermes_upgrade)
        if fresh.fingerprint != _fingerprint(snapshot):
            raise ValueError("decomposed evidence changed before install")
        rendered = rendered or render(originals, detection.hook_strategy)
        manifest = {
            "manifest_version": MANIFEST_VERSION, "layout": "gateway-decomposed-v1",
            "integration_mode": "legacy-patch",
            "targets": {name: {"path": name, "backup": name + BACKUP_SUFFIX,
                                "original_sha256": sha256(raw).hexdigest(),
                                "patched_sha256": sha256(rendered[name]).hexdigest(),
                                "patch_groups": list(_patch_groups_for_target(name, rendered[name])),
                                "layout_strategy": LAYOUT_STRATEGY}
                        for name, raw in originals.items()},
        }
        validate_manifest(manifest)
        changes = [(detection.root / name, raw.decode("utf-8")) for name, raw in rendered.items()
                   if snapshot[name] != raw]
        if state in {"clean", "stale_unpatched"}:
            changes = [(detection.root / (name + BACKUP_SUFFIX), raw.decode("utf-8"))
                       for name, raw in originals.items()] + changes
            changes.append((detection.root / MANIFEST_NAME, json.dumps(manifest, indent=2) + "\n"))
        _commit_recovery_changes(detection, fresh, changes, accept_hermes_upgrade=accept_hermes_upgrade)
        _inspect(detection.root)
        return True


def restore(detection):
    from .recovery import _root_lock, _commit_recovery_changes, _require_secure_dirfd_transactions
    _require_secure_dirfd_transactions()
    with _root_lock(detection.root):
        snapshot, originals, _, state = _inspect(detection.root)
        if state == "clean":
            return
        if state == "stale_unpatched":
            raise ValueError("decomposed source drift; refusing restore until upgrade is accepted")
        fresh = plan(detection)
        if fresh.fingerprint != _fingerprint(snapshot):
            raise ValueError("decomposed evidence changed before restore")
        changes = [(detection.root / name, raw.decode("utf-8")) for name, raw in originals.items()
                   if snapshot[name] != raw]
        changes.extend((detection.root / (name + BACKUP_SUFFIX), None) for name in originals)
        changes.append((detection.root / MANIFEST_NAME, None))
        _commit_recovery_changes(detection, fresh, changes)
