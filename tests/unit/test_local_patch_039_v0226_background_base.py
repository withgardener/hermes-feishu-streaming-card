"""PATCH-039: Hermes v0.22.6's background-turn base and admission cohort.

v0.22.6 (``6cfdb53323``) extracted background-turn execution from
``gateway/run_turn.py`` into ``gateway/run_background.py`` and made
``GatewayBackgroundMixin`` the *first* base of ``GatewayTurnMixin``::

    class GatewayTurnMixin(GatewayBackgroundMixin, GatewayTurnPrepareMixin,
                           GatewayTurnHygieneMixin, GatewayTurnPersistenceMixin):

The three completion methods still live in ``gateway/run_turn_persistence.py``,
so ownership did not move — the installer simply refused an unknown base tuple
(*"inherited completion ownership contract changed"*). Accepting the tuple alone
is not enough: the earlier-base shadow proof resolves every base through
``sources``, and ``gateway/run_background.py`` is not a render target, so it used
to be parsed as an empty module and reported as a shadow.

The tests below drive the real installer contracts over verbatim source
excerpts, then repeat them against a real v0.22.6 checkout when
``HFC_UPSTREAM_V0226_ROOT`` is supplied (the same opt-in shape as
``test_issue_456_453_contracts.py``).
"""
from __future__ import annotations

import os
import subprocess
import textwrap
from hashlib import sha256
from pathlib import Path

import pytest

from hermes_feishu_card.admission_completion import SOURCE_COHORTS, SOURCE_HASHES
from hermes_feishu_card.install import decomposed, decomposed_ownership, detect, patcher
from hermes_feishu_card.install.source_layout import (
    COMPLETION_REFERENCE_SOURCES,
    DECOMPOSED_GATEWAY_TARGETS,
    DECOMPOSED_SOURCE_TARGETS,
    DECOMPOSED_TARGETS,
)

V0226_ROOT_ENV = "HFC_UPSTREAM_V0226_ROOT"

# Verbatim shape of gateway/run_turn.py:163-168 (Hermes v0.22.6).
V0226_RUN_TURN = textwrap.dedent(
    '''\
    from gateway.run_turn_prepare import GatewayTurnPrepareMixin
    from gateway.run_background import GatewayBackgroundMixin
    from gateway.run_turn_hygiene import GatewayTurnHygieneMixin
    from gateway.run_turn_persistence import GatewayTurnPersistenceMixin


    class GatewayTurnMixin(GatewayBackgroundMixin, GatewayTurnPrepareMixin, GatewayTurnHygieneMixin, GatewayTurnPersistenceMixin):
        """Agent-turn execution for GatewayRunner (see module docstring)."""

        async def _handle_message_with_agent(self, event, source, _quick_key, run_generation):
            hook_ctx = {}
            session_entry = None
            session_key = _quick_key
            agent_result = await self._run_agent(event, source)
            _turn_seconds = 1.25
            agent_messages = []
            response = agent_result.get("response", "")
            _footer_line = ""
            _intentional_silence = False
            await self._hmwa_post_turn_hooks(hook_ctx, agent_result, response)
            return await self._hmwa_deliver_turn_response(
                event, source, session_entry, session_key, run_generation,
                agent_result, agent_messages, response, _footer_line, _intentional_silence,
            )

        async def _run_agent(self, event, source):
            return {"response": "answer"}
    '''
)

# Verbatim shape of gateway/run_turn_persistence.py (the completion owner).
V0226_PERSISTENCE = textwrap.dedent(
    '''\
    from __future__ import annotations


    class GatewayTurnPersistenceMixin:
        async def _hmwa_post_turn_hooks(self, hook_ctx, agent_result, response):
            await self.hooks.emit("agent:end", {**hook_ctx, "response": response})

        async def _hmwa_deliver_turn_response(
            self, event, source, session_entry, session_key, run_generation,
            agent_result, agent_messages, response, _footer_line, _intentional_silence,
        ):
            if _intentional_silence:
                response = ""
            return response
    '''
)

# Verbatim shape of gateway/run_background.py:22 — no base, no completion method.
V0226_BACKGROUND = textwrap.dedent(
    '''\
    """Finite background tasks launched by the gateway /bg command."""


    class GatewayBackgroundMixin:
        async def _run_background_task_inner(self, prompt, source, task_id):
            return None
    '''
)

