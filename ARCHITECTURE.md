# Architecture — fac

## Overview

fac is a Phoenix/Elixir web application with an integrated control-plane for deterministic PR agent loops. AI coding agents (Codex, Claude) pick up issues, write code, and open PRs that pass through a machine-verifiable review pipeline before human merge.

## System Components

### 1. Phoenix Web Application (`lib/`)

Standard Phoenix 1.8 app with:
- **Contexts** (`lib/fac/`) — Business logic modules
- **Harness** (`lib/fac/harness/`) — Runtime risk classification and evidence validation
- **Web** (`lib/fac_web/`) — Controllers, views, router, endpoint

### 2. Harness Contract (`harness/contract.json`)

Machine-readable JSON contract that defines:
- **Risk tier rules** — Glob patterns mapping file paths to risk levels (high/medium/low)
- **Merge policy** — Which CI checks are required per risk tier
- **Rollout phases** — Progressive enforcement (phase-0: advisory → phase-2: full enforcement)
- **Review policy** — CodeRabbit configuration, timeout, actionable keywords
- **Evidence policy** — UI impact paths requiring browser evidence

All GitHub Actions workflows consume this contract.

### 3. Python Harness Scripts (`scripts/harness/`)

Battle-tested CI scripts ported from open_fang:
- `risk_policy_gate.py` — Main deterministic PR preflight gate
- `checks_resolver.py` — Risk tier computation and policy helpers
- `coderabbit_state.py` — GitHub check-run polling for CodeRabbit review state
- `rerun_comment_dedupe.py` — Deduplicated review rerun comments per SHA
- `browser_evidence_verify.py` — Browser evidence manifest validation
- `emit_structured_event.py` — Structured telemetry event emission
- `linear_sync.py` — GitHub ↔ Linear issue sync

### 4. GitHub Actions Workflows (`.github/workflows/`)

Dependency chain:
```
risk-policy-gate.yml  (trigger: pull_request)
  ├── coderabbit-rerun.yml      (trigger: workflow_run)
  ├── coderabbit-auto-resolve.yml (trigger: workflow_run)
  ├── ci-pipeline.yml           (trigger: workflow_run)
  └── harness-smoke.yml         (trigger: workflow_run)

codex-agent.yml   (trigger: issues labeled agent:codex)
claude-agent.yml  (trigger: issues labeled agent:claude)
linear-sync.yml   (trigger: issues + pull_request + schedule)
```

### 5. Observability

- **Sentry** — Error tracking and performance monitoring
- **Structured events** — Telemetry via `emit_structured_event.py`

## Data Flow

```
Issue (Linear/GitHub)
  → Agent (Codex/Claude) creates branch + PR
  → risk-policy-gate classifies risk, checks review state
  → CodeRabbit reviews current-head SHA
  → If findings → remediation agent patches
  → Rerun deduplicated (once per SHA)
  → CI fanout (ExUnit, Credo, Dialyzer, format, secrets)
  → All pass → ready for human merge
```

## Technology Choices

| Choice | Rationale |
|--------|-----------|
| Phoenix/Elixir | Fault-tolerant, real-time capable, excellent for control-plane |
| Python for CI scripts | Battle-tested from open_fang, stdlib-only (no pip deps) |
| CodeRabbit over Greptile | Better Elixir support, GitHub-native integration |
| Codex primary, Claude backup | Codex for routine tasks, Claude for complex reasoning |
| Contract-driven policy | Single source of truth, machine-readable, versionable |
