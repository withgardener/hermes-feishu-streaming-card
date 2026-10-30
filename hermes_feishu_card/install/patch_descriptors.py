from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import hashlib
import re
from typing import Callable, Iterable

from hermes_feishu_card.integration import (
    HYBRID_REQUIRED_PATCH_GROUPS,
    KNOWN_PATCH_GROUPS,
)


HYBRID_PATCH_TARGET_ORDER = (
    "gateway/run.py",
    "agent/turn_context.py",
    "agent/turn_finalizer.py",
    "tools/approval.py",
    "tools/delegate_tool.py",
    "cron/scheduler.py",
    "gateway/platforms/base.py",
)
HYBRID_PATCH_TARGETS = frozenset(HYBRID_PATCH_TARGET_ORDER)
HYBRID_PATCH_GROUPS = HYBRID_REQUIRED_PATCH_GROUPS

_FRAGMENT_NAME_RE = re.compile(r"[a-z][a-z0-9_]*\Z")
_OWNED_MARKER_RE = re.compile(
    rb"# HERMES_FEISHU_CARD_[A-Z0-9_]*PATCH_[A-Z0-9_]+"
)
_CANONICAL_MARKER_RE = re.compile(
    rb"# HERMES_FEISHU_CARD_[A-Z0-9_]+_PATCH_(?:BEGIN|END)\Z"
)
_SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")


def _require_ordinary_str(value: object, *, label: str) -> str:
    if type(value) is not str:
        raise TypeError(f"{label} must be an ordinary str")
    return value


def _require_ordinary_bytes(value: object, *, label: str) -> bytes:
    if type(value) is not bytes:
        raise TypeError(f"{label} must be ordinary bytes")
    return value


@dataclass(frozen=True)
class PatchFragmentDescriptor:
    name: str
    begin_marker: bytes
    end_marker: bytes

    def __post_init__(self) -> None:
        name = _require_ordinary_str(self.name, label="fragment name")
        begin_marker = _require_ordinary_bytes(
            self.begin_marker,
            label="fragment begin marker",
        )
        end_marker = _require_ordinary_bytes(
            self.end_marker,
            label="fragment end marker",
        )
        if not _FRAGMENT_NAME_RE.fullmatch(name):
            raise ValueError("fragment name must be a lowercase identifier")
        if begin_marker == end_marker:
            raise ValueError("fragment markers must be distinct")
        for marker, suffix in (
            (begin_marker, b"_BEGIN"),
            (end_marker, b"_END"),
        ):
            if b"\n" in marker or b"\r" in marker:
                raise ValueError("fragment marker must be one line")
            if not _CANONICAL_MARKER_RE.fullmatch(marker) or not marker.endswith(suffix):
                raise ValueError("fragment marker must be canonical ASCII owned marker")
        if begin_marker[: -len(b"_BEGIN")] != end_marker[: -len(b"_END")]:
            raise ValueError("fragment markers must use the same marker stem")


@dataclass(frozen=True)
class PatchGroupDescriptor:
    group: str
    target: str
    fragments: tuple[PatchFragmentDescriptor, ...]
    renderer: Callable[[bytes], bytes] | None = None
    remover: Callable[[bytes], bytes] | None = None
    renderer_revision: str | None = None

    def __post_init__(self) -> None:
        group = _require_ordinary_str(self.group, label="patch group")
        target = _require_ordinary_str(self.target, label="patch target")
        if group not in KNOWN_PATCH_GROUPS:
            raise ValueError(f"unknown patch group: {group}")
        if target not in HYBRID_PATCH_TARGETS:
            raise ValueError(f"unknown or nonexact patch target: {target}")
        if type(self.fragments) is not tuple or not self.fragments:
            raise TypeError("patch fragments must be a nonempty ordinary tuple")
        if any(type(fragment) is not PatchFragmentDescriptor for fragment in self.fragments):
            raise TypeError("patch fragments must contain exact PatchFragmentDescriptor values")

        names = tuple(fragment.name for fragment in self.fragments)
        markers = tuple(
            marker
            for fragment in self.fragments
            for marker in (fragment.begin_marker, fragment.end_marker)
        )
        if len(set(names)) != len(names):
            raise ValueError("duplicate fragment name in patch descriptor")
        if len(set(markers)) != len(markers):
            raise ValueError("duplicate fragment marker in patch descriptor")

        if (self.renderer is None) != (self.remover is None):
            raise ValueError("renderer and remover must be registered together")
        if self.renderer is not None:
            if not callable(self.renderer) or not callable(self.remover):
                raise TypeError("renderer and remover must be callable")
            revision = _require_ordinary_str(
                self.renderer_revision,
                label="renderer revision",
            )
            if not revision:
                raise ValueError("reviewed renderer revision must be nonempty")
        elif self.renderer_revision is not None:
            raise ValueError("renderer revision requires renderer and remover")

    @property
    def has_reviewed_renderer(self) -> bool:
        return self.renderer is not None and self.renderer_revision is not None


