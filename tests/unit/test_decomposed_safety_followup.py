from pathlib import Path
import ast
import shutil

import pytest

from hermes_feishu_card.install import detect, decomposed

FIXTURE = Path(__file__).parents[1] / "fixtures/hermes_decomposed"


def test_modern_split_capabilities_allow_multiple_usage_locations(tmp_path):
    root = tmp_path / "hermes"
    shutil.copytree(FIXTURE, root)
    detection = detect.detect_hermes(root)
    assert detection.supported
    assert detection.layout == detect.HermesLayout.MODERN_SPLIT_GATEWAY.value
    assert detection.reason == "supported"
    assert detection.anchor_candidates == {}
    assert detection.capability_locations["reply_context"] == (
        "gateway/run_notifications.py",
        "gateway/run_turn.py",
    )
    assert detection.capability_locations["attachment_delivery"] == (
        "gateway/run_notifications.py",
        "gateway/run_turn.py",
    )
    assert "ambiguous" not in detection.reason


def test_doctor_report_keeps_capability_evidence_separate(tmp_path):
    root = tmp_path / "hermes"
    shutil.copytree(FIXTURE, root)
    detection = detect.detect_hermes(root)
    assert detection.layout == "modern_split_gateway"
    assert detection.anchor_candidates == {}
    assert detection.capability_locations["reply_context"]
    assert detection.capability_locations["attachment_delivery"]


def test_duplicate_handler_is_ambiguous():
    tree = ast.parse("async def _handle_message_with_agent(): pass\nasync def _handle_message_with_agent(): pass\n")
    with pytest.raises(detect.AnchorAmbiguityError) as error:
        detect._find_supported_handler(tree)
    assert error.value.locations == ("line 1:column 0", "line 2:column 0")


def test_docstring_and_string_pseudo_anchors_are_not_functions():
    tree = ast.parse('''"""async def _handle_message_with_agent(): pass"""\nexample = "def _run_agent(): pass"\n''')
    assert detect._find_supported_handler(tree) is None
    assert detect._find_function(tree, "_run_agent") is None


def test_layout_constants_are_explicit():
    assert detect.HermesLayout.LEGACY_SINGLE_FILE.value == "legacy_single_file"
    assert detect.HermesLayout.MODERN_SPLIT_GATEWAY.value == "modern_split_gateway"
    assert detect.HermesLayout.UNSUPPORTED_OR_AMBIGUOUS.value == "unsupported_or_ambiguous"


def test_manifest_requires_exact_target_ownership():
    manifest = {
        "manifest_version": decomposed.MANIFEST_VERSION,
        "layout": "gateway-decomposed-v1",
        "integration_mode": "legacy-patch",
        "targets": {},
    }
    with pytest.raises(ValueError, match="ownership"):
        decomposed.validate_manifest(manifest)
