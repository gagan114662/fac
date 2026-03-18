#!/usr/bin/env python3
"""Validate browser evidence manifests without third-party dependencies."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple


def _iso_datetime(value: str) -> bool:
    try:
        dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
        return True
    except Exception:
        return False


def _validate_required_fields(payload: Dict[str, Any], errors: List[str]) -> None:
    required = ["head_sha", "captured_at", "flows", "artifacts", "assertions"]
    for field in required:
        if field not in payload:
            errors.append(f"missing required field '{field}'")


def _validate_artifacts(manifest_path: Path, artifacts: Sequence[Dict[str, Any]], errors: List[str]) -> None:
    for idx, artifact in enumerate(artifacts, start=1):
        label = f"artifact[{idx}]"
        for field in ["path", "sha256", "size_bytes"]:
            if field not in artifact:
                errors.append(f"{label}: missing '{field}'")

        rel_path = str(artifact.get("path", ""))
        expected_hash = str(artifact.get("sha256", "")).lower()
        expected_size = artifact.get("size_bytes", 0)

        if len(expected_hash) != 64 or any(ch not in "0123456789abcdef" for ch in expected_hash):
            errors.append(f"{label}: invalid sha256 '{expected_hash}'")

        if not isinstance(expected_size, int) or expected_size <= 0:
            errors.append(f"{label}: invalid size_bytes '{expected_size}'")

        if not rel_path:
            continue

        file_path = (manifest_path.parent / rel_path).resolve()
        if not file_path.exists() or not file_path.is_file():
            errors.append(f"{label}: artifact path does not exist: {rel_path}")
            continue

        actual_size = file_path.stat().st_size
        if actual_size != expected_size:
            errors.append(f"{label}: size mismatch for {rel_path} (expected {expected_size}, got {actual_size})")

        digest = hashlib.sha256(file_path.read_bytes()).hexdigest().lower()
        if expected_hash and digest != expected_hash:
            errors.append(f"{label}: sha256 mismatch for {rel_path}")


def verify_manifest(
    manifest_path: str,
    *,
    head_sha: Optional[str] = None,
    required_flows: Optional[Sequence[str]] = None,
    required_assertions: Optional[Sequence[str]] = None,
) -> Tuple[bool, List[str], Dict[str, Any]]:
    errors: List[str] = []
    path = Path(manifest_path)

    if not path.exists():
        return False, [f"manifest not found at {manifest_path}"], {}

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return False, [f"manifest is not valid JSON: {exc}"], {}

    if not isinstance(payload, dict):
        return False, ["manifest root must be a JSON object"], {}

    _validate_required_fields(payload, errors)

    if "captured_at" in payload and not _iso_datetime(str(payload.get("captured_at"))):
        errors.append("captured_at must be ISO-8601 timestamp")

    flows = payload.get("flows", [])
    if not isinstance(flows, list) or not all(isinstance(flow, str) for flow in flows):
        errors.append("flows must be an array of strings")
        flows = []

    assertions = payload.get("assertions", [])
    if not isinstance(assertions, list):
        errors.append("assertions must be an array")
        assertions = []

    artifacts = payload.get("artifacts", [])
    if not isinstance(artifacts, list):
        errors.append("artifacts must be an array")
        artifacts = []

    if head_sha and str(payload.get("head_sha", "")) != head_sha:
        errors.append(f"head_sha mismatch (expected {head_sha}, got {payload.get('head_sha')})")

    required_flows = list(required_flows or [])
    for flow in required_flows:
        if flow not in flows:
            errors.append(f"required flow missing: {flow}")

    assertion_map = {str(item.get("name", "")): str(item.get("status", "")).lower() for item in assertions if isinstance(item, dict)}
    required_assertions = list(required_assertions or [])
    for name in required_assertions:
        status = assertion_map.get(name)
        if status is None:
            errors.append(f"required assertion missing: {name}")
        elif status != "pass":
            errors.append(f"required assertion not passing: {name} ({status})")

    for idx, assertion in enumerate(assertions, start=1):
        if not isinstance(assertion, dict):
            errors.append(f"assertion[{idx}] must be an object")
            continue
        if "name" not in assertion or "status" not in assertion or "details" not in assertion:
            errors.append(f"assertion[{idx}] missing name/status/details")
            continue
        status = str(assertion.get("status", "")).lower()
        if status not in {"pass", "fail"}:
            errors.append(f"assertion[{idx}] has invalid status '{status}'")

    typed_artifacts = [artifact for artifact in artifacts if isinstance(artifact, dict)]
    _validate_artifacts(path, typed_artifacts, errors)

    return len(errors) == 0, errors, payload


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Verify browser evidence manifest")
    parser.add_argument("--manifest", required=True, help="Path to browser-evidence-manifest.json")
    parser.add_argument("--head-sha", default="", help="Expected current head SHA")
    parser.add_argument("--required-flow", action="append", default=[], help="Flow that must exist (repeatable)")
    parser.add_argument(
        "--required-assertion",
        action="append",
        default=[],
        help="Assertion name that must exist with pass status (repeatable)",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    ok, errors, payload = verify_manifest(
        args.manifest,
        head_sha=args.head_sha or None,
        required_flows=args.required_flow,
        required_assertions=args.required_assertion,
    )

    result = {
        "ok": ok,
        "errors": errors,
        "manifest": payload,
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