@dataclass(frozen=True)
class PatchDescriptorRegistry:
    descriptors: tuple[PatchGroupDescriptor, ...]
    required_groups: frozenset[str]
    required_targets: frozenset[str] = HYBRID_PATCH_TARGETS

    def __post_init__(self) -> None:
        if type(self.descriptors) is not tuple or not self.descriptors:
            raise TypeError("descriptors must be a nonempty ordinary tuple")
        if any(type(descriptor) is not PatchGroupDescriptor for descriptor in self.descriptors):
            raise TypeError("descriptors must contain exact PatchGroupDescriptor values")
        if type(self.required_groups) is not frozenset:
            raise TypeError("required groups must be an ordinary frozenset")
        required_groups = self._validate_groups(self.required_groups)
        if type(self.required_targets) is not frozenset:
            raise TypeError("required targets must be an ordinary frozenset")
        if any(type(target) is not str for target in self.required_targets):
            raise TypeError("required target names must be ordinary str values")
        if self.required_targets != HYBRID_PATCH_TARGETS:
            raise ValueError("required targets must equal the corrected fixed-tag target set")

        descriptor_groups = frozenset(descriptor.group for descriptor in self.descriptors)
        if descriptor_groups != required_groups:
            raise ValueError("descriptor groups must exactly equal required groups")

        group_targets: set[tuple[str, str]] = set()
        markers: set[bytes] = set()
        for descriptor in self.descriptors:
            group_target = (descriptor.group, descriptor.target)
            if group_target in group_targets:
                raise ValueError("duplicate patch group descriptor for target")
            group_targets.add(group_target)
            for fragment in descriptor.fragments:
                for marker in (fragment.begin_marker, fragment.end_marker):
                    if marker in markers:
                        raise ValueError("duplicate fragment marker in descriptor registry")
                    markers.add(marker)

    @staticmethod
    def _validate_groups(groups: Iterable[str]) -> frozenset[str]:
        try:
            values = tuple(groups)
        except TypeError as exc:
            raise TypeError("patch groups must be iterable") from exc
        if any(type(group) is not str for group in values):
            raise TypeError("patch group names must be ordinary str values")
        if len(values) != len(set(values)):
            raise ValueError("duplicate patch group")
        result = frozenset(values)
        unknown = result - KNOWN_PATCH_GROUPS
        if unknown:
            raise ValueError("unknown patch groups: " + ", ".join(sorted(unknown)))
        return result

    def _selected_groups(self, groups: Iterable[str]) -> frozenset[str]:
        selected = self._validate_groups(groups)
        unknown = selected - self.required_groups
        if unknown:
            raise ValueError(
                "patch groups are not registered: " + ", ".join(sorted(unknown))
            )
        return selected

    def target_groups(self, groups: Iterable[str]) -> dict[str, frozenset[str]]:
        selected = self._selected_groups(groups)
        by_target: dict[str, set[str]] = {
            target: set() for target in HYBRID_PATCH_TARGET_ORDER
        }
        for descriptor in self.descriptors:
            if descriptor.group in selected:
                by_target[descriptor.target].add(descriptor.group)
        result = {
            target: frozenset(by_target[target]) for target in HYBRID_PATCH_TARGET_ORDER
        }
        if frozenset().union(*result.values()) != selected:
            raise ValueError("target expansion does not preserve the logical patch group set")
        return result

    def target_fragments(
        self,
        groups: Iterable[str],
    ) -> dict[str, tuple[tuple[str, str], ...]]:
        selected = self._selected_groups(groups)
        by_target: dict[str, list[tuple[str, str]]] = {
            target: [] for target in HYBRID_PATCH_TARGET_ORDER
        }
        for descriptor in self.descriptors:
            if descriptor.group not in selected:
                continue
            by_target[descriptor.target].extend(
                (descriptor.group, fragment.name) for fragment in descriptor.fragments
            )
        return {
            target: tuple(by_target[target]) for target in HYBRID_PATCH_TARGET_ORDER
        }

    def validate_expected_fragment_matrix(
        self,
        expected_groups: Iterable[str],
        expected_fragment_matrix: Mapping[str, tuple[tuple[str, str], ...]],
    ) -> dict[str, tuple[tuple[str, str], ...]]:
        selected = self._selected_groups(expected_groups)
        if not isinstance(expected_fragment_matrix, Mapping):
            raise TypeError("expected patch fragment matrix must be an ordinary Mapping")
        try:
            items = tuple(expected_fragment_matrix.items())
        except Exception as exc:
            raise TypeError(
                "expected patch fragment matrix must expose ordinary mapping items"
            ) from exc
        normalized: dict[str, tuple[tuple[str, str], ...]] = {}
        for target, fragments in items:
            if type(target) is not str:
                raise TypeError(
                    "expected patch fragment matrix target must be ordinary str"
                )
            if type(fragments) is not tuple:
                raise TypeError(
                    "expected patch fragment matrix values must be ordinary tuples"
                )
            normalized_fragments: list[tuple[str, str]] = []
            for identity in fragments:
                if type(identity) is not tuple or len(identity) != 2:
                    raise TypeError(
                        "expected patch fragment identities must be ordinary two-tuples"
                    )
                group, fragment = identity
                if type(group) is not str or type(fragment) is not str:
                    raise TypeError(
                        "expected patch fragment identities must contain ordinary str"
                    )
                normalized_fragments.append((group, fragment))
            normalized[target] = tuple(normalized_fragments)
        if (
            frozenset(normalized) != self.required_targets
            or len(items) != len(self.required_targets)
        ):
            raise ValueError("expected patch fragment matrix target set mismatch")
        canonical = self.target_fragments(selected)
        if normalized != canonical:
            raise ValueError(
                "expected patch fragment matrix does not match descriptor registry"
            )
        return {
            target: normalized[target] for target in HYBRID_PATCH_TARGET_ORDER
        }

    @property
    def available_groups(self) -> frozenset[str]:
        availability = {
            group: all(
                descriptor.has_reviewed_renderer
                for descriptor in self.descriptors
                if descriptor.group == group
            )
            for group in self.required_groups
        }
        return frozenset(group for group, available in availability.items() if available)

    def validate_snapshots(self, snapshots: Mapping[str, bytes]) -> dict[str, bytes]:
        if not isinstance(snapshots, Mapping):
            raise TypeError("patch snapshots must be an ordinary Mapping")
        try:
            items = tuple(snapshots.items())
        except Exception as exc:
            raise TypeError("patch snapshots must expose ordinary mapping items") from exc
        for target, content in items:
            if type(target) is not str:
                raise TypeError("snapshot target names must be ordinary str values")
            if type(content) is not bytes:
                raise TypeError("snapshot contents must be ordinary bytes")
        targets = frozenset(target for target, _content in items)
        if targets != self.required_targets or len(items) != len(self.required_targets):
            missing = sorted(self.required_targets - targets)
            extra = sorted(targets - self.required_targets)
            raise ValueError(
                f"snapshot target set mismatch: missing={missing}; extra={extra}"
            )
        return {target: snapshots[target] for target in HYBRID_PATCH_TARGET_ORDER}

    def validate_verified_original_sha256(
        self,
        snapshots: Mapping[str, bytes],
        verified_original_sha256: Mapping[str, str],
    ) -> None:
        contents = self.validate_snapshots(snapshots)
        if not isinstance(verified_original_sha256, Mapping):
            raise TypeError("verified original SHA-256 must be an ordinary Mapping")
        try:
            items = tuple(verified_original_sha256.items())
        except Exception as exc:
            raise TypeError(
                "verified original SHA-256 must expose ordinary mapping items"
            ) from exc
        normalized: dict[str, str] = {}
        for target, digest in items:
            if type(target) is not str:
                raise TypeError("verified original SHA-256 target must be ordinary str")
            if type(digest) is not str:
                raise TypeError("verified original SHA-256 digest must be ordinary str")
            if not _SHA256_RE.fullmatch(digest):
                raise ValueError(
                    "verified original SHA-256 digest must be lowercase 64-hex"
                )
            normalized[target] = digest
        if (
            frozenset(normalized) != self.required_targets
            or len(items) != len(self.required_targets)
        ):
            raise ValueError("verified original SHA-256 target set mismatch")
        for target in HYBRID_PATCH_TARGET_ORDER:
            observed = hashlib.sha256(contents[target]).hexdigest()
            if observed != normalized[target]:
                raise ValueError(
                    f"verified original SHA-256 mismatch for target {target}"
                )

    @property
    def _known_markers(self) -> frozenset[bytes]:
        return frozenset(
            marker
            for descriptor in self.descriptors
            for fragment in descriptor.fragments
            for marker in (fragment.begin_marker, fragment.end_marker)
        )

    @staticmethod
    def _exact_marker_lines(content: bytes, marker: bytes) -> tuple[int, ...]:
        return tuple(
            index
            for index, line in enumerate(content.splitlines(keepends=True))
            if line.strip(b" \t\r\n") == marker
        )

    def _validate_target_marker_shape(
        self,
        target: str,
        content: bytes,
        descriptors: tuple[PatchGroupDescriptor, ...],
    ) -> dict[tuple[str, str], bool]:
        known_markers = self._known_markers
        observed_owned_markers = tuple(_OWNED_MARKER_RE.findall(content))
        observed = frozenset(observed_owned_markers)
        unknown = observed - known_markers
        if unknown:
            raise ValueError(f"unknown owned patch marker in target {target}")
        target_markers = frozenset(
            marker
            for descriptor in descriptors
            for fragment in descriptor.fragments
            for marker in (fragment.begin_marker, fragment.end_marker)
        )
        if observed - target_markers:
            raise ValueError(f"misplaced patch marker in target {target}")

        events: list[tuple[int, str, tuple[str, str]]] = []
        fragment_presence: dict[tuple[str, str], bool] = {}
        for descriptor in descriptors:
            descriptor_presence: list[bool] = []
            for fragment in descriptor.fragments:
                begin_lines = self._exact_marker_lines(content, fragment.begin_marker)
                end_lines = self._exact_marker_lines(content, fragment.end_marker)
                begin_count = content.count(fragment.begin_marker)
                end_count = content.count(fragment.end_marker)
                if begin_count != len(begin_lines) or end_count != len(end_lines):
                    raise ValueError(f"misplaced patch marker in target {target}")
                if begin_count > 1 or end_count > 1:
                    raise ValueError(f"duplicate patch marker in target {target}")
                if begin_count != end_count:
                    raise ValueError(f"partial patch marker in target {target}")
                present = begin_count == 1
                descriptor_presence.append(present)
                fragment_presence[(descriptor.group, fragment.name)] = present
                if present:
                    events.append(
                        (begin_lines[0], "begin", (descriptor.group, fragment.name))
                    )
                    events.append((end_lines[0], "end", (descriptor.group, fragment.name)))
            if any(descriptor_presence) and not all(descriptor_presence):
                raise ValueError(
                    f"patch group {descriptor.group} has incomplete fragments in {target}"
                )

        stack: list[tuple[str, str]] = []
        for _line, edge, identity in sorted(events):
            if edge == "begin":
                if stack:
                    raise ValueError(f"nested patch markers in target {target}")
                stack.append(identity)
                continue
            if not stack or stack[-1] != identity:
                raise ValueError(f"reversed patch markers in target {target}")
            stack.pop()
        if stack:
            raise ValueError(f"partial patch marker in target {target}")
        return fragment_presence

    def detect(
        self,
        snapshots: Mapping[str, bytes],
        *,
        expected_groups: Iterable[str],
        expected_fragment_matrix: Mapping[str, tuple[tuple[str, str], ...]],
    ) -> dict[str, frozenset[str]]:
        selected = self._selected_groups(expected_groups)
        expected_matrix = self.validate_expected_fragment_matrix(
            selected,
            expected_fragment_matrix,
        )
        contents = self.validate_snapshots(snapshots)
        presence: dict[tuple[str, str], bool] = {}
        observed_matrix: dict[str, list[tuple[str, str]]] = {
            target: [] for target in HYBRID_PATCH_TARGET_ORDER
        }
        descriptors_by_target = {
            target: tuple(
                descriptor
                for descriptor in self.descriptors
                if descriptor.target == target
            )
            for target in HYBRID_PATCH_TARGET_ORDER
        }
        for target, descriptors in descriptors_by_target.items():
            fragment_presence = self._validate_target_marker_shape(
                target,
                contents[target],
                descriptors,
            )
            for descriptor in descriptors:
                descriptor_present = all(
                    fragment_presence[(descriptor.group, fragment.name)]
                    for fragment in descriptor.fragments
                )
                presence[(descriptor.group, descriptor.target)] = descriptor_present
                if not descriptor_present:
                    continue
                observed_matrix[target].extend(
                    (descriptor.group, fragment.name)
                    for fragment in descriptor.fragments
                )

        detected_groups: set[str] = set()
        for group in self.required_groups:
            group_descriptors = tuple(
                descriptor for descriptor in self.descriptors if descriptor.group == group
            )
            states = tuple(
                presence[(descriptor.group, descriptor.target)]
                for descriptor in group_descriptors
            )
            if any(states) and not all(states):
                raise ValueError(f"patch group {group} is incomplete across targets")
            if states and all(states):
                detected_groups.add(group)

        normalized_observed_matrix = {
            target: tuple(observed_matrix[target])
            for target in HYBRID_PATCH_TARGET_ORDER
        }
        if normalized_observed_matrix != expected_matrix:
            raise ValueError("expected patch fragment matrix does not match installed snapshot")
        if frozenset(detected_groups) != selected:
            raise ValueError("expected patch groups do not match installed snapshot")

        for descriptor in self.descriptors:
            if not presence[(descriptor.group, descriptor.target)]:
                continue
            if not descriptor.has_reviewed_renderer:
                raise ValueError(
                    f"reviewed renderer unavailable for patch group {descriptor.group}"
                )
            try:
                removed = descriptor.remover(contents[descriptor.target])
                if type(removed) is not bytes:
                    raise TypeError("patch remover must return ordinary bytes")
                rerendered = descriptor.renderer(removed)
            except Exception as exc:
                raise ValueError(
                    f"owned patch body or placement changed for group {descriptor.group}"
                ) from exc
            if type(rerendered) is not bytes or rerendered != contents[descriptor.target]:
                raise ValueError(
                    f"owned patch body or placement changed for group {descriptor.group}"
                )

        result = self.target_groups(frozenset(detected_groups))
        if frozenset().union(*result.values()) != frozenset(detected_groups):
            raise ValueError("detected patch group union is inconsistent")
        return result

    def render_verified_originals(
        self,
        verified_originals: Mapping[str, bytes],
        required_groups: Iterable[str],
        *,
        expected_fragment_matrix: Mapping[str, tuple[tuple[str, str], ...]],
        verified_original_sha256: Mapping[str, str],
    ) -> dict[str, bytes]:
        selected = self._selected_groups(required_groups)
        expected_matrix = self.validate_expected_fragment_matrix(
            selected,
            expected_fragment_matrix,
        )
        originals = self.validate_snapshots(verified_originals)
        self.validate_verified_original_sha256(
            originals,
            verified_original_sha256,
        )
        clean_groups = frozenset()
        clean_matrix = self.target_fragments(clean_groups)
        self.detect(
            originals,
            expected_groups=clean_groups,
            expected_fragment_matrix=clean_matrix,
        )
        unavailable = selected - self.available_groups
        if unavailable:
            raise ValueError(
                "reviewed renderer unavailable for patch groups: "
                + ", ".join(sorted(unavailable))
            )

        rendered = dict(originals)
        for descriptor in self.descriptors:
            if descriptor.group not in selected:
                continue
            result = descriptor.renderer(rendered[descriptor.target])
            if type(result) is not bytes:
                raise TypeError("patch renderer must return ordinary bytes")
            rendered[descriptor.target] = result

        expected = self.target_groups(selected)
        if self.detect(
            rendered,
            expected_groups=selected,
            expected_fragment_matrix=expected_matrix,
        ) != expected:
            raise ValueError("rendered patch target/group/fragment matrix is incomplete")
        return rendered

    def remove(
        self,
        snapshots: Mapping[str, bytes],
        *,
        expected_groups: Iterable[str],
        expected_fragment_matrix: Mapping[str, tuple[tuple[str, str], ...]],
    ) -> dict[str, bytes]:
        contents = self.validate_snapshots(snapshots)
        selected = self._selected_groups(expected_groups)
        expected_matrix = self.validate_expected_fragment_matrix(
            selected,
            expected_fragment_matrix,
        )
        detected = self.detect(
            contents,
            expected_groups=selected,
            expected_fragment_matrix=expected_matrix,
        )
        flat_detected = frozenset().union(*detected.values())
        if flat_detected != selected:
            raise ValueError("detected patch groups do not match expected patch groups")

        removed = dict(contents)
        for descriptor in reversed(self.descriptors):
            if descriptor.group not in flat_detected:
                continue
            result = descriptor.remover(removed[descriptor.target])
            if type(result) is not bytes:
                raise TypeError("patch remover must return ordinary bytes")
            removed[descriptor.target] = result
        clean_groups = frozenset()
        clean_matrix = self.target_fragments(clean_groups)
        if any(
            self.detect(
                removed,
                expected_groups=clean_groups,
                expected_fragment_matrix=clean_matrix,
            ).values()
        ):
            raise ValueError("strict aggregate removal left owned patch markers")
        return removed


