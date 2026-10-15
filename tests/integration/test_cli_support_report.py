"""Real CLI selection/export with diagnostic I/O replaced by synthetic input."""
import json
import os
import socket
import stat

import pytest

from hermes_feishu_card import cli, support_report


@pytest.fixture
def doctor_config(tmp_path, monkeypatch):
    path = tmp_path / "input.yaml"
    path.write_text("server: {}\n")

    def no_network(*args, **kwargs):
        pytest.fail("support-report test attempted a network connection")

    monkeypatch.setattr(socket.socket, "connect", no_network)
    return path


@pytest.mark.parametrize("status,exit_code", [("ok", 0), ("warning", 0), ("error", 1)])
def test_preview_is_sanitized_read_only_and_preserves_doctor_exit_code(
    doctor_config, monkeypatch, capsys, status, exit_code,
):
    source = {"status": status, "config": {"path": "/synthetic/PRIVATE_PATH", "loaded": True},
              "recommendations": [{"code": "config_load_failed", "severity": "error",
                                   "message": "PRIVATE_ERROR", "next_step": "PRIVATE_COMMAND"}],
              "configuration": {"app_secret": "PRIVATE_CONFIG"}, "chat_id": "PRIVATE_CHAT"}
    monkeypatch.setattr(cli, "_build_doctor_report", lambda *args: source)
    before = doctor_config.read_bytes()
    assert cli.main(["doctor", "--config", str(doctor_config), "--support-report"]) == exit_code
    captured = capsys.readouterr()
    report = json.loads(captured.out)
    assert report["diagnostics"]["status"] == status
    assert report["diagnostics"]["recommendations"][0]["code"] == "config_load_failed"
    assert "PRIVATE_" not in captured.out + captured.err
    assert doctor_config.read_bytes() == before
    assert sorted(p.name for p in doctor_config.parent.iterdir()) == ["input.yaml"]


def test_export_previews_exact_safe_report_before_creating_private_file(doctor_config, monkeypatch, capsys):
    source = {"status": "warning", "config": {"path": "/synthetic/PRIVATE_PATH"}}
    monkeypatch.setattr(cli, "_build_doctor_report", lambda *args: source)
    original_writer = support_report.write_support_report
    previews = []
    target = doctor_config.parent / "report.json"

    def inspect_before_write(path, payload):
        assert not target.exists()
        previews.append(json.loads(capsys.readouterr().out))
        original_writer(path, payload)

    monkeypatch.setattr(support_report, "write_support_report", inspect_before_write)
    assert cli.main(["doctor", "--config", str(doctor_config), "--export-report", str(target)]) == 0
    assert previews == [json.loads(target.read_text())]
    captured = capsys.readouterr()
    assert "saved locally" in captured.err and "Nothing was uploaded" in captured.err
    assert "PRIVATE_" not in target.read_text() + captured.out + captured.err
    if os.name != "nt":
        assert stat.S_IMODE(target.stat().st_mode) == 0o600


@pytest.mark.parametrize("mode", ["--support-report", "--export-report"])
@pytest.mark.parametrize("config_case,expected_code,expected_status", [
    ("missing", 0, "ok"), ("invalid", 1, "error"),
])
def test_unavailable_config_preserves_legacy_doctor_result_and_exports_safely(
    tmp_path, monkeypatch, capsys, mode, config_case, expected_code, expected_status,
):
    def no_network(*args, **kwargs):
        pytest.fail("missing configuration must not contact a service")

    monkeypatch.setattr(socket.socket, "connect", no_network)
    missing, target = tmp_path / "PRIVATE_MISSING_CONFIG.yaml", tmp_path / "report.json"
    if config_case == "invalid":
        missing.write_text("- PRIVATE_CONFIG_CONTENT\n")
    # The established loader uses defaults when no file exists. Invalid YAML
    # is an error; adding an export mode must not silently change either case.
    legacy_code = cli.main(["doctor", "--config", str(missing), "--json"])
    legacy = json.loads(capsys.readouterr().out)
    assert legacy_code == expected_code
    assert legacy["status"] == expected_status
    args = ["doctor", "--config", str(missing), mode]
    if mode == "--export-report":
        args.append(str(target))
    assert cli.main(args) == legacy_code
    captured = capsys.readouterr()
    report = json.loads(captured.out)
    assert report["diagnostics"]["status"] == expected_status
    assert [item["code"] for item in report["diagnostics"]["recommendations"]] == [
        item["code"] for item in legacy["recommendations"]
    ]
    assert "PRIVATE_MISSING_CONFIG" not in captured.out + captured.err
    assert str(tmp_path) not in captured.out + captured.err
    if mode == "--export-report":
        assert json.loads(target.read_text()) == report


def test_oversized_report_fails_before_preview_or_file_creation(doctor_config, monkeypatch, capsys):
    source = {"findings": [{"code": "config_load_failed", "severity": "error"}] * 2000}
    monkeypatch.setattr(cli, "_build_doctor_report", lambda *args: source)
    target = doctor_config.parent / "report.json"
    assert cli.main(["doctor", "--config", str(doctor_config), "--export-report", str(target)]) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "Unable to create" in captured.err
    assert not target.exists()


def test_export_existing_file_is_preserved_with_distinct_export_error(doctor_config, monkeypatch, capsys):
    monkeypatch.setattr(cli, "_build_doctor_report", lambda *args: {"status": "ok"})
    target = doctor_config.parent / "report.json"
    target.write_text("original")
    assert cli.main(["doctor", "--config", str(doctor_config), "--export-report", str(target)]) == 2
    captured = capsys.readouterr()
    assert json.loads(captured.out)["diagnostics"]["status"] == "ok"
    assert "already exists" in captured.err
    assert target.read_text() == "original"


def test_export_write_error_never_prints_raw_failure_or_claims_success(doctor_config, monkeypatch, capsys):
    monkeypatch.setattr(cli, "_build_doctor_report", lambda *args: {"status": "ok"})

    def fail_sync(fd):
        raise OSError("PRIVATE_WRITE_ERROR /synthetic/PRIVATE_PATH")

    monkeypatch.setattr(support_report.os, "fsync", fail_sync)
    target = doctor_config.parent / "report.json"
    assert cli.main(["doctor", "--config", str(doctor_config), "--export-report", str(target)]) == 2
    captured = capsys.readouterr()
    assert json.loads(captured.out)["diagnostics"]["status"] == "ok"
    assert "PRIVATE_" not in captured.out + captured.err
    assert "saved locally" not in captured.err
    assert "Unable to create" in captured.err


@pytest.mark.parametrize("other", ["--json", "--explain", "--export-report"])
def test_support_report_cannot_mix_with_another_output_mode(doctor_config, other):
    args = ["doctor", "--config", str(doctor_config), "--support-report", other]
    if other == "--export-report":
        args.append(str(doctor_config.parent / "report.json"))
    with pytest.raises(SystemExit) as error:
        cli.main(args)
    assert error.value.code == 2