_THIN_MIXIN = "class {name}:\n    \"\"\"Mixin seam.\"\"\"\n"


def _sources(*, background_base: bool = True, background: str = V0226_BACKGROUND) -> dict:
    """A v0.22.6-shaped source set; the render targets are the only settings."""
    run_turn = V0226_RUN_TURN
    if not background_base:
        run_turn = run_turn.replace(
            "from gateway.run_background import GatewayBackgroundMixin\n", ""
        ).replace(
            "class GatewayTurnMixin(GatewayBackgroundMixin, GatewayTurnPrepareMixin, "
            "GatewayTurnHygieneMixin, GatewayTurnPersistenceMixin):",
            "class GatewayTurnMixin(GatewayTurnPrepareMixin, GatewayTurnHygieneMixin, "
            "GatewayTurnPersistenceMixin):",
        )
    sources = {
        "gateway/run_turn.py": run_turn,
        "gateway/run_turn_persistence.py": V0226_PERSISTENCE,
        "gateway/run_turn_prepare.py": _THIN_MIXIN.format(name="GatewayTurnPrepareMixin"),
        "gateway/run_turn_hygiene.py": _THIN_MIXIN.format(name="GatewayTurnHygieneMixin"),
    }
    if background_base:
        sources["gateway/run_background.py"] = background
    return sources


def test_v0226_background_base_tuple_is_accepted():
    assert patcher._split_completion_node(_sources(), "gateway/run_turn.py") is not None
    assert patcher._split_completion_node(
        _sources(), "gateway/run_turn_persistence.py"
    ) is not None


def test_v0225_three_base_tuple_is_still_accepted():
    node = patcher._split_completion_node(
        _sources(background_base=False), "gateway/run_turn.py"
    )
    assert node is not None


def test_a_missing_background_source_fails_closed():
    """An allowlisted base name is not evidence; its module has to be present."""
    sources = _sources()
    del sources["gateway/run_background.py"]

    with pytest.raises(ValueError, match="earlier base source missing"):
        patcher._split_completion_node(sources, "gateway/run_turn.py")


def test_a_background_base_owning_a_completion_method_is_refused():
    shadowed = V0226_BACKGROUND + textwrap.dedent(
        '''\

        class GatewayBackgroundMixin:  # rebinding the name is still shadowing
            async def _hmwa_deliver_turn_response(self, *args, **kwargs):
                return None
        '''
    )

    with pytest.raises(ValueError, match="shadow or rebinding"):
        patcher._split_completion_node(
            _sources(background=shadowed), "gateway/run_turn.py"
        )


def test_the_background_module_is_a_read_only_reference():
    assert COMPLETION_REFERENCE_SOURCES == ("gateway/run_background.py",)
    reference = set(COMPLETION_REFERENCE_SOURCES)
    assert not reference & set(DECOMPOSED_GATEWAY_TARGETS)
    assert not reference & set(DECOMPOSED_TARGETS)
    assert not reference & set(DECOMPOSED_SOURCE_TARGETS)

    with pytest.raises(ValueError, match="unknown Gateway patch target"):
        patcher.apply_gateway_fragment(V0226_BACKGROUND, "gateway/run_background.py")


def test_reference_sources_are_read_without_becoming_targets(tmp_path):
    gateway = tmp_path / "gateway"
    gateway.mkdir()
    (gateway / "run_background.py").write_text(V0226_BACKGROUND)

    read = decomposed_ownership.read_reference_sources(tmp_path)

    assert set(read) == set(COMPLETION_REFERENCE_SOURCES)
    assert read["gateway/run_background.py"] == V0226_BACKGROUND.encode()
    assert not set(read) & set(DECOMPOSED_SOURCE_TARGETS)


def test_reference_sources_do_not_add_or_duplicate_anchor_locations():
    sources = {"gateway/run_turn_runner.py": "class TurnRunner:\n    pass\n"}

    plain = detect._detect_layout_capabilities(sources, "", "cron/scheduler.py")
    referenced = detect._detect_layout_capabilities(
        sources,
        "",
        "cron/scheduler.py",
        reference_sources={"gateway/run_background.py": V0226_BACKGROUND},
    )

    assert plain == referenced
    assert all(
        "gateway/run_background.py" not in location
        for locations in referenced[1].values()
        for location in locations
    )