@dataclass(frozen=True)
class LegacyTargetPatchAdapter:
    target: str
    renderer: Callable[[str], str]
    strict_remover: Callable[[str], str]
    owned_markers: tuple[tuple[str, str], ...]

    def __post_init__(self) -> None:
        target = _require_ordinary_str(self.target, label="legacy patch target")
        if target not in HYBRID_PATCH_TARGETS:
            raise ValueError(f"unknown or nonexact legacy patch target: {target}")
        if not callable(self.renderer) or not callable(self.strict_remover):
            raise TypeError("legacy renderer and strict remover must be callable")
        if type(self.owned_markers) is not tuple or not self.owned_markers:
            raise TypeError("legacy owned markers must be a nonempty ordinary tuple")
        flat_markers: list[str] = []
        for pair in self.owned_markers:
            if type(pair) is not tuple or len(pair) != 2:
                raise TypeError("legacy marker pairs must be ordinary two-tuples")
            begin, end = pair
            _require_ordinary_str(begin, label="legacy begin marker")
            _require_ordinary_str(end, label="legacy end marker")
            if begin == end:
                raise ValueError("legacy marker pair must be distinct")
            flat_markers.extend(pair)
        if len(flat_markers) != len(set(flat_markers)):
            raise ValueError("duplicate marker in legacy target adapter")


