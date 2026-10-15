"""Compatibility names for existing decomposed installer consumers.

Internal callers use read-only ownership or the recovery transaction owner.
"""
from .source_layout import (
    BACKUP_SUFFIX as BACKUP_SUFFIX,
    MANIFEST_NAME as MANIFEST_NAME,
    DECOMPOSED_MANIFEST_VERSION as MANIFEST_VERSION,
    DECOMPOSED_SOURCE_TARGETS as SOURCE_TARGETS,
)
from .manifest import validate_decomposed_manifest as validate_manifest
from .decomposed_ownership import (
    is_managed as is_managed,
    _snapshot as _snapshot,
    _fingerprint as _fingerprint,
    render as render,
    snapshot_provenance as snapshot_provenance,
    verified_snapshot_provenance as verified_snapshot_provenance,
    _remove_target as _remove_target,
    _verified_reapplied_source as _verified_reapplied_source,
    _legacy_upgrade_sources as _legacy_upgrade_sources,
    _inspect as _inspect,
    VERSION_TARGETS as VERSION_TARGETS,
    EXPLICIT_UPGRADE_STATES as EXPLICIT_UPGRADE_STATES,
)
from .recovery import (
    _plan_decomposed_recovery as plan,
    install_decomposed as install,
    restore_decomposed as restore,
)
