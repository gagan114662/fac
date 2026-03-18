#!/usr/bin/env python3
"""Sync GitHub issues and PRs with Linear project."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional


LINEAR_API = "https://api.linear.app/graphql"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Sync GitHub events to Linear")
    parser.add_argument("--mode", choices=("github-to-linear", "linear-to-github", "sync-status"), required=True)
    parser.add_argument("--team-key", default=os.getenv("LINEAR_TEAM_KEY", "GET"))
    parser.add_argument("--project-name", default=os.getenv("LINEAR_PROJECT_NAME", "NEW ONE"))
    parser.add_argument("--linear-token-env", default="LINEAR_API_KEY")
    parser.add_argument("--github-token-env", default="GITHUB_TOKEN")
    parser.add_argument("--repo", default=os.getenv("GITHUB_REPOSITORY", ""), help="owner/repo")
    parser.add_argument("--branch", default=os.getenv("GITHUB_REF_NAME", ""), help="branch name")
    parser.add_argument("--pr-url", default=os.getenv("LINEAR_SYNC_PR_URL", ""), help="PR URL when available")
    parser.add_argument("--head-sha", default=os.getenv("GITHUB_SHA", ""), help="Current head SHA")
    parser.add_argument("--issue-number", type=int, default=0, help="GitHub issue number")
    parser.add_argument("--issue-title", default="", help="GitHub issue title")
    parser.add_argument("--issue-body", default="", help="GitHub issue body")
    parser.add_argument("--issue-state", default="", help="GitHub issue state (open/closed)")
    parser.add_argument("--state", default="", help="Workflow status name override")
    parser.add_argument("--agent-label", default="agent:codex", help="GitHub label to apply for agent dispatch")
    parser.add_argument("--pr-state", default="", help="PR state (open/closed/merged)")
    parser.add_argument("--pr-merged", default="", help="Whether PR was merged (true/false)")
    parser.add_argument("--out", default="artifacts/linear-sync.json")
    return parser.parse_args()


def _read_json(path: str) -> Dict[str, Any]:
    target = Path(path)
    if not path or not target.exists():
        return {}
    payload = json.loads(target.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def _write_json(path: str, payload: Dict[str, Any]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def gql(token: str, query: str, variables: Dict[str, Any]) -> Dict[str, Any]:
    req = urllib.request.Request(
        LINEAR_API,
        data=json.dumps({"query": query, "variables": variables}).encode("utf-8"),
        headers={
            "Authorization": token,
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if payload.get("errors"):
        raise RuntimeError(json.dumps(payload["errors"]))
    data = payload.get("data")
    return data if isinstance(data, dict) else {}


def team_project_context(token: str, team_key: str, project_name: str, state_name: str) -> Dict[str, str]:
    query = """
    query FacContext($teamKey: String!, $projectName: String!, $stateName: String!) {
      teams(filter: { key: { eq: $teamKey } }) {
        nodes { id key name }
      }
      projects(filter: { name: { eq: $projectName } }) {
        nodes { id name url }
      }
      workflowStates(filter: { name: { eq: $stateName }, team: { key: { eq: $teamKey } } }) {
        nodes { id name type }
      }
    }
    """
    data = gql(token, query, {"teamKey": team_key, "projectName": project_name, "stateName": state_name})
    teams = (((data.get("teams") or {}).get("nodes")) or [])
    projects = (((data.get("projects") or {}).get("nodes")) or [])
    states = (((data.get("workflowStates") or {}).get("nodes")) or [])
    if not teams:
        raise RuntimeError(f"Linear team not found: {team_key}")
    if not projects:
        raise RuntimeError(f"Linear project not found: {project_name}")
    if not states:
        raise RuntimeError(f"Linear workflow state not found: {state_name}")
    return {
        "team_id": teams[0]["id"],
        "project_id": projects[0]["id"],
        "project_url": projects[0].get("url", ""),
        "state_id": states[0]["id"],
    }


def find_issue_by_key(token: str, team_key: str, key: str) -> Optional[Dict[str, Any]]:
    query = """
    query ExistingFacIssue($teamKey: String!, $key: String!) {
      issues(
        first: 1,
        filter: {
          team: { key: { eq: $teamKey } }
          title: { containsIgnoreCase: $key }
        }
      ) {
        nodes {
          id
          identifier
          title
          url
          description
          state { name type }
        }
      }
    }
    """
    data = gql(token, query, {"teamKey": team_key, "key": key})
    nodes = (((data.get("issues") or {}).get("nodes")) or [])
    return nodes[0] if nodes else None


def create_issue(
    token: str,
    *,
    team_id: str,
    project_id: str,
    state_id: str,
    title: str,
    description: str,
    priority: int,
) -> Dict[str, Any]:
    mutation = """
    mutation CreateFacIssue($input: IssueCreateInput!) {
      issueCreate(input: $input) {
        success
        issue { id identifier title url }
      }
    }
    """
    data = gql(
        token,
        mutation,
        {
            "input": {
                "teamId": team_id,
                "projectId": project_id,
                "stateId": state_id,
                "title": title,
                "description": description,
                "priority": priority,
            }
        },
    )
    return ((data.get("issueCreate") or {}).get("issue")) or {}


def update_issue(token: str, issue_id: str, *, state_id: str, description: str, project_id: str) -> Dict[str, Any]:
    mutation = """
    mutation UpdateFacIssue($id: String!, $input: IssueUpdateInput!) {
      issueUpdate(id: $id, input: $input) {
        success
        issue { id identifier title url }
      }
    }
    """
    data = gql(
        token,
        mutation,
        {
            "id": issue_id,
            "input": {
                "stateId": state_id,
                "description": description,
                "projectId": project_id,
            },
        },
    )
    return ((data.get("issueUpdate") or {}).get("issue")) or {}


def create_comment(token: str, issue_id: str, body: str) -> None:
    mutation = """
    mutation AddFacComment($input: CommentCreateInput!) {
      commentCreate(input: $input) {
        success
        comment { id }
      }
    }
    """
    gql(token, mutation, {"input": {"issueId": issue_id, "body": body}})


def sync_github_to_linear(token: str, args: argparse.Namespace) -> List[Dict[str, Any]]:
    state_name = args.state or "Todo"
    context = team_project_context(token, args.team_key, args.project_name, state_name)
    synced: List[Dict[str, Any]] = []

    key = f"github:{args.repo}#{args.issue_number}"
    title = f"[{key}] {args.issue_title[:140]}"
    description = f"GitHub-Key: {key}\n\n{args.issue_body}\n\n- Repo: {args.repo}\n- Issue: #{args.issue_number}"

    existing = find_issue_by_key(token, args.team_key, key)
    if existing:
        issue = update_issue(
            token,
            existing["id"],
            state_id=context["state_id"],
            description=description,
            project_id=context["project_id"],
        )
        create_comment(
            token,
            existing["id"],
            f"Updated from GitHub sync at {dt.datetime.now(dt.timezone.utc).isoformat()}.\n\n- Issue: #{args.issue_number}\n- State: {args.issue_state}",
        )
        synced.append({"action": "updated", "key": key, "issue": issue or existing})
    else:
        issue = create_issue(
            token,
            team_id=context["team_id"],
            project_id=context["project_id"],
            state_id=context["state_id"],
            title=title,
            description=description,
            priority=3,
        )
        synced.append({"action": "created", "key": key, "issue": issue})

    return synced


def get_state_id(token: str, team_key: str, state_name: str) -> str:
    """Look up a single workflow state ID by name."""
    query = """
    query StateId($teamKey: String!, $stateName: String!) {
      workflowStates(filter: { name: { eq: $stateName }, team: { key: { eq: $teamKey } } }) {
        nodes { id name }
      }
    }
    """
    data = gql(token, query, {"teamKey": team_key, "stateName": state_name})
    nodes = (((data.get("workflowStates") or {}).get("nodes")) or [])
    if not nodes:
        raise RuntimeError(f"Workflow state not found: {state_name}")
    return nodes[0]["id"]


def get_todo_issues(token: str, team_key: str, project_name: str) -> List[Dict[str, Any]]:
    """Fetch issues in 'Todo' state from the given project."""
    query = """
    query TodoIssues($teamKey: String!, $projectName: String!) {
      issues(
        first: 50
        filter: {
          team: { key: { eq: $teamKey } }
          project: { name: { eq: $projectName } }
          state: { name: { eq: "Todo" } }
        }
        orderBy: createdAt
      ) {
        nodes {
          id identifier title url description
          state { name type }
          labels { nodes { name } }
          priority
        }
      }
    }
    """
    data = gql(token, query, {"teamKey": team_key, "projectName": project_name})
    return (((data.get("issues") or {}).get("nodes")) or [])


def update_issue_state(token: str, issue_id: str, state_id: str) -> Dict[str, Any]:
    """Update only the state of a Linear issue."""
    mutation = """
    mutation UpdateState($id: String!, $input: IssueUpdateInput!) {
      issueUpdate(id: $id, input: $input) {
        success
        issue { id identifier title url state { name } }
      }
    }
    """
    data = gql(token, mutation, {"id": issue_id, "input": {"stateId": state_id}})
    return ((data.get("issueUpdate") or {}).get("issue")) or {}


def create_github_issue(github_token: str, repo: str, title: str, body: str, labels: List[str]) -> Dict[str, Any]:
    """Create a GitHub issue via REST API."""
    url = f"https://api.github.com/repos/{repo}/issues"
    payload = json.dumps({"title": title, "body": body, "labels": labels}).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=payload,
        headers={
            "Authorization": f"token {github_token}",
            "Accept": "application/vnd.github+json",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def sync_linear_to_github(token: str, args: argparse.Namespace) -> List[Dict[str, Any]]:
    """Poll Linear for Todo issues and create GitHub issues with agent label."""
    github_token = os.getenv(args.github_token_env, "").strip()
    if not github_token:
        raise RuntimeError(f"missing GitHub token in env var: {args.github_token_env}")
    if not args.repo:
        raise RuntimeError("--repo is required for linear-to-github mode")

    todo_issues = get_todo_issues(token, args.team_key, args.project_name)
    ai_delegated_id = get_state_id(token, args.team_key, "AI Delegated")
    synced: List[Dict[str, Any]] = []

    for issue in todo_issues:
        linear_id = issue["identifier"]
        # Skip if already synced (description contains "GitHub-Issue:")
        desc = issue.get("description") or ""
        if "GitHub-Issue:" in desc:
            continue

        title = f"[{linear_id}] {issue['title'][:200]}"
        body = (
            f"Linear: [{linear_id}]({issue['url']})\n\n"
            f"{desc}\n\n"
            f"---\n"
            f"_Synced from Linear project **{args.project_name}**_"
        )

        # Create GitHub issue with agent label
        gh_issue = create_github_issue(
            github_token, args.repo, title, body, [args.agent_label],
        )
        gh_number = gh_issue.get("number", 0)
        gh_url = gh_issue.get("html_url", "")

        # Move Linear issue to "AI Delegated" and comment with GitHub link
        update_issue_state(token, issue["id"], ai_delegated_id)
        create_comment(
            token,
            issue["id"],
            f"Delegated to AI agent via GitHub.\n\n"
            f"- GitHub Issue: [{args.repo}#{gh_number}]({gh_url})\n"
            f"- Agent: `{args.agent_label}`\n"
            f"- Time: {dt.datetime.now(dt.timezone.utc).isoformat()}",
        )

        synced.append({
            "action": "delegated",
            "linear_id": linear_id,
            "linear_url": issue["url"],
            "github_number": gh_number,
            "github_url": gh_url,
            "agent_label": args.agent_label,
        })

    return synced


def sync_pr_status(token: str, args: argparse.Namespace) -> List[Dict[str, Any]]:
    """Update Linear issue status based on PR events."""
    synced: List[Dict[str, Any]] = []
    branch = args.branch

    # Extract issue number from agent branch names: codex/issue-N or claude/issue-N
    import re
    match = re.match(r"(?:codex|claude)/issue-(\d+)", branch)
    if not match:
        return synced  # Not an agent branch, nothing to sync

    gh_issue_number = int(match.group(1))

    # Read the GitHub issue to find the Linear identifier
    github_token = os.getenv(args.github_token_env, "").strip()
    if not github_token or not args.repo:
        return synced

    gh_url = f"https://api.github.com/repos/{args.repo}/issues/{gh_issue_number}"
    req = urllib.request.Request(
        gh_url,
        headers={
            "Authorization": f"token {github_token}",
            "Accept": "application/vnd.github+json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as response:
            gh_issue = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError:
        return synced

    gh_title = gh_issue.get("title", "")
    # Extract Linear ID from title: [GET-123] ...
    linear_match = re.match(r"\[(GET-\d+)\]", gh_title)
    if not linear_match:
        return synced

    linear_identifier = linear_match.group(1)

    # Find the Linear issue
    existing = find_issue_by_key(token, args.team_key, linear_identifier)
    if not existing:
        return synced

    # Determine target state based on PR event
    pr_merged = args.pr_merged.lower() == "true"
    if pr_merged:
        target_state = "Done"
    else:
        target_state = "In Review"

    state_id = get_state_id(token, args.team_key, target_state)
    updated = update_issue_state(token, existing["id"], state_id)

    # Add comment about PR status
    status_text = "merged" if pr_merged else "opened"
    create_comment(
        token,
        existing["id"],
        f"PR {status_text}.\n\n"
        f"- PR: {args.pr_url}\n"
        f"- Branch: `{branch}`\n"
        f"- SHA: `{args.head_sha[:8]}`\n"
        f"- Status: **{target_state}**\n"
        f"- Time: {dt.datetime.now(dt.timezone.utc).isoformat()}",
    )

    synced.append({
        "action": f"status_{status_text}",
        "linear_id": linear_identifier,
        "linear_url": existing.get("url", ""),
        "target_state": target_state,
        "pr_url": args.pr_url,
    })

    return synced


def main() -> int:
    args = parse_args()
    token = os.getenv(args.linear_token_env, "").strip()

    result: Dict[str, Any] = {
        "mode": args.mode,
        "team_key": args.team_key,
        "project_name": args.project_name,
        "repo": args.repo,
        "branch": args.branch,
        "head_sha": args.head_sha,
        "pr_url": args.pr_url,
        "synced": [],
        "status": "missing",
        "errors": [],
    }

    if not token:
        result["errors"].append(f"missing Linear token in env var: {args.linear_token_env}")
        _write_json(args.out, result)
        return 0

    try:
        if args.mode == "github-to-linear":
            result["synced"] = sync_github_to_linear(token, args)
        elif args.mode == "linear-to-github":
            result["synced"] = sync_linear_to_github(token, args)
        elif args.mode == "sync-status":
            result["synced"] = sync_pr_status(token, args)
        result["status"] = "success"
        _write_json(args.out, result)
        return 0
    except urllib.error.HTTPError as exc:
        result["status"] = "error"
        result["errors"].append(f"Linear API HTTP error: {exc.code}")
    except urllib.error.URLError as exc:
        result["status"] = "error"
        result["errors"].append(f"Linear API connection error: {exc.reason}")
    except Exception as exc:
        result["status"] = "error"
        result["errors"].append(str(exc))

    _write_json(args.out, result)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