def detect_patch_groups_by_target(
    snapshots: Mapping[str, bytes],
    *,
    expected_groups: Iterable[str],
    expected_fragment_matrix: Mapping[str, tuple[tuple[str, str], ...]],
    registry: PatchDescriptorRegistry,
) -> dict[str, frozenset[str]]:
    if type(registry) is not PatchDescriptorRegistry:
        raise TypeError("registry must be an exact PatchDescriptorRegistry")
    return registry.detect(
        snapshots,
        expected_groups=expected_groups,
        expected_fragment_matrix=expected_fragment_matrix,
    )


def remove_patch_snapshots(
    snapshots: Mapping[str, bytes],
    *,
    expected_groups: Iterable[str],
    expected_fragment_matrix: Mapping[str, tuple[tuple[str, str], ...]],
    registry: PatchDescriptorRegistry,
) -> dict[str, bytes]:
    if type(registry) is not PatchDescriptorRegistry:
        raise TypeError("registry must be an exact PatchDescriptorRegistry")
    return registry.remove(
        snapshots,
        expected_groups=expected_groups,
        expected_fragment_matrix=expected_fragment_matrix,
    )


def render_patch_snapshots_from_verified_originals(
    verified_originals: Mapping[str, bytes],
    *,
    verified_original_sha256: Mapping[str, str],
    integration_mode: str,
    required_patch_groups: Iterable[str],
    expected_fragment_matrix: Mapping[str, tuple[tuple[str, str], ...]],
    registry: PatchDescriptorRegistry,
) -> dict[str, bytes]:
    if type(registry) is not PatchDescriptorRegistry:
        raise TypeError("registry must be an exact PatchDescriptorRegistry")
    if type(integration_mode) is not str:
        raise TypeError("integration mode must be an ordinary str")
    selected = registry._selected_groups(required_patch_groups)
    expected_matrix = registry.validate_expected_fragment_matrix(
        selected,
        expected_fragment_matrix,
    )
    if integration_mode == "native-hooks":
        if selected:
            raise ValueError("native-hooks required patch groups must be empty")
        originals = registry.validate_snapshots(verified_originals)
        registry.validate_verified_original_sha256(
            originals,
            verified_original_sha256,
        )
        registry.detect(
            originals,
            expected_groups=selected,
            expected_fragment_matrix=expected_matrix,
        )
        return dict(originals)
    if integration_mode != "hybrid":
        raise ValueError(
            "aggregate descriptor rendering currently supports hybrid or native-hooks"
        )
    if selected != registry.required_groups:
        raise ValueError("required patch groups do not match the descriptor registry")
    return registry.render_verified_originals(
        verified_originals,
        selected,
        expected_fragment_matrix=expected_matrix,
        verified_original_sha256=verified_original_sha256,
    )