def test_the_v0226_admission_pair_is_registered_without_touching_the_first_row():
    v0226 = {
        "gateway.session_ingress": (
            "12466f9c31f57877c6ae8ea6189d76123a278bdc99e5242c13c5c4ecff0f8ae9"
        ),
        "gateway.session_authority": (
            "207708e4aeb0bf2d8e577f145110a414d80c12da1c4e69570f0402f7d7f6d1a6"
        ),
    }

    assert v0226 in SOURCE_COHORTS
    assert SOURCE_COHORTS[0] is SOURCE_HASHES
    assert SOURCE_HASHES == {
        "gateway.session_ingress": (
            "fc8b666f74aa430c832c973e64a6b6332ae8c0c43ac5d3b69766debf31fb8dd4"
        ),
        "gateway.session_authority": (
            "e5f3f9b24ccb765dc7fccb98d9c61bed359e3b1da3a73c855c713be425df5d7c"
        ),
    }


def test_an_unknown_admission_pair_is_still_refused(tmp_path):
    gateway = tmp_path / "gateway"
    gateway.mkdir()
    (gateway / "session_ingress.py").write_text("# not a pinned cohort\n")
    (gateway / "session_authority.py").write_text("# not a pinned cohort\n")

    assert detect._detect_admission_completion(tmp_path, "") == (
        False,
        "unsupported-source",
    )


def _v0226_root() -> Path:
    configured = os.environ.get(V0226_ROOT_ENV)
    if not configured:
        pytest.skip(f"exact v0.22.6 checkout not supplied: {V0226_ROOT_ENV}")
    root = Path(configured)
    assert (root / "gateway" / "run_background.py").is_file(), root
    return root


def _head_blob(root: Path, name: str) -> bytes:
    """Read the checked-in v0.22.6 bytes, not whatever HFC has installed."""
    return subprocess.check_output(["git", "-C", str(root), "show", f"HEAD:{name}"])


def test_real_v0226_ownership_proof_accepts_the_background_base():
    root = _v0226_root()
    sources = {
        name: _head_blob(root, name).decode()
        for name in decomposed.SOURCE_TARGETS
        if (root / name).exists()
    }
    # The base module is not a target, so the caller supplies it read-only.
    assert "gateway/run_background.py" not in sources
    sources.update(
        {name: raw.decode() for name, raw in
         decomposed_ownership.read_reference_sources(root).items()}
    )

    assert patcher._split_completion_node(sources, "gateway/run_turn.py") is not None
    assert patcher._split_completion_node(
        sources, "gateway/run_turn_persistence.py"
    ) is not None


def test_real_v0226_render_keeps_the_reference_out_of_the_target_set():
    root = _v0226_root()
    sources = {
        name: _head_blob(root, name)
        for name in decomposed.SOURCE_TARGETS
        if (root / name).exists()
    }

    rendered = decomposed_ownership.render(
        sources,
        reference_sources=decomposed_ownership.read_reference_sources(root),
    )

    assert set(rendered) == set(sources)
    assert "gateway/run_background.py" not in rendered


def test_real_v0226_detection_is_full_with_the_whole_anchor_set(tmp_path):
    root = _v0226_root()
    # A fresh checkout: the source files only, no manifest or backups, so the
    # anchors are assessed on the v0.22.6 bytes rather than on owned originals.
    fresh = tmp_path / "checkout"
    for name in (*decomposed.SOURCE_TARGETS, *COMPLETION_REFERENCE_SOURCES,
                 "gateway/session_ingress.py", "gateway/session_authority.py"):
        source = root / name
        if not source.is_file():
            continue
        target = fresh / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(_head_blob(root, name))

    detection = detect.detect_hermes(fresh)

    assert detection.supported, detection.reason
    assert detection.compatibility == "full"
    assert [name for name, found in detection.capabilities.items() if not found] == []
    assert len(detection.capabilities) == 21
    assert detection.capabilities["message_handler"]
    assert detection.capabilities["completion_return"]
    assert detection.capabilities["admission_completion"]
