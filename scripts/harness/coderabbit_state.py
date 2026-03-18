#!/usr/bin/env python3
"""GitHub check-run polling and review finding normalization for CodeRabbit."""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class ReviewState:
    provider: str
    status: str
    details: str
    check_run_url: str = ""


def _api_get_json(url: str, token: str) -> Dict[str, Any]:
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "Authorization": f"Bearer {token}",
    }
    req = urllib.request.Request(url, headers=headers, method="GET")
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def list_check_runs(repo: str, sha: str, token: str) -> List[Dict[str, Any]]:
    url = f"https://api.github.com/repos/{repo}/commits/{sha}/check-runs?per_page=100"
    payload = _api_get_json(url, token)
    return payload.get("check_runs", [])


def _find_check_run(check_runs: List[Dict[str, Any]], check_name: str) -> Optional[Dict[str, Any]]:
    matches = [run for run in check_runs if run.get("name") == check_name]
    if not matches:
        return None
    matches.sort(key=lambda run: run.get("id", 0), reverse=True)
    return matches[0]


def get_review_check_state_once(
    repo: str,
    sha: str,
    token: str,
    check_name: str,
    provider: str = "coderabbit",
) -> ReviewState:
    try:
        runs = list_check_runs(repo, sha, token)
        run = _find_check_run(runs, check_name)

        if run is None:
            return ReviewState(
                provider=provider,
                status="missing",
                details=f"check run '{check_name}' not found for head SHA {sha}",
            )

        status = str(run.get("status", ""))
        conclusion = str(run.get("conclusion", ""))
        details_url = str(run.get("html_url", ""))
        summary = str(run.get("output", {}).get("summary", "")).strip()
        title = str(run.get("output", {}).get("title", "")).strip()
        details = summary or title or f"status={status}, conclusion={conclusion}"

        if status != "completed":
            return ReviewState(
                provider=provider,
                status="pending",
                details=f"check '{check_name}' still {status}",
                check_run_url=details_url,
            )

        if conclusion in {"success", "neutral", "skipped"}:
            return ReviewState(provider=provider, status="success", details=details, check_run_url=details_url)

        if conclusion in {"timed_out"}:
            return ReviewState(provider=provider, status="timeout", details=details, check_run_url=details_url)

        return ReviewState(provider=provider, status="failure", details=details, check_run_url=details_url)

    except urllib.error.HTTPError as exc:
        return ReviewState(
            provider=provider,
            status="error",
            details=f"GitHub API HTTP error while reading check runs: {exc.code}",
        )
    except urllib.error.URLError as exc:
        return ReviewState(
            provider=provider,
            status="error",
            details=f"GitHub API connection error while reading check runs: {exc.reason}",
        )
    except Exception as exc:  # pragma: no cover
        return ReviewState(provider=provider, status="error", details=f"unexpected review-state error: {exc}")


def wait_for_review_check(
    repo: str,
    sha: str,
    token: str,
    check_name: str,
    timeout_minutes: int = 15,
    poll_seconds: int = 20,
    provider: str = "coderabbit",
) -> ReviewState:
    deadline = time.time() + (timeout_minutes * 60)
    last_state = ReviewState(provider=provider, status="missing", details="")

    while time.time() < deadline:
        state = get_review_check_state_once(
            repo=repo,
            sha=sha,
            token=token,
            check_name=check_name,
            provider=provider,
        )
        last_state = state

        if state.status == "pending" or state.status == "missing":
            time.sleep(poll_seconds)
            continue

        return state

    return ReviewState(
        provider=provider,
        status="timeout",
        details=last_state.details or "review check timeout",
        check_run_url=last_state.check_run_url,
    )


def _is_actionable_from_heuristic(
    finding: Dict[str, Any], weak_confidence_threshold: float, actionable_keywords: List[str]
) -> bool:
    severity = str(finding.get("severity", "")).lower()
    summary = str(finding.get("summary", "")).lower()
    confidence = float(finding.get("confidence", 0.0) or 0.0)

    if severity in {"critical", "high"}:
        return True

    keyword_hit = any(keyword.lower() in summary for keyword in actionable_keywords)
    if keyword_hit:
        return True

    return confidence >= weak_confidence_threshold and severity in {"medium", "high", "critical"}


def load_or_init_review_findings(
    findings_path: str,
    *,
    head_sha: str,
    provider: str,
    weak_confidence_threshold: float,
    actionable_keywords: List[str],
) -> Dict[str, Any]:
    path = Path(findings_path)

    if path.exists():
        payload = json.loads(path.read_text(encoding="utf-8"))
    else:
        payload = {
            "head_sha": head_sha,
            "provider": provider,
            "status": "missing",
            "findings": [],
        }

    payload.setdefault("head_sha", head_sha)
    payload.setdefault("provider", provider)
    payload.setdefault("status", "missing")
    payload.setdefault("findings", [])

    normalized_findings: List[Dict[str, Any]] = []
    for idx, finding in enumerate(payload.get("findings", []), start=1):
        normalized = {
            "id": str(finding.get("id", f"finding-{idx}")),
            "severity": str(finding.get("severity", "medium")).lower(),
            "confidence": float(finding.get("confidence", 0.0) or 0.0),
            "path": str(finding.get("path", "")),
            "line": int(finding.get("line", 1) or 1),
            "summary": str(finding.get("summary", "")),
            "actionable": bool(
                finding.get(
                    "actionable",
                    _is_actionable_from_heuristic(
                        finding,
                        weak_confidence_threshold=weak_confidence_threshold,
                        actionable_keywords=actionable_keywords,
                    ),
                )
            ),
        }
        normalized_findings.append(normalized)

    payload["findings"] = normalized_findings
    return payload


def count_actionable_findings(review_findings: Dict[str, Any]) -> int:
    findings = review_findings.get("findings", [])
    return sum(1 for finding in findings if bool(finding.get("actionable")))


def write_review_findings(findings_path: str, review_findings: Dict[str, Any]) -> None:
    path = Path(findings_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(review_findings, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def review_state_as_dict(state: ReviewState) -> Dict[str, Any]:
    return {
        "provider": state.provider,
        "status": state.status,
        "details": state.details,
        "check_run_url": state.check_run_url,
    }