def _hybrid_marker(group: str, fragment: str, edge: str) -> bytes:
    token = f"{group}_{fragment}".upper()
    return f"# HERMES_FEISHU_CARD_HYBRID_{token}_PATCH_{edge}".encode("ascii")


def _structural_descriptor(
    group: str,
    target: str,
    *fragments: str,
) -> PatchGroupDescriptor:
    return PatchGroupDescriptor(
        group=group,
        target=target,
        fragments=tuple(
            PatchFragmentDescriptor(
                name=fragment,
                begin_marker=_hybrid_marker(group, fragment, "BEGIN"),
                end_marker=_hybrid_marker(group, fragment, "END"),
            )
            for fragment in fragments
        ),
    )


HYBRID_PATCH_DESCRIPTORS = (
    _structural_descriptor(
        "ingress_binding",
        "gateway/run.py",
        "authenticated_ingress",
        "canonical_turn_consume",
    ),
    _structural_descriptor(
        "ingress_binding",
        "agent/turn_context.py",
        "canonical_turn_publish",
    ),
    _structural_descriptor(
        "ingress_binding",
        "agent/turn_finalizer.py",
        "canonical_turn_clear",
    ),
    _structural_descriptor(
        "terminal_disposition", "gateway/run.py", "terminal_consume",
        "terminal_carrier_empty", "terminal_carrier_normal",
        "native_progress_enqueue", "native_progress_send", "native_progress_cancel",
        "queued_terminal_consume",
    ),
    _structural_descriptor("answer_delta", "gateway/run.py", "answer_delta"),
    _structural_descriptor("thinking_delta", "gateway/run.py", "thinking_delta"),
    _structural_descriptor(
        "clarify_round_trip",
        "gateway/run.py",
        "clarify_register",
        "clarify_resolve",
    ),
    _structural_descriptor(
        "approval_round_trip",
        "tools/approval.py",
        "approval_register",
        "approval_resolve",
    ),
    _structural_descriptor("status_notice", "gateway/run.py", "status_notice"),
    _structural_descriptor(
        "slash_confirm",
        "gateway/run.py",
        "slash_register",
        "slash_resolve",
    ),
    _structural_descriptor(
        "command_card_startup",
        "gateway/run.py",
        "command_card_startup",
    ),
    _structural_descriptor(
        "command_card_adapter",
        "gateway/run.py",
        "command_card_adapter",
    ),
    _structural_descriptor("native_redelivery", "gateway/run.py", "native_redelivery"),
    _structural_descriptor("platform_notice", "gateway/run.py", "platform_notice"),
    _structural_descriptor("hfc_command", "gateway/run.py", "hfc_command"),
    _structural_descriptor("cron_delivery", "cron/scheduler.py", "cron_delivery"),
    _structural_descriptor(
        "exact_base_no_text",
        "gateway/platforms/base.py",
        "exact_base_no_text",
    ),
    _structural_descriptor(
        "exact_base_final_delivery",
        "gateway/platforms/base.py",
        "exact_base_final_delivery",
    ),
    _structural_descriptor(
        "subagent_parent_identity",
        "tools/delegate_tool.py",
        "immutable_parent_turn",
    ),
)

HYBRID_PATCH_REGISTRY = PatchDescriptorRegistry(
    descriptors=HYBRID_PATCH_DESCRIPTORS,
    required_groups=HYBRID_PATCH_GROUPS,
)
