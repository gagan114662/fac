#!/usr/bin/env python3
"""Build PR acceptance packet with checklist, validation artifacts & media embeds."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List, Tuple

from browser_evidence_verify import verify_manifest


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate PR review packet")
    parser.add_argument("--contract", default="harness/contract.json", help="Harness contract path")
    parser.add_argument("--risk-report", default="artifacts/risk-policy-report.json", help="Risk gate report path")
    parser.add_argument("--review-findings", default="artifacts/review-findings.json", help="Review findings")
    parser.add_argument("--browser-evidence-manifest", default="artifacts/browser-evidence-manifest.json",
                        help="Browser evidence manifest path")
    parser.add_argument("--sentry-validation-report", default="artifacts/sentry-logs-validation.json",
                        help="Sentry validation report path")
    parser.add_argument("--media-manifest", default="artifacts/media-manifest.json",
                        help="Media manifest JSON for embedded screenshots/videos")
    parser.add_argument("--out-json", default="artifacts/pr-review-packet.json", help="Output packet JSON")
    parser.add_argument("--out-md", default="artifacts/pr-review-packet.md", help="Output packet markdown")
    return parser.parse_args()


def _read_json(path: str) -> Dict[str, Any]:
    target = Path(path)
    if not target.exists():
        return {}
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}


def _write_file(path: str, content: str) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")


def _provider_ok(payload: Dict[str, Any]) -> Tuple[bool, int, str]:
    status = str(payload.get("status", "missing")).lower()
    findings = payload.get("findings", [])
    actionable_count = 0
    if isinstance(findings, list):
        actionable_count = sum(1 for f in findings if isinstance(f, dict) and bool(f.get("actionable")))
    ok = status == "success" and actionable_count == 0
    return ok, actionable_count, status


def _build_artifact_table(args: argparse.Namespace, risk_decision: str, review_status: str,
                          browser_ok: bool) -> List[str]:
    rows = [
        ("Risk policy report", args.risk_report, risk_decision),
        ("Review findings", args.review_findings, review_status),
        ("Evidence manifest", args.browser_evidence_manifest, "ok" if browser_ok else "missing"),
        ("PR review packet", args.out_json, "generated"),
    ]
    lines = [
        "",
        "## Validation Artifacts",
        "",
        "| Artifact | Path | Status |",
        "|----------|------|--------|",
    ]
    for name, path, status in rows:
        lines.append(f"| {name} | `{path}` | {status} |")
    return lines


def _build_media_section(media_manifest: Dict[str, Any]) -> List[str]:
    items = media_manifest.get("items", [])
    if not items:
        return [
            "",
            "## Execution Evidence",
            "",
            "_No media attachments provided._",
        ]

    lines = [
        "",
        "## Execution Evidence",
        "",
        "> Media attached by harness automation. Expand to view.",
        "",
        "<details><summary>Screenshots & Recordings</summary>",
        "",
    ]

    for item in items:
        item_type = str(item.get("type", "")).lower()
        if item_type == "screenshot":
            label = item.get("label", "screenshot")
            path = item.get("path", "")
            url = item.get("url", path)
            lines.append(f"![{label}]({url})")
            lines.append("")
        elif item_type == "loom":
            url = item.get("url", "")
            thumbnail = item.get("thumbnail", "")
            if thumbnail:
                lines.append(f"[![Loom recording]({thumbnail})]({url})")
            else:
                lines.append(f"[Loom recording]({url})")
            lines.append("")
        elif item_type == "asciinema":
            url = item.get("url", "")
            svg_url = url.rstrip("/") + ".svg" if url and not url.endswith(".svg") else url
            lines.append(f"[![asciicast]({svg_url})]({url})")
            lines.append("")
        elif item_type == "video":
            label = item.get("label", "video")
            url = item.get("url", item.get("path", ""))
            lines.append(f"[{label}]({url})")
            lines.append("")

    lines.append("</details>")
    return lines


def _build_markdown(checklist: List[Dict[str, Any]], artifact_lines: List[str],
                    media_lines: List[str]) -> str:
    lines: List[str] = []
    lines.append("<!-- pr-review-checklist:start -->")
    lines.append("## Acceptance Criteria")
    lines.append("")
    for item in checklist:
        mark = "x" if item["passed"] else " "
        lines.append(f"- [{mark}] {item['label']} ({item['details']})")
    lines.extend(artifact_lines)
    lines.extend(media_lines)
    lines.append("")
    lines.append("<!-- pr-review-checklist:end -->")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    args = parse_args()

    contract = _read_json(args.contract)
    risk_report = _read_json(args.risk_report)
    review_findings = _read_json(args.review_findings)
    sentry_report = _read_json(args.sentry_validation_report)
    media_manifest = _read_json(args.media_manifest)

    evidence_policy = contract.get("evidencePolicy", {})
    if not isinstance(evidence_policy, dict):
        evidence_policy = {}
    head_sha = str(risk_report.get("head_sha", ""))
    risk_decision = str(risk_report.get("decision", "fail")).lower()

    review_ok, review_actionable, review_status = _provider_ok(review_findings)

    browser_ok = True
    browser_details = "not provided"
    if Path(args.browser_evidence_manifest).exists():
        browser_ok, browser_errors, _ = verify_manifest(
            args.browser_evidence_manifest,
            head_sha=head_sha or None,
            required_flows=evidence_policy.get("requiredFlows", []),
            required_assertions=evidence_policy.get("requiredAssertions", []),
        )
        browser_details = "ok" if browser_ok else "; ".join(browser_errors)

    sentry_required = "sentry-live-validate" in risk_report.get("required_checks", [])
    sentry_status = str(sentry_report.get("status", "missing")).lower()
    sentry_ok = (not sentry_required) or (sentry_status == "pass" and bool(sentry_report.get("ok", False)))

    checklist = [
        {
            "id": "risk_policy_pass",
            "label": "Risk policy gate passed on current head",
            "passed": risk_decision == "pass",
            "details": risk_decision,
        },
        {
            "id": "coderabbit_clean",
            "label": "CodeRabbit review clean",
            "passed": review_ok,
            "details": f"status={review_status}, actionable={review_actionable}",
        },
        {
            "id": "browser_evidence",
            "label": "Browser execution evidence verified",
            "passed": browser_ok,
            "details": browser_details,
        },
        {
            "id": "ci_pipeline",
            "label": "CI pipeline passed (compile, test, credo, format)",
            "passed": risk_decision == "pass",
            "details": "inferred from risk gate",
        },
        {
            "id": "sentry_live_validation",
            "label": "Sentry live validation passed",
            "passed": sentry_ok,
            "details": "not required" if not sentry_required else sentry_status,
        },
    ]

    all_passed = all(item["passed"] for item in checklist)

    artifact_lines = _build_artifact_table(args, risk_decision, review_status, browser_ok)
    media_lines = _build_media_section(media_manifest)

    packet = {
        "head_sha": head_sha,
        "pr_number": risk_report.get("pr_number"),
        "risk_tier": risk_report.get("risk_tier"),
        "required_checks": risk_report.get("required_checks", []),
        "review_provider": {
            "status": review_status,
            "actionable": review_actionable,
        },
        "browser_evidence": {
            "ok": browser_ok,
            "manifest": args.browser_evidence_manifest,
        },
        "sentry_live_validation": {
            "required": sentry_required,
            "status": sentry_status,
            "ok": sentry_ok,
        },
        "media_manifest": args.media_manifest,
        "checklist": checklist,
        "all_passed": all_passed,
    }

    markdown = _build_markdown(checklist, artifact_lines, media_lines)
    _write_file(args.out_json, json.dumps(packet, indent=2, sort_keys=True) + "\n")
    _write_file(args.out_md, markdown)

    print(json.dumps(packet, indent=2, sort_keys=True))
    return 0 if all_passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
