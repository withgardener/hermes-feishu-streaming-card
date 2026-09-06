from pathlib import Path
import ast

import pytest

from hermes_feishu_card.install import detect, decomposed


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
