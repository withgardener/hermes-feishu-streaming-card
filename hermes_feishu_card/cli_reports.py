"""Read-only CLI reports, independent of command execution and process control."""
from __future__ import annotations

from typing import Any, TYPE_CHECKING

from .diagnostics import DiagnosticReport, safe_event_endpoint_for_output

if TYPE_CHECKING:
    from .install.detect import HermesDetection


def format_route_chain(report: DiagnosticReport | dict[str, Any]) -> str:
    if isinstance(report, DiagnosticReport):
        routing = report.routing
        finding_codes = [finding.code for finding in report.findings]
    else:
        routing = report.get("routing", {})
        recommendations = report.get("recommendations", [])
        finding_codes = [
            str(item.get("code") or "")
            for item in recommendations
            if isinstance(item, dict)
        ]
    profile_id = str(routing.get("profile_id") or "")
    profile_exists = bool(routing.get("profile_exists"))
    endpoint = safe_event_endpoint_for_output(
        str(routing.get("event_endpoint") or "")
    )
    lines = [
        "Route Chain",
        f"- identity_source: {routing.get('profile_source') or 'unknown'}",
        f"- profile_id: {profile_id or 'missing'}",
        f"- event_endpoint: {endpoint or 'missing'}",
        f"- config_profile: {profile_id if profile_exists else 'missing'}",
        f"- bot_id: {routing.get('bot_id') or 'missing'}",
        f"- route_reason: {routing.get('route_reason') or 'missing'}",
    ]
    route_codes = {
        "profile_identity_missing",
        "profile_unknown",
        "profile_credentials_missing",
        "event_endpoint_mismatch",
        "bot_unknown",
        "route_fallback",
    }
    findings = [code for code in finding_codes if code in route_codes]
    if findings:
        lines.append(f"- findings: {', '.join(findings)}")
    return "\n".join(lines)


def exact_delivery_contract_status(detection: HermesDetection) -> str:
    if not detection.base_required:
        return "not_required"
    if detection.capabilities.get("exact_base_delivery") is True:
        return "ready"
    return "missing_or_unsupported"


def doctor_exit_code(report: dict[str, Any]) -> int:
    return 1 if report.get("status") == "error" else 0


def format_doctor_explanation(report: dict[str, Any]) -> str:
    config = report["config"]
    lines = ["Doctor Summary"]
    if config.get("loaded"):
        lines.append(f"- Config: OK ({config['path']})")
        lines.append(f"- Sidecar: {report['sidecar']['address']}")
    else:
        lines.append(f"- Config: ERROR ({config['path']})")
        lines.append(f"- Error: {config.get('error', 'unknown')}")

    hermes = report["hermes"]
    hermes_status = hermes["status"]
    if hermes.get("checked"):
        details = []
        if hermes.get("version"):
            details.append(str(hermes["version"]))
        if hermes.get("hook_strategy"):
            details.append(str(hermes["hook_strategy"]))
        if hermes.get("compatibility"):
            details.append(f"compatibility {hermes['compatibility']}")
        suffix = f" ({', '.join(details)})" if details else ""
        lines.append(f"- Hermes: {hermes_status}{suffix}")
        exact_contract = hermes.get("exact_delivery_contract")
        if exact_contract:
            lines.append(f"- Exact delivery contract: {exact_contract}")
    else:
        lines.append(f"- Hermes: {hermes_status}")

    runtime_import = report.get("runtime_import", {})
    if runtime_import.get("status"):
        lines.append(
            f"- Runtime import: {runtime_import['status']} - "
            f"{runtime_import.get('message', '')}"
        )

    feishu_sdk = report.get("feishu_sdk", {})
    if isinstance(feishu_sdk, dict) and feishu_sdk.get("status"):
        lines.append(
            f"- Feishu SDK: {feishu_sdk['status']} - "
            f"{feishu_sdk.get('message', '')}"
        )

    streaming = report["streaming"]
    if streaming.get("status"):
        lines.append(
            f"- Streaming: {streaming['status']} - {streaming.get('message', '')}"
        )

    install_state = report["install_state"]
    if install_state.get("status"):
        lines.append(
            f"- Install state: {install_state['status']} - "
            f"{install_state.get('message', '')}"
        )

    lines.append("")
    lines.append("Next steps")
    recommendations = report.get("recommendations", [])
    if not recommendations:
        lines.append("- No action required.")
        return "\n".join(lines)
    for item in recommendations:
        severity = item.get("severity", "info")
        message = item.get("message", "")
        next_step = item.get("next_step", "")
        lines.append(f"- [{severity}] {message}")
        if next_step:
            lines.append(f"  Next: {next_step}")
    return "\n".join(lines)


def format_hermes_detection(detection: HermesDetection) -> str:
    status = "supported" if detection.supported else "unsupported"
    run_py_exists = "yes" if detection.run_py_exists else "no"
    version = detection.version
    if (
        detection.supported
        and version == "unknown"
        and detection.version_source == "gateway anchors"
    ):
        version = "unknown (source-stripped metadata)"
    lines = [
        f"hermes: {status}",
        f"hermes_root: {detection.root}",
        f"run_py: {detection.run_py}",
        f"run_py_exists: {run_py_exists}",
        f"cron_py: {detection.cron_py}",
        f"cron_py_exists: {'yes' if detection.cron_py_exists else 'no'}",
        f"version_source: {detection.version_source}",
        f"version: {version}",
        f"minimum_supported_version: {detection.minimum_version}",
        f"hook_strategy: {detection.hook_strategy}",
        f"cron_hook_strategy: {detection.cron_hook_strategy}",
        f"base_py: {detection.base_py}",
        f"base_py_exists: {'yes' if detection.base_py_exists else 'no'}",
        f"base_required: {'yes' if detection.base_required else 'no'}",
        f"base_hook_strategy: {detection.base_hook_strategy}",
        f"exact_delivery_contract: {exact_delivery_contract_status(detection)}",
        f"compatibility: {detection.compatibility}",
        f"suggested_root: {detection.suggested_root or ''}",
        f"suggestion_reason: {detection.suggestion_reason}",
        "anchors:",
    ]
    for capability, found in detection.capabilities.items():
        anchor_status = "found" if found else "missing"
        locations = ", ".join(detection.capability_locations.get(capability, ()))
        lines.append(f"  {capability}: {anchor_status}" + (f" ({locations})" if locations else ""))
    lines.append(f"reason: {detection.reason}")
    return "\n".join(lines)

