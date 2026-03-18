#!/usr/bin/env python3
"""Post a single canonical review-rerun comment per head SHA."""

from __future__ import annotations

import argparse
import json
import os
import urllib.request
from pathlib import Path
from typing import Any, Dict, List


def _request_json(url: str, token: str, method: str = "GET", payload: Dict[str, Any] | None = None) -> Dict[str, Any]:
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "Authorization": f"Bearer {token}",
    }
    data = None
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"

    req = urllib.request.Request(url, headers=headers, method=method, data=data)
    with urllib.request.urlopen(req, timeout=30) as resp:
        body = resp.read().decode("utf-8")
        if not body:
            return {}
        return json.loads(body)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Post deduplicated rerun comment")
    parser.add_argument("--repo", required=True, help="owner/repo")
    parser.add_argument("--pr-number", type=int, required=True, help="Pull request number")
    parser.add_argument("--head-sha", required=True, help="Current head SHA")
    parser.add_argument("--token-env", default="GITHUB_TOKEN", help="Environment variable with GitHub token")
    parser.add_argument("--marker", default="<!-- coderabbit-auto-rerun -->", help="Deduplication marker")
    parser.add_argument("--message", default="@coderabbitai full review", help="Comment message")
    parser.add_argument("--out", default="artifacts/rerun-comment-result.json", help="Output result path")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    token = os.getenv(args.token_env, "")

    result: Dict[str, Any] = {
        "repo": args.repo,
        "pr_number": args.pr_number,
        "head_sha": args.head_sha,
        "posted": False,
        "deduped": False,
        "comment_url": "",
        "error": "",
    }

    if not token:
        result["error"] = f"missing token in env var {args.token_env}"
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(json.dumps(result, indent=2, sort_keys=True))
        return 1

    trigger = f"sha:{args.head_sha}"
    comments_url = f"https://api.github.com/repos/{args.repo}/issues/{args.pr_number}/comments?per_page=100"

    comments: List[Dict[str, Any]] = _request_json(comments_url, token)
    for comment in comments:
        body = str(comment.get("body", ""))
        if args.marker in body and trigger in body:
            result["deduped"] = True
            result["comment_url"] = str(comment.get("html_url", ""))
            break

    if not result["deduped"]:
        post_url = f"https://api.github.com/repos/{args.repo}/issues/{args.pr_number}/comments"
        body = f"{args.marker}\n{args.message}\n{trigger}"
        posted = _request_json(post_url, token, method="POST", payload={"body": body})
        result["posted"] = True
        result["comment_url"] = str(posted.get("html_url", ""))

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
