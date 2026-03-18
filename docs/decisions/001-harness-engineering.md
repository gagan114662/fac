# ADR 001: Harness Engineering for Deterministic PR Agent Loop

## Status

Accepted

## Context

We need a deterministic, machine-verifiable review pipeline for PRs created by AI coding agents (Codex, Claude). The system must:

1. Classify PRs by risk tier based on changed files
2. Enforce review state from an automated reviewer (CodeRabbit)
3. Run CI checks proportional to risk
4. Support progressive rollout (advisory → enforced → full loop)
5. Be observable via Sentry

## Decisions

### Python for CI Scripts

**Decision:** Use Python (stdlib only, no pip dependencies) for all CI harness scripts.

**Rationale:** Battle-tested from open_fang. Python runs natively on GitHub Actions runners without installation. The stdlib provides everything needed (urllib, json, argparse, fnmatch). No dependency management overhead in CI.

### CodeRabbit over Greptile

**Decision:** Use CodeRabbit as the primary automated code reviewer.

**Rationale:** CodeRabbit has native GitHub integration, better Elixir support, and provides review comments as GitHub review threads (enabling auto-resolve of bot-only threads). The review can be triggered via `@coderabbitai full review` comments.

### Contract-Driven Policy

**Decision:** A single `harness/contract.json` file defines all policy — risk tiers, required checks, rollout phase, review configuration.

**Rationale:** Machine-readable, versionable, consumed by both Python scripts and Elixir runtime. Changes to policy are code-reviewed just like any other change. Enables progressive rollout without code changes.

### Codex Primary, Claude Backup

**Decision:** Codex is the primary coding agent (via `agent:codex` label), Claude is backup (via `agent:claude` label or assignment).

**Rationale:** Codex sandbox provides safer execution for routine tasks. Claude provides stronger reasoning for complex issues. Both produce PRs that go through the same deterministic review loop.

### Workflow Dependency Chain

**Decision:** All downstream workflows trigger via `workflow_run` on `risk-policy-gate` completion, not directly on PR events.

**Rationale:** Ensures risk classification happens first and all downstream workflows have access to the risk-policy-report artifact. Prevents race conditions between risk assessment and CI execution.

### Progressive Rollout Phases

**Decision:** Three phases: phase-0 (advisory), phase-1 (enforce), phase-2 (full loop with remediation + evidence).

**Rationale:** Allows safe deployment. Phase-0 runs everything but doesn't block merges. Phase-1 enforces merge blocks. Phase-2 adds automated remediation and browser evidence requirements.

## Consequences

- All PR policy decisions are traceable to `harness/contract.json`
- CI scripts have no external dependencies (reproducible across environments)
- Risk classification is deterministic and auditable
- Rollout can be advanced by editing a single JSON field
- CodeRabbit integration requires the CodeRabbit GitHub App installed on the repo
